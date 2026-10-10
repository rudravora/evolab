"""Job runner: executes a job's argv under worker/policy.py's checks
(ARCHITECTURE.md sections 3.2 job lifecycle and 6 safety).

Cross-platform: Windows, macOS and Linux. No POSIX-only (or Windows-only)
module is imported at top level unconditionally -- resource (POSIX) and the
Windows-only bits of subprocess/os are all guarded, so importing this module
on any platform never raises, even though the actual process-tree-kill path
differs per platform (see kill_process_tree below).

Safety properties:
- Never starts a process for a `deny` verdict, or an un-approved
  `needs_approval` verdict.
- POSIX: runs in its own process group (start_new_session=True) so the
  whole group, including any children the job spawns, can be signalled
  together via os.killpg. Windows: runs with
  CREATE_NEW_PROCESS_GROUP so SIGBREAK/CTRL_BREAK_EVENT could reach the
  group, but the actual kill path is psutil-based tree walking (Windows has
  no process-group-wide SIGKILL equivalent) with `taskkill /T /F` as a
  fallback if psutil itself is unavailable or fails.
- Per-job wall-clock timeout: terminate the whole process tree, short grace
  period, then force-kill. Reports `timed_out`.
- Output capped at max_output_bytes; stdout_tail/stderr_tail hold only the
  tail once the cap is hit.
- Clean environment, platform-specific base keys (see build_clean_env),
  plus only the payload-provided keys that pass policy.check_env. The
  parent's full environment (including secrets) is never inherited.
- RLIMIT_CPU, RLIMIT_NOFILE, RLIMIT_FSIZE are set via a preexec_fn, POSIX
  only (the `resource` module does not exist on Windows, and is not
  meaningfully enforced on macOS for RLIMIT_AS/RLIMIT_DATA -- see the
  memory note below).
- Memory limit: enforced on every platform by polling RSS of the whole
  process tree via psutil and killing the tree if it exceeds the cap, since
  neither macOS nor Windows enforces a memory rlimit the way Linux does.
  psutil is a required dependency (not optional) specifically so this
  enforcement always exists.
- Log lines are scrubbed for API-key/token-shaped strings before being
  batched into chunks and handed to the `on_log` callback, roughly once a
  second.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import policy
import psutil

try:
    import resource
except ImportError:
    resource = None  # resource is POSIX-only; absent on Windows

IS_WINDOWS = os.name == "nt"

LOG_FLUSH_INTERVAL_S = 1.0
TERMINATE_GRACE_S = 3.0
DEFAULT_MAX_RSS_BYTES = 1024 * 1024 * 1024  # 1 GiB; caller may override
MEMORY_POLL_INTERVAL_S = 1.0

# RLIMIT_CPU is seconds of CPU time, used as a backstop alongside the
# wall-clock timeout (a busy-looping single-threaded job hits this close to
# its wall time; a mostly-sleeping job won't, which is intentional -- the
# wall-clock timeout in run_job is the primary enforcement). POSIX only.
DEFAULT_RLIMIT_CPU_S = 3600
DEFAULT_RLIMIT_NOFILE = 256
DEFAULT_RLIMIT_FSIZE_BYTES = 500 * 1024 * 1024  # 500 MiB per written file

# Secret-shaped strings to scrub from logs before they leave this process.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{16,}"),
    re.compile(r"gho_[A-Za-z0-9]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{16,}"),
    # Matches `key=`, `api_key=`, `token=`, `auth_token=`, `secret=`, etc. --
    # the identifier just needs to END in one of these words, not equal it
    # exactly, since real-world env/config keys are usually prefixed
    # (API_KEY, AUTH_TOKEN, DB_PASSWORD, ...).
    re.compile(r"(?i)[A-Za-z0-9_]*(?:key|token|secret|password|passwd)\s*=\s*[\"']?[A-Za-z0-9+/_\-]{16,}[\"']?"),
]


def scrub_secrets(text: str) -> str:
    """Replace API-key/token-shaped substrings with a redaction marker."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# Base environment keys preserved from the worker process's own environment,
