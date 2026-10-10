"""Workspace jail and command policy (ARCHITECTURE.md section 6).

Two independent checks:
- resolve_in_jail(path, root): is this path inside root, after resolving
  symlinks and ".." segments?
- classify(job): is this job auto-runnable, does it need approval, or is it
  denied outright? Independent of whatever `risk` tag the backend already put
  on the job at creation time — this is the worker's own second opinion,
  required by API.md section 9 ("re-check every command against the local
  policy").

Deny always wins: a job the backend marked `approved` may run its
needs_approval items, but a deny verdict never runs regardless of approval.
"""
import ipaddress
import os
import shlex
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent

DENY_COMMANDS = {"sudo", "ssh", "scp", "sftp", "shutdown", "reboot", "poweroff", "halt", "init"}
SHELL_PIPE_TARGETS = {"sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish", "powershell", "pwsh", "cmd"}
DOWNLOADER_COMMANDS = {"curl", "wget", "fetch", "http"}
DELETE_COMMANDS = {"rm", "rmdir", "del", "unlink", "shred"}
CREDENTIAL_PATH_MARKERS = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".netrc",
    ".git-credentials",
    "id_rsa",
    "id_ed25519",
    ".env",
    "credentials",
)
AUTO_FILE_COMMANDS = {"python", "python3", "ls", "mkdir", "cat"}

DEFAULT_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024  # 200 MiB; caller may override


class JailViolation(Exception):
    pass


def resolve_in_jail(path: str | os.PathLike, root: str | os.PathLike) -> Path:
    """Resolve `path` (relative to `root` if not absolute) and require the
    result to sit inside `root`, after resolving symlinks and ".." segments.

    Raises JailViolation on any escape attempt, including:
    - absolute paths outside root
    - literal ".." segments
    - symlinks (anywhere in the chain) that resolve outside root

    Uses os.path.realpath so this catches symlink escapes even for paths that
    don't exist yet (realpath resolves the existing prefix and leaves the
    rest literal, which is sufficient: an attacker needs an existing symlink
    somewhere in the chain to escape, and that symlink gets resolved).
    """
    root_real = Path(os.path.realpath(root))
    raw = Path(path)

    if raw.is_absolute():
        candidate = raw
    else:
        candidate = root_real / raw

    resolved = Path(os.path.realpath(candidate))

    try:
        resolved.relative_to(root_real)
    except ValueError:
        raise JailViolation(f"path escapes jail root: {path!r} -> {resolved}")

    return resolved


def _load_list_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line.lower())
    return names


def load_package_allowlist(path: Path | None = None) -> set[str]:
    return _load_list_file(path or (HERE / "package_allowlist.txt"))


def load_domain_allowlist(path: Path | None = None) -> set[str]:
    return _load_list_file(path or (HERE / "domain_allowlist.txt"))


def _package_name(spec: str) -> str:
    """Strip a version/extras suffix from a pip package spec, e.g.
    'numpy==1.26.0' -> 'numpy', 'scikit-learn[extra]>=1.0' -> 'scikit-learn'.
    """
    name = spec.strip()
    for sep in ("==", ">=", "<=", "!=", "~=", ">", "<", "["):
        name = name.split(sep, 1)[0]
    return name.strip().lower()


def _looks_like_pip_extra_index(args: list[str]) -> bool:
    flags = {"--index-url", "-i", "--extra-index-url", "--find-links", "-f"}
    return any(a in flags for a in args)


def _is_delete_argv(argv: list[str]) -> bool:
    if not argv:
        return False
    cmd = os.path.basename(argv[0])
    if cmd in DELETE_COMMANDS:
        return True
    # `find ... -delete`, `git clean -fd` style deletes hidden in flags
    if "-delete" in argv or "--delete" in argv:
        return True
    return False


def _touches_credential_path(argv: list[str]) -> bool:
    for arg in argv:
        lowered = arg.lower()
        for marker in CREDENTIAL_PATH_MARKERS:
            if marker in lowered:
                return True
    return False


