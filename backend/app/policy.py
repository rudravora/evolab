"""Backend job policy, checked when a job is created (ARCHITECTURE section 6, API.md section 9).

The worker re-checks every job with its own policy (worker/policy.py). This
module mirrors that policy's verdicts so a job the backend accepts is not
refused by the worker, and it validates payload shapes per job type.

Verdicts: "auto" (claimable now), "approval" (risk='high', waits for an
approval), "deny" (never created).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

_LISTS = json.loads((Path(__file__).with_name("policy_lists.json")).read_text(encoding="utf-8"))
ALLOWED_PACKAGES = {p.lower() for p in _LISTS["packages"]}
ALLOWED_DOMAINS = {d.lower() for d in _LISTS["domains"]}
MAX_DOWNLOAD_BYTES = int(_LISTS["max_download_bytes"])
LONG_RUN_APPROVAL_S = int(_LISTS["long_run_approval_s"])

JOB_TYPES = {"shell", "python_script", "pip_install", "write_file", "read_file", "list_dir", "git", "download"}

DENY_COMMANDS = {"sudo", "su", "ssh", "scp", "sftp", "shutdown", "reboot", "poweroff", "halt", "init"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish", "powershell", "pwsh", "cmd"}
DOWNLOADERS = {"curl", "wget", "fetch", "http"}
DELETE_COMMANDS = {"rm", "rmdir", "del", "unlink", "shred"}
AUTO_COMMANDS = {"python", "python3", "ls", "mkdir", "cat"}
CREDENTIAL_MARKERS = (".ssh", ".aws", ".gnupg", ".netrc", ".git-credentials", "id_rsa", "id_ed25519", ".env", "credentials")
PY_ESCAPES = ("os.system", "subprocess", "os.popen", "os.exec", "pty.spawn", "__import__('os')", '__import__("os")')
DENY_ENV_KEYS = {"GIT_SSH_COMMAND", "PYTHONPATH", "PYTHONSTARTUP", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL"}
DENY_ENV_PREFIXES = ("GIT_CONFIG", "LD_", "DYLD_")
DENY_ENV_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET")
PINNED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?==[A-Za-z0-9.+!_-]+$")


@dataclass(frozen=True)
class Verdict:
    kind: str            # auto | approval | deny
    reason: str
    approval_type: str | None = None   # risky_command | new_package | expensive_run


def _deny(reason: str) -> Verdict:
    return Verdict("deny", reason)


def _approval(reason: str, approval_type: str = "risky_command") -> Verdict:
    return Verdict("approval", reason, approval_type)


def check_path(p: object, field: str) -> str | None:
    """Jail rule (D-042): relative to WORKSPACE_ROOT/<project_id>/, no absolute paths, no '..'."""
    if not isinstance(p, str) or not p.strip():
        return f"{field} must be a non-empty string"
    if "\x00" in p:
        return f"{field} contains a NUL byte"
    for flavour in (PurePosixPath(p), PureWindowsPath(p)):
        if flavour.is_absolute() or flavour.drive or flavour.root:
            return f"{field} must be relative to the project jail: {p!r}"
        if ".." in flavour.parts:
            return f"{field} must not contain '..': {p!r}"
    return None


def _argv(payload: dict) -> list[str] | str:
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return "argv must be a non-empty list of strings (never a shell string)"
    return argv


def _env_problem(env: object) -> str | None:
    if env is None:
        return None
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        return "env must be an object of string values"
    for key in env:
        up = key.upper()
        if up in DENY_ENV_KEYS or up.startswith(DENY_ENV_PREFIXES) or up.endswith(DENY_ENV_SUFFIXES):
            return f"env key not allowed: {key}"
    return None


def _command_verdict(argv: list[str]) -> Verdict:
    cmd = os.path.basename(argv[0]).lower().removesuffix(".exe")
    if cmd in DENY_COMMANDS:
        return _deny(f"denied command: {cmd}")
    if cmd in SHELLS or any(t == "|" for t in argv):
        return _deny("shell interpreters and pipes are denied")
    if cmd in DOWNLOADERS:
        return _deny(f"{cmd} must go through a download job")
    if any(m in a.lower() for a in argv for m in CREDENTIAL_MARKERS):
        return _deny("argument touches a credential path")
    if cmd in ("python", "python3") and "-c" in argv:
        i = argv.index("-c")
        if i + 1 < len(argv) and any(m in argv[i + 1] for m in PY_ESCAPES):
            return _deny("python -c script invokes a shell or process escape")
    if cmd in DELETE_COMMANDS or "-delete" in argv or "--delete" in argv:
        return _approval("delete operation")
    if cmd in AUTO_COMMANDS:
        return Verdict("auto", f"{cmd} inside the jail")
    return _approval(f"command not on the auto list: {cmd}")


def classify(job_type: str, payload: dict, timeout_s: int) -> Verdict:
    if job_type not in JOB_TYPES:
        return _deny(f"unknown job type: {job_type}")
    if not isinstance(payload, dict):
        return _deny("payload must be an object")

    for field in ("cwd", "path", "dest"):
        if field in payload and (problem := check_path(payload[field], field)):
            return _deny(problem)

    if job_type in ("shell", "python_script"):
        argv = _argv(payload)
        if isinstance(argv, str):
            return _deny(argv)
        if problem := _env_problem(payload.get("env")):
            return _deny(problem)
        if job_type == "python_script":
            if os.path.basename(argv[0]).lower().removesuffix(".exe") not in ("python", "python3") or len(argv) < 2 \
                    or not argv[1].endswith(".py"):
                return _deny('python_script argv must be ["python", "<file>.py", ...]')
            if problem := check_path(argv[1], "script"):
                return _deny(problem)
        verdict = _command_verdict(argv)
    elif job_type == "pip_install":
        pkgs = payload.get("packages")
        if not isinstance(pkgs, list) or not pkgs:
            return _deny("packages must be a non-empty list")
        unpinned = [p for p in pkgs if not isinstance(p, str) or not PINNED.match(p)]
        if unpinned:
            return _deny(f"packages must be pinned as name==version: {unpinned}")
        if payload.get("index_url") or payload.get("extra_index_url"):
            return _approval("custom package index", "new_package")
        unknown = [p for p in pkgs if re.split(r"[\[=]", p, maxsplit=1)[0].lower() not in ALLOWED_PACKAGES]
        verdict = _approval(f"package(s) not on the allowlist: {unknown}", "new_package") if unknown \
            else Verdict("auto", "all packages on the allowlist")
    elif job_type == "download":
        url = payload.get("url")
        if not isinstance(url, str) or urlparse(url).scheme != "https":
            return _deny("download url must be https")
        if "dest" not in payload:
            return _deny("download needs dest")
        host = (urlparse(url).hostname or "").lower()
        size = payload.get("size_bytes")
        if host not in ALLOWED_DOMAINS:
            verdict = _approval(f"domain not on the allowlist: {host}")
        elif isinstance(size, (int, float)) and size > MAX_DOWNLOAD_BYTES:
            verdict = _approval(f"download size {size} exceeds {MAX_DOWNLOAD_BYTES}")
        else:
            verdict = Verdict("auto", "domain allowlisted")
    elif job_type == "git":
        op, args = payload.get("op"), payload.get("args", {})
        if op == "push":
            return _deny("git push is denied")
        if op not in ("init", "commit", "diff") or not isinstance(args, dict):
            return _deny("git op must be init, commit or diff with an args object")
        if op == "commit" and not isinstance(args.get("message"), str):
            return _deny("git commit needs args.message")
        if op == "diff":
            paths = args.get("paths", [])
            if not isinstance(paths, list):
                return _deny("git diff args.paths must be a list")
            for p in paths:
                if problem := check_path(p, "paths"):
                    return _deny(problem)
        verdict = Verdict("auto", f"git {op} inside the jail")
    else:  # write_file, read_file, list_dir
        if "path" not in payload:
            return _deny(f"{job_type} needs path")
        if job_type == "write_file" and not (isinstance(payload.get("content"), str) or payload.get("artifact_id")):
            return _deny("write_file needs content or artifact_id")
        verdict = Verdict("auto", f"{job_type} inside the jail")

    if verdict.kind == "auto" and timeout_s > LONG_RUN_APPROVAL_S:
        return _approval(f"timeout {timeout_s}s exceeds the long-run threshold {LONG_RUN_APPROVAL_S}s", "expensive_run")
    return verdict