# per platform. Everything else is dropped; only policy.check_env-approved
# extra keys from the job payload are added on top (see build_clean_env).
POSIX_BASE_ENV_KEYS = ("PATH", "HOME", "LANG")
WINDOWS_BASE_ENV_KEYS = ("PATH", "PATHEXT", "SYSTEMROOT", "COMSPEC", "USERPROFILE", "TEMP", "TMP")


def build_clean_env(workspace_dir: Path, extra_env: dict | None) -> tuple[dict, list[str]]:
    """Clean subprocess environment: a small platform-appropriate base plus
    a workspace-local temp dir, plus only the extra_env keys that pass
    policy.check_env. The parent process's environment is never inherited.
    """
    tmp_dir = str(workspace_dir / ".tmp")
    if IS_WINDOWS:
        base = {k: os.environ[k] for k in WINDOWS_BASE_ENV_KEYS if k in os.environ}
        base.setdefault("SYSTEMROOT", r"C:\Windows")
        base.setdefault("COMSPEC", r"C:\Windows\System32\cmd.exe")
        base["TEMP"] = tmp_dir
        base["TMP"] = tmp_dir
    else:
        base = {k: os.environ[k] for k in POSIX_BASE_ENV_KEYS if k in os.environ}
        base.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        base.setdefault("HOME", "/tmp")
        base.setdefault("LANG", "en_US.UTF-8")
        base["TMPDIR"] = tmp_dir

    allowed_extra, rejected = policy.check_env(extra_env or {})
    base.update(allowed_extra)
    return base, rejected


def resolve_python_executable(argv: list[str]) -> list[str]:
    """If argv[0] names a bare "python"/"python3" interpreter, substitute
    sys.executable -- the literal name is never guaranteed to exist on
    PATH (not on a minimal Windows runner, and not reliably as exactly
    "python3" vs "python" across platforms either). Any other argv[0] is
    left untouched: this only replaces what policy.classify's
    AUTO_FILE_COMMANDS already recognises as a generic interpreter call.
    """
    if not argv:
        return argv
    if policy.normalize_command_name(argv[0]) in ("python", "python3"):
        return [sys.executable, *argv[1:]]
    return argv


def _set_resource_limits(
    cpu_s: int = DEFAULT_RLIMIT_CPU_S,
    nofile: int = DEFAULT_RLIMIT_NOFILE,
    fsize_bytes: int = DEFAULT_RLIMIT_FSIZE_BYTES,
):
    """Returned as a preexec_fn (POSIX only; never passed to Popen on
    Windows). Runs in the child after fork, before exec. Sets what POSIX
    actually enforces (CPU time, file descriptor count, max file size).
    Does NOT attempt a memory rlimit -- see module docstring.
    """
    def _apply():
        if resource is None:  # defensive; _set_resource_limits is only used on POSIX
            return
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        except (ValueError, OSError):
            pass
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            cap = min(nofile, hard) if hard != resource.RLIM_INFINITY else nofile
            resource.setrlimit(resource.RLIMIT_NOFILE, (cap, hard))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes))
        except (ValueError, OSError):
            pass
        # No os.setsid() here: start_new_session=True on Popen already calls
        # it before preexec_fn runs, and calling it twice raises OSError
        # ("Exception occurred in preexec_fn"), aborting the spawn entirely.

    return _apply


def popen_job(argv: list[str], cwd: Path, env: dict) -> subprocess.Popen:
    """Start argv as its own process group (POSIX) or process group leader
    (Windows), ready for kill_process_tree to signal the whole tree later.
    """
    if IS_WINDOWS:
        return subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,  # own process group; pgid == proc.pid
        preexec_fn=_set_resource_limits(),
    )