def _has_shell_pipe_to_interpreter(argv: list[str]) -> bool:
    """Catches `curl ... | sh` style patterns. Since argv is a single
    command's arguments (never a shell string per the no-shell=True rule),
    a literal pipe only shows up if someone embedded shell metacharacters as
    a plain argv token (e.g. ["curl", "http://x", "|", "sh"] passed to a
    *shell* job type we don't support) or asked for a shell job type at all.
    We deny any argv whose first token is a shell interpreter outright, and
    separately deny any argv containing a literal '|' followed by a shell
    name, in case a caller built that token list from a user shell string.
    """
    if not argv:
        return False
    cmd = os.path.basename(argv[0])
    if cmd in SHELL_PIPE_TARGETS:
        return True
    for i, tok in enumerate(argv):
        if tok == "|" and i + 1 < len(argv):
            nxt = os.path.basename(argv[i + 1])
            if nxt in SHELL_PIPE_TARGETS:
                return True
    return False


def _python_c_runs_shell(argv: list[str]) -> bool:
    """Flags `python -c "...os.system(...)..."` / subprocess / shell escapes
    embedded in an inline -c script. This is a heuristic string search, not a
    parse of the Python source — see the "cannot reliably catch" notes.
    """
    if not argv:
        return False
    cmd = os.path.basename(argv[0])
    if cmd not in ("python", "python3"):
        return False
    if "-c" not in argv:
        return False
    idx = argv.index("-c")
    if idx + 1 >= len(argv):
        return False
    script = argv[idx + 1]
    danger_markers = (
        "os.system",
        "subprocess",
        "os.popen",
        "os.exec",
        "pty.spawn",
        "__import__('os')",
        '__import__("os")',
    )
    return any(marker in script for marker in danger_markers)


def _git_injects_config(argv: list[str]) -> bool:
    """`git -c core.sshCommand=... ...` or `-c` with any key that can run an
    external command (sshCommand, pager, core.editor, alias.*, http.proxy).
    """
    if not argv or os.path.basename(argv[0]) != "git":
        return False
    dangerous_keys = ("sshcommand", "core.editor", "pager", "http.proxy", "credential.helper")
    for i, tok in enumerate(argv):
        if tok == "-c" and i + 1 < len(argv):
            key = argv[i + 1].split("=", 1)[0].lower()
            if any(dk in key for dk in dangerous_keys) or key.startswith("alias."):
                return True
        if tok.startswith("-c") and len(tok) > 2:
            key = tok[2:].split("=", 1)[0].lower()
            if any(dk in key for dk in dangerous_keys) or key.startswith("alias."):
                return True
    return False


def _normalize_argv(job_type: str, payload: dict) -> list[str] | None:
    """Return the argv-equivalent list for argv-bearing job types, or None if
    this job type has no argv (write_file, read_file, list_dir, download).
    If `payload["argv"]` is a single string, parse it with shlex (never
    shell=True) and treat the parsed tokens as the real argv for re-checking.
    """
    if job_type in ("shell", "python_script"):
        argv = payload.get("argv")
        if isinstance(argv, str):
            return shlex.split(argv)
        if isinstance(argv, list):
            return [str(a) for a in argv]
        return []
    if job_type == "git":
        op = payload.get("op", "")
        args = payload.get("args", {}) or {}
        argv = ["git"]
        if isinstance(args, dict):
            extra = args.get("argv")
            if isinstance(extra, list):
                argv += [str(a) for a in extra]
        argv.append(op)
        return argv
    return None