def kill_process_tree(pid: int, *, grace_s: float = TERMINATE_GRACE_S) -> None:
    """Kill pid and every descendant it has spawned, on any platform.

    POSIX: os.killpg is the fast path (SIGTERM to the whole group, wait up
    to grace_s, then SIGKILL) since it needs no extra dependency and
    reliably reaches processes that re-parented after their parent exited,
    as long as they stayed in the same process group.

    Windows (and as a POSIX fallback if os.killpg is unavailable): walk the
    process tree with psutil (children recursive), terminate() each, wait
    up to grace_s, then kill() whatever is left. If psutil itself raises
    something unexpected, fall back to `taskkill /T /F` on Windows as a
    last resort.
    """
    if not IS_WINDOWS and hasattr(os, "killpg"):
        _killpg_tree(pid, grace_s=grace_s)
        return

    try:
        _psutil_tree_kill(pid, grace_s=grace_s)
    except Exception:
        if IS_WINDOWS:
            _taskkill_fallback(pid)


def _killpg_tree(pgid: int, *, grace_s: float) -> None:
    import signal

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        pass
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # raises ProcessLookupError once the group is gone
        except ProcessLookupError:
            return
        except PermissionError:
            # pgid was reaped and reused by a process we can't signal; we
            # can no longer tell whether our job's group is still alive, so
            # stop polling and fall through to the SIGKILL attempt below.
            break
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _psutil_tree_kill(pid: int, *, grace_s: float) -> None:
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    procs = []
    try:
        procs = root.children(recursive=True)
    except psutil.NoSuchProcess:
        pass
    procs.append(root)

    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass

    gone, alive = psutil.wait_procs(procs, timeout=grace_s)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=2)


def _taskkill_fallback(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass  # best effort; nothing more we can do


class CancelRegistry:
    """Thread-safe map of job_id -> (process id, cancel event) for jobs
    currently executing. Lets the heartbeat loop's cancel_job_ids handling
    (worker.py) kill a running job's process tree from a different thread
    than the one running execute() for that job: cancel() sets the event and
    kills the tree directly; execute()'s own watchdog thread for that job
    waits on the same event purely to label the result "cancelled" instead
    of "failed" once proc.wait() returns.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[int, threading.Event]] = {}

    def register(self, job_id: str, pid: int) -> threading.Event:
        event = threading.Event()
        if job_id is not None:
            with self._lock:
                self._entries[job_id] = (pid, event)
        return event

    def unregister(self, job_id: str) -> None:
        if job_id is None:
            return
        with self._lock:
            self._entries.pop(job_id, None)

    def cancel(self, job_id: str) -> bool:
        """Kill the process tree for job_id if it is currently running.
        Returns True if a running job was found and killed, False otherwise
        (already finished, or never registered)."""
        with self._lock:
            entry = self._entries.get(job_id)
        if entry is None:
            return False
        pid, event = entry
        event.set()
        kill_process_tree(pid)
        return True


def _group_rss_bytes(pid: int) -> int:
    """Sum RSS across the process and all its descendants. Requires psutil
    (a required dependency of this module)."""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return 0
    total = 0
    try:
        total += proc.memory_info().rss
    except psutil.NoSuchProcess:
        pass
    try:
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.NoSuchProcess:
                continue
    except psutil.NoSuchProcess:
        pass
    return total


class _OutputCapture:
    """Reads a pipe in a background thread, applying the byte cap and
    forwarding scrubbed lines to a chunk buffer flushed roughly every
    LOG_FLUSH_INTERVAL_S seconds via on_chunks(list[chunk]).
    """

    def __init__(self, stream_name: str, pipe, max_bytes: int, seq_counter: list, on_chunks, lock: threading.Lock):
        self.stream_name = stream_name
        self.pipe = pipe
        self.max_bytes = max_bytes
        self.seq_counter = seq_counter
        self.on_chunks = on_chunks
        self.lock = lock
        self.captured_bytes = 0
        self.tail_lines: list[str] = []
        self.truncated = False
        self._pending: list[str] = []
        self._pending_lock = threading.Lock()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)

    def start(self) -> None:
        self.thread.start()
        self.flush_thread.start()

    def _read_loop(self) -> None:
        for raw_line in iter(self.pipe.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            line = scrub_secrets(line)
            encoded_len = len(raw_line)
            if self.captured_bytes + encoded_len > self.max_bytes:
                self.truncated = True
                remaining = max(0, self.max_bytes - self.captured_bytes)
                if remaining > 0:
                    self.tail_lines.append(line[:remaining])
                self.captured_bytes = self.max_bytes
            else:
                self.tail_lines.append(line)
                self.captured_bytes += encoded_len
            with self._pending_lock:
                self._pending.append(line)
        self.pipe.close()
        self._stop.set()

    def _flush_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(LOG_FLUSH_INTERVAL_S)
            self._flush()
        self._flush()  # final flush after the pipe closes

    def _flush(self) -> None:
        with self._pending_lock:
            if not self._pending:
                return
            lines = self._pending
            self._pending = []
        chunks = []
        with self.lock:
            for line in lines:
                self.seq_counter[0] += 1
                chunks.append({"seq": self.seq_counter[0], "stream": self.stream_name, "text": line})
        if chunks:
            self.on_chunks(chunks)

    def join(self, timeout: float | None = None) -> None:
        self.thread.join(timeout=timeout)
        self.flush_thread.join(timeout=timeout)

    def tail_text(self, max_chars: int = 5000) -> str:
        text = "\n".join(self.tail_lines)
        return text[-max_chars:]


def execute(
    argv: list[str],
    cwd: Path,
    env: dict,
    timeout_s: int,
    max_output_bytes: int,
    on_log=None,
    max_rss_bytes: int = DEFAULT_MAX_RSS_BYTES,
    cancel_registry: "CancelRegistry | None" = None,
    job_id: str | None = None,
) -> dict:
    """Run argv (a real list, never a shell string) as its own process
    tree under cwd/env, capturing output and enforcing timeout_s and
    max_rss_bytes (via psutil, on every platform).

    "python"/"python3" as argv[0] are replaced with sys.executable (see
    resolve_python_executable) before the process is started.

    If cancel_registry is given, this job's process id is registered under
    job_id for the duration of the run so a concurrent call to
    cancel_registry.cancel(job_id) (from the heartbeat loop, handling
    cancel_job_ids) can kill it; the registration is removed once the
    process exits, win or lose.

    Returns {"status", "exit_code", "stdout_tail", "stderr_tail"}. status is
    "cancelled" if cancel_registry.cancel() killed it, "timed_out" if the
    wall-clock timeout killed it, "done" on exit code 0, else "failed". Does
    not know about `metrics`/`files` (results JSON) -- see run_job below.
    """
    on_log = on_log or (lambda chunks: None)
    argv = resolve_python_executable(argv)
    seq_counter = [0]
    log_lock = threading.Lock()

    try:
        proc = popen_job(argv, cwd, env)
    except (OSError, FileNotFoundError) as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": f"failed to start process: {exc}",
        }

    pid = proc.pid
    cancel_event = None
    if cancel_registry is not None and job_id is not None:
        cancel_event = cancel_registry.register(job_id, pid)

    stdout_capture = _OutputCapture("stdout", proc.stdout, max_output_bytes, seq_counter, on_log, log_lock)
    stderr_capture = _OutputCapture("stderr", proc.stderr, max_output_bytes, seq_counter, on_log, log_lock)
    stdout_capture.start()
    stderr_capture.start()

    timed_out = threading.Event()
    memory_exceeded = threading.Event()
    cancelled = threading.Event()
    proc_finished = threading.Event()

    def _timeout_watchdog():
        if not proc_finished.wait(timeout_s):
            timed_out.set()
            kill_process_tree(pid)

    def _memory_watchdog():
        while not proc_finished.is_set():
            if proc_finished.wait(MEMORY_POLL_INTERVAL_S):
                return
            try:
                rss = _group_rss_bytes(pid)
            except Exception:
                continue
            if rss > max_rss_bytes:
                memory_exceeded.set()
                kill_process_tree(pid)
                return

    def _cancel_watchdog():
        # cancel_registry.cancel() (called from the heartbeat thread) sets
        # cancel_event and kills the process tree itself; this thread's
        # only job is to notice that happened so the result can be labelled
        # "cancelled" rather than "failed" once proc.wait() returns. Waits on
        # proc_finished too so it doesn't block past the process's own exit.
        if cancel_event is None:
            return
        while not proc_finished.is_set():
            if cancel_event.wait(0.2):
                cancelled.set()
                return

    timeout_thread = threading.Thread(target=_timeout_watchdog, daemon=True)
    memory_thread = threading.Thread(target=_memory_watchdog, daemon=True)
    cancel_thread = threading.Thread(target=_cancel_watchdog, daemon=True)
    timeout_thread.start()
    memory_thread.start()
    cancel_thread.start()

    exit_code = proc.wait()
    proc_finished.set()

    if cancel_registry is not None and job_id is not None:
        cancel_registry.unregister(job_id)

    stdout_capture.join(timeout=5)
    stderr_capture.join(timeout=5)
    timeout_thread.join(timeout=1)
    memory_thread.join(timeout=1)
    cancel_thread.join(timeout=1)

    if cancelled.is_set():
        status = "cancelled"
    elif timed_out.is_set():
        status = "timed_out"
    elif memory_exceeded.is_set():
        status = "failed"
    elif exit_code == 0:
        status = "done"
    else:
        status = "failed"

    stderr_tail = stderr_capture.tail_text()
    if memory_exceeded.is_set():
        stderr_tail = (stderr_tail + "\nkilled: exceeded memory limit (RSS)").strip()
    if cancelled.is_set():
        stderr_tail = (stderr_tail + "\ncancelled: job was cancelled").strip()

    return {
        "status": status,
        "exit_code": exit_code,
        "stdout_tail": stdout_capture.tail_text(),
        "stderr_tail": stderr_tail,
    }


def _read_results_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _denied(reason: str) -> dict:
    return {
        "status": "failed",
        "exit_code": None,
        "stdout_tail": "",
        "stderr_tail": f"policy_denied: {reason}",
        "metrics": {},
        "files": [],
    }


def _write_file_job(payload: dict, jail_root: Path) -> dict:
    """read_file/list_dir/write_file are implemented directly in Python
    rather than shelling out to cat/ls/mkdir (per the task spec: "do not
    rely on ls, cat or mkdir existing as programs"). Cross-platform, and
    does not need policy.normalize_argv or a subprocess at all.
    """
    path_rel = payload.get("path")
    try:
        target = policy.resolve_in_jail(path_rel, jail_root)
    except policy.JailViolation as exc:
        return _denied(str(exc))

    content = payload.get("content")
    if content is None:
        return _denied("write_file requires a 'content' field (artifact_id is not yet supported)")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": f"write_file failed: {exc}",
            "metrics": {},
            "files": [],
        }
    return {
        "status": "done",
        "exit_code": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "metrics": {},
        "files": [],
    }


def _read_file_job(payload: dict, jail_root: Path) -> dict:
    path_rel = payload.get("path")
    try:
        target = policy.resolve_in_jail(path_rel, jail_root)
    except policy.JailViolation as exc:
        return _denied(str(exc))

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": f"read_file failed: {exc}",
            "metrics": {},
            "files": [],
        }
    return {
        "status": "done",
        "exit_code": 0,
        "stdout_tail": text,
        "stderr_tail": "",
        "metrics": {},
        "files": [],
    }


def _list_dir_job(payload: dict, jail_root: Path) -> dict:
    path_rel = payload.get("path", ".")
    try:
        target = policy.resolve_in_jail(path_rel, jail_root)
    except policy.JailViolation as exc:
        return _denied(str(exc))

    try:
        entries = sorted(os.listdir(target))
    except OSError as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": f"list_dir failed: {exc}",
            "metrics": {},
            "files": [],
        }
    lines = []
    for name in entries:
        suffix = "/" if (target / name).is_dir() else ""
        lines.append(name + suffix)
    return {
        "status": "done",
        "exit_code": 0,
        "stdout_tail": "\n".join(lines) + ("\n" if lines else ""),
        "stderr_tail": "",
        "metrics": {},
        "files": [],
    }


def run_job(job: dict, workspace_root: Path, on_log=None, cancel_registry=None) -> dict:
    """Classify the job, run it if allowed, return the result shape
    worker.py's post_result expects: status, exit_code, stdout_tail,
    stderr_tail, metrics, files.

    Never starts a process for `deny`, or for `needs_approval` unless
    job.get("approved") is true (ARCHITECTURE.md 3.2/6: deny always wins,
    approval only unlocks needs_approval items).

    API.md section 9 / D-042: every job carries `project_id` at the top
    level; the jail root for this job is WORKSPACE_ROOT/<project_id>/, not
    WORKSPACE_ROOT itself. project_id is validated before use (empty,
    absolute, '..' or a path separator are all rejected).

    `cancel_registry`, if given, is a CancelRegistry (see above) that this
    call registers its live subprocess's pid into for the duration of the
    run, so a concurrent cancel request (from the heartbeat loop) can find
    and kill it.
    """
    try:
        project_id = policy.validate_project_id(job.get("project_id"))
    except policy.JailViolation as exc:
        return _denied(str(exc))

    jail_root = workspace_root / project_id

    verdict, reason = policy.classify(job)
    if verdict == "deny":
        return _denied(reason)
    if verdict == "needs_approval" and not job.get("approved"):
        return _denied(f"needs_approval: {reason}")

    job_type = job.get("type", "")
    payload = job.get("payload", {}) or {}

    # read_file/list_dir/write_file are implemented in Python, not by
    # shelling out, so they're handled before the argv-based path below.
    if job_type == "write_file":
        return _write_file_job(payload, jail_root)
    if job_type == "read_file":
        return _read_file_job(payload, jail_root)
    if job_type == "list_dir":
        return _list_dir_job(payload, jail_root)

    argv = policy.normalize_argv(job_type, payload)
    if not argv:
        return {
            "status": "failed",
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": f"runner: no executable command for job type {job_type!r}",
            "metrics": {},
            "files": [],
        }

    cwd_rel = payload.get("cwd") or job.get("cwd") or "."
    try:
        cwd = policy.resolve_in_jail(cwd_rel, jail_root)
    except policy.JailViolation as exc:
        return _denied(str(exc))
    cwd.mkdir(parents=True, exist_ok=True)
    (jail_root / ".tmp").mkdir(parents=True, exist_ok=True)

    env, rejected_env_keys = build_clean_env(jail_root, payload.get("env"))

    job_id = job.get("job_id")
    result = execute(
        argv,
        cwd=cwd,
        env=env,
        timeout_s=job.get("timeout_s", 900),
        max_output_bytes=job.get("max_output_bytes", 5_000_000),
        on_log=on_log,
        cancel_registry=cancel_registry,
        job_id=job_id,
    )

    if rejected_env_keys and on_log:
        on_log(
            [
                {
                    "seq": 1,
                    "stream": "stderr",
                    "text": f"runner: rejected env keys not passed to the job: {rejected_env_keys}",
                }
            ]
        )

    results_path = payload.get("results_path")
    metrics = {}
    if results_path:
        try:
            resolved_results_path = policy.resolve_in_jail(results_path, jail_root)
            metrics = _read_results_file(resolved_results_path)
        except policy.JailViolation:
            pass  # results_path outside the jail: no metrics, job output stands as-is

    result["metrics"] = metrics
    result["files"] = []
    return result