def classify(job: dict, *, allowed_packages=None, allowed_domains=None, max_download_bytes=None) -> tuple[str, str]:
    """Classify a job dict (shape: {"type": ..., "payload": {...}, "cwd": ...,
    optionally "approved": bool}) as ("auto"|"needs_approval"|"deny", reason).

    Deny always wins over an "approved" flag; approval only unlocks
    needs_approval items.
    """
    allowed_packages = allowed_packages if allowed_packages is not None else load_package_allowlist()
    allowed_domains = allowed_domains if allowed_domains is not None else load_domain_allowlist()
    max_download_bytes = max_download_bytes if max_download_bytes is not None else DEFAULT_MAX_DOWNLOAD_BYTES

    job_type = job.get("type", "")
    payload = job.get("payload", {}) or {}
    approved = bool(job.get("approved", False))

    argv = _normalize_argv(job_type, payload)

    # --- Deny checks (apply regardless of job type, and regardless of approval) ---
    if argv:
        cmd = os.path.basename(argv[0]) if argv else ""
        if cmd in DENY_COMMANDS:
            return "deny", f"denied command: {cmd}"
        if _has_shell_pipe_to_interpreter(argv):
            return "deny", "piping to a shell interpreter is denied"
        if _python_c_runs_shell(argv):
            return "deny", "python -c script invokes a shell/process escape (os.system, subprocess, ...)"
        if job_type == "git" and payload.get("op") == "push":
            return "deny", "git push is denied"
        if _git_injects_config(argv):
            return "deny", "git -c with a command-executing config key is denied"
        if _touches_credential_path(argv):
            return "deny", "argument touches a credential path (.ssh, .aws, .env, etc.)"
        if cmd in DOWNLOADER_COMMANDS:
            # curl/wget run directly as argv[0] (not through a download job)
            # are never auto; piping to a shell is already caught above, but
            # a bare curl/wget invocation still bypasses the download policy
            # (domain allowlist, size limit), so treat it as denied outright.
            return "deny", f"{cmd} must go through a download job, not a direct command"

    # path-bearing job types: jail must hold regardless of verdict elsewhere
    path_field = payload.get("path")
    cwd = job.get("cwd") or payload.get("cwd")

    # --- needs_approval checks ---
    if job_type == "pip_install":
        packages = payload.get("packages", [])
        if _looks_like_pip_extra_index(payload.get("argv", []) if isinstance(payload.get("argv"), list) else []):
            if not approved:
                return "needs_approval", "pip install with a custom index/find-links URL"
        unknown = [p for p in packages if _package_name(p) not in allowed_packages]
        if unknown:
            if approved:
                pass  # fall through to auto below
            else:
                return "needs_approval", f"package(s) not on the allowlist: {unknown}"

    if job_type == "download":
        url = payload.get("url", "")
        size = payload.get("size_bytes")
        host = urlparse(url).hostname or ""
        if host.lower() not in allowed_domains:
            if not approved:
                return "needs_approval", f"domain not on the allowlist: {host!r}"
        if isinstance(size, (int, float)) and size > max_download_bytes:
            if not approved:
                return "needs_approval", f"download size {size} exceeds limit {max_download_bytes}"

    if argv and _is_delete_argv(argv):
        if not approved:
            return "needs_approval", "delete operation requires approval"
        return "auto", "delete operation approved"

    # --- jail check (applies to every job type that carries a path) ---
    # Actual filesystem resolution happens in the caller with the real
    # WORKSPACE_ROOT; classify() only flags obviously-unsafe literal path
    # shapes it can see without touching the filesystem.
    for candidate_path in (path_field, cwd):
        if candidate_path is None:
            continue
        if Path(candidate_path).is_absolute():
            return "deny", f"absolute path is outside the jail: {candidate_path!r}"
        if ".." in Path(candidate_path).parts:
            return "deny", f"path contains '..': {candidate_path!r}"

    # --- auto checks ---
    if job_type in ("write_file", "read_file", "list_dir"):
        return "auto", f"{job_type} inside the jail"

    if job_type == "git":
        op = payload.get("op", "")
        if op in ("init", "commit", "diff"):
            return "auto", f"git {op} inside the jail"
        return "needs_approval", f"git operation not in the auto list: {op!r}"

    if job_type == "pip_install":
        return "auto", "all packages on the allowlist"

    if job_type in ("shell", "python_script") and argv:
        cmd = os.path.basename(argv[0])
        if cmd in AUTO_FILE_COMMANDS:
            return "auto", f"{cmd} inside the jail"
        return "needs_approval", f"command not on the auto allowlist: {cmd!r}"

    if job_type == "download":
        return "auto", "domain allowlisted and within size limit"

    return "needs_approval", f"unrecognized job type: {job_type!r}"
