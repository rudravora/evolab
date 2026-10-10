"""Worker process: registers with the backend, heartbeats, pulls and runs jobs.

API.md section 9 is the contract. ARCHITECTURE.md sections 3.1 (pairing),
3.2 (job lifecycle) and 6 (safety) govern behaviour.

Cross-platform: Windows, macOS and Linux. psutil is a required dependency
(not optional) because runner.py's memory limit and process-tree kill rely
on it on every platform.

Run:
    BACKEND_URL=http://localhost:8000 PAIRING_CODE=ABCD-1234 \
        WORKSPACE_ROOT=./workspace MAX_JOBS=2 python worker.py

A second run with no PAIRING_CODE reuses the token in WORKSPACE_ROOT-relative
worker/.worker_token (first run only needs the pairing code).
"""
import json
import os
import random
import signal
import sys
import threading
import time
from pathlib import Path

import psutil
import requests

import policy
import runner

TOKEN_PATH = Path(__file__).resolve().parent / ".worker_token"
API_PREFIX = "/api/v1"

BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 60.0
LOG_FLUSH_INTERVAL_S = 1.0

RETRYABLE_STATUS_CODES = {429, 500, 501, 502, 503, 504}


class AuthError(Exception):
    """Raised when the backend returns 401 or 403: the worker token is
    invalid or revoked. D-042: a rejected token makes the worker exit and
    re-pair -- this is never retried with backoff."""


class JobHTTPError(Exception):
    """Raised for a non-retryable 4xx (not 401/403) on a job-specific call
    (start/logs/result). The caller reports that one job as failed instead
    of retrying forever or crashing the whole worker."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE per line, '#' comments, no quoting rules."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        os.environ.setdefault(key, value)


def load_config() -> dict:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    backend_url = os.environ.get("BACKEND_URL")
    if not backend_url:
        print("BACKEND_URL is required (env or worker/.env)", file=sys.stderr)
        sys.exit(1)
    workspace_root = os.environ.get("WORKSPACE_ROOT", "./workspace")
    max_jobs = int(os.environ.get("MAX_JOBS", "4"))
    cores = os.cpu_count() or 1
    concurrency = max(1, min(cores - 1, max_jobs))
    return {
        "backend_url": backend_url.rstrip("/"),
        "pairing_code": os.environ.get("PAIRING_CODE"),
        "workspace_root": Path(workspace_root).resolve(),
        "max_jobs": max_jobs,
        "concurrency": concurrency,
    }


def save_token(token: str) -> None:
    TOKEN_PATH.write_text(token)
    if os.name != "nt":
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except OSError:
            pass  # best-effort
    # On Windows, chmod's POSIX permission bits don't model NTFS ACLs, so we
    # skip it entirely rather than call something that wouldn't do what the
    # comment implies. The token file lives in this worker.py's own
    # directory, i.e. wherever the user checked out/cloned the worker --
    # typically under their user profile (e.g. C:\Users\<name>\...\worker\),
    # which is already private to that Windows user account by default.


def load_token() -> str | None:
    if not TOKEN_PATH.exists():
        return None
    return TOKEN_PATH.read_text().strip() or None


JailViolation = policy.JailViolation  # re-exported for callers/tests built against this name


def run_job(job: dict, workspace_root: Path, on_log=None, cancel_registry=None) -> dict:
    """Classify and run a job under worker/policy.py and worker/runner.py.

    API.md section 9 / D-042: `job["project_id"]` selects the jail root
    (WORKSPACE_ROOT/<project_id>/); runner.run_job validates it and resolves
    `cwd` and `results_path` relative to that root, not WORKSPACE_ROOT
    directly.
    """
    return runner.run_job(job, workspace_root, on_log=on_log, cancel_registry=cancel_registry)


class Worker:
    def __init__(self, config: dict):
        self.config = config
        self.backend_url = config["backend_url"]
        self.workspace_root = config["workspace_root"]
        self.concurrency = config["concurrency"]
        self.token: str | None = None
        self.worker_id: str | None = None
        self.poll_interval_s = 2
        self.heartbeat_interval_s = 10
        self.stop_event = threading.Event()
        self.running_jobs: dict[str, dict] = {}  # job_id -> {"attempt": int}
        self.running_jobs_lock = threading.Lock()
        self.active_count = 0
        self.active_count_lock = threading.Lock()
        self.cancel_registry = runner.CancelRegistry()
        self.auth_error: AuthError | None = None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _url(self, path: str) -> str:
        return f"{self.backend_url}{API_PREFIX}{path}"

    def _backoff_request(self, fn, *, what: str, job_call: bool = False):
        """Call fn() (which must call resp.raise_for_status() itself) with
        exponential backoff, but only for errors that backoff can actually
        fix: connection errors, timeouts, 429, and 5xx.

        401/403 (an invalid or revoked token) are never retried -- raises
        AuthError so the caller can exit with a clear message and a request
        for re-pairing (D-042).

        Any other 4xx is also never retried (retrying a malformed or
        rejected request forever just spins). If job_call is True, raises
        JobHTTPError so the caller reports that one job as failed instead of
        crashing the worker; if False (register/heartbeat/claim -- not tied
        to one job), the HTTPError itself propagates.

        Returns None if stop_event is set while backing off, otherwise
        either returns fn()'s result or raises.
        """
        delay = BACKOFF_INITIAL_S
        while not self.stop_event.is_set():
            try:
                return fn()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (401, 403):
                    raise AuthError(f"{what}: backend returned {status} (worker token invalid or revoked)") from exc
                if status in RETRYABLE_STATUS_CODES:
                    print(f"{what} failed: HTTP {status}; retrying in {delay:.1f}s")
                    self.stop_event.wait(delay + random.uniform(0, delay * 0.1))
                    delay = min(delay * 2, BACKOFF_MAX_S)
                    continue
                message = f"{what}: backend returned {status}"
                if job_call:
                    raise JobHTTPError(status, message) from exc
                raise
            except (requests.ConnectionError, requests.Timeout) as exc:
                print(f"{what} failed: {exc}; retrying in {delay:.1f}s")
                self.stop_event.wait(delay + random.uniform(0, delay * 0.1))
                delay = min(delay * 2, BACKOFF_MAX_S)
        return None

    def register(self) -> None:
        existing_token = load_token()
        pairing_code = self.config["pairing_code"]

        if existing_token and not pairing_code:
            self.token = existing_token
            print("reusing stored worker token")
            # poll_interval_s / heartbeat_interval_s keep their defaults; the
            # backend does not re-send them outside of /worker/register.
            return

        if not pairing_code:
            print(
                "No stored token and no PAIRING_CODE set. Get a pairing code "
                "from the dashboard and re-run with PAIRING_CODE set.",
                file=sys.stderr,
            )
            sys.exit(1)

        capabilities = {
            "cpu_cores": os.cpu_count() or 1,
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
            "gpu": False,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        }

        def do_register():
            resp = requests.post(
                self._url("/worker/register"),
                json={
                    "pairing_code": pairing_code,
                    "name": os.environ.get("WORKER_NAME", "worker"),
                    "platform": sys.platform,
                    "capabilities": capabilities,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = self._backoff_request(do_register, what="register")
        except AuthError as exc:
            print(f"error: {exc}. Get a new pairing code and re-run.", file=sys.stderr)
            sys.exit(1)
        if data is None:
            return  # stop_event was set during backoff
        self.token = data["worker_token"]  # never printed or logged
        self.worker_id = data["worker_id"]
        self.poll_interval_s = data.get("poll_interval_s", self.poll_interval_s)
        self.heartbeat_interval_s = data.get("heartbeat_interval_s", self.heartbeat_interval_s)
        save_token(self.token)
        print(f"registered worker_id={self.worker_id}")

    def _cpu_ram_pct(self) -> tuple[float, float]:
        try:
            return psutil.cpu_percent(interval=None), psutil.virtual_memory().percent
        except Exception:
            return 0.0, 0.0

    def heartbeat_once(self) -> dict | None:
        cpu_pct, ram_pct = self._cpu_ram_pct()
        with self.running_jobs_lock:
            running_ids = list(self.running_jobs.keys())
        status = "busy" if running_ids else "idle"

        def do_heartbeat():
            resp = requests.post(
                self._url("/worker/heartbeat"),
                json={
                    "status": status,
                    "cpu_pct": cpu_pct,
                    "ram_pct": ram_pct,
                    "running_job_ids": running_ids,
                },
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()

        return self._backoff_request(do_heartbeat, what="heartbeat")

    def heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                data = self.heartbeat_once()
            except AuthError as exc:
                self.auth_error = exc
                self.stop_event.set()
                return
            if data:
                if data.get("stop"):
                    print("backend requested stop")
                    self.stop_event.set()
                    return
                for job_id in data.get("cancel_job_ids", []):
                    # cancel() kills the process group directly; _run_one_job
                    # (running on its own thread) still owns posting the
                    # "cancelled" result once execute() returns, and still
                    # removes the job from running_jobs itself -- this call
                    # does not touch running_jobs, so a job that already
                    # finished between the backend's request and this call
                    # is simply a no-op (cancel() returns False).
                    killed = self.cancel_registry.cancel(job_id)
                    print(f"job_id={job_id} cancel requested by backend (killed={killed})")
            self.stop_event.wait(self.heartbeat_interval_s)

    def claim_job(self) -> dict | None:
        def do_claim():
            resp = requests.get(
                self._url("/worker/jobs/next"),
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 204:
                return "no_job"
            resp.raise_for_status()
            return resp.json()

        result = self._backoff_request(do_claim, what="claim")
        if result == "no_job":
            return None
        return result

    def start_job(self, job_id: str, attempt: int) -> None:
        def do_start():
            resp = requests.post(
                self._url(f"/worker/jobs/{job_id}/start"),
                json={"attempt": attempt},
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()

        self._backoff_request(do_start, what="start", job_call=True)

    def post_logs(self, job_id: str, attempt: int, chunks: list[dict]) -> None:
        if not chunks:
            return

        def do_logs():
            resp = requests.post(
                self._url(f"/worker/jobs/{job_id}/logs"),
                json={"attempt": attempt, "chunks": chunks},
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()

        self._backoff_request(do_logs, what="logs", job_call=True)

    def post_result(self, job_id: str, attempt: int, result: dict) -> None:
        body = dict(result)
        body["attempt"] = attempt

        def do_result():
            resp = requests.post(
                self._url(f"/worker/jobs/{job_id}/result"),
                json=body,
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()

        self._backoff_request(do_result, what="result", job_call=True)

    def _run_one_job(self, job: dict) -> None:
        job_id = job["job_id"]
        attempt = job["attempt"]

        with self.running_jobs_lock:
            self.running_jobs[job_id] = {"attempt": attempt}

        def on_log(chunks: list[dict]) -> None:
            # runner.py assigns its own sequence numbers across stdout+stderr;
            # forward chunks to the backend as they're produced.
            self.post_logs(job_id, attempt, chunks)

        try:
            try:
                self.start_job(job_id, attempt)
                result = run_job(job, self.workspace_root, on_log=on_log, cancel_registry=self.cancel_registry)

                if self.stop_event.is_set() and job_id in self.running_jobs:
                    # Shutting down while this job was still considered running:
                    # report cancelled instead of whatever run_job returned.
                    result = {
                        "status": "cancelled",
                        "exit_code": None,
                        "stdout_tail": "",
                        "stderr_tail": "",
                        "metrics": {},
                        "files": [],
                    }

                self.post_result(job_id, attempt, result)
            except JobHTTPError as exc:
                # A non-retryable 4xx (other than 401/403) on a job-specific
                # call: this one job failed, the worker keeps running. Best
                # effort to still tell the backend (may itself fail the same
                # way, in which case there is nothing more to do).
                print(f"job_id={job_id}: {exc}")
                try:
                    self.post_result(
                        job_id,
                        attempt,
                        {
                            "status": "failed",
                            "exit_code": None,
                            "stdout_tail": "",
                            "stderr_tail": str(exc),
                            "metrics": {},
                            "files": [],
                        },
                    )
                except (JobHTTPError, AuthError):
                    pass
        except AuthError as exc:
            # The token is invalid or revoked: stop the whole worker (D-042)
            # and let main() report it after the poll loop exits.
            self.auth_error = exc
            self.stop_event.set()
        finally:
            with self.running_jobs_lock:
                self.running_jobs.pop(job_id, None)
            with self.active_count_lock:
                self.active_count -= 1

    def poll_loop(self) -> None:
        threads: list[threading.Thread] = []
        while not self.stop_event.is_set():
            with self.active_count_lock:
                has_capacity = self.active_count < self.concurrency
            if not has_capacity:
                self.stop_event.wait(self.poll_interval_s)
                continue

            try:
                job = self.claim_job()
            except AuthError as exc:
                self.auth_error = exc
                self.stop_event.set()
                break
            if job is None:
                self.stop_event.wait(self.poll_interval_s)
                continue

            with self.active_count_lock:
                self.active_count += 1
            print(f"claimed job_id={job['job_id']} type={job['type']}")
            t = threading.Thread(target=self._run_one_job, args=(job,), daemon=True)
            t.start()
            threads.append(t)
            threads = [t for t in threads if t.is_alive()]

        for t in threads:
            t.join(timeout=5)

    def request_shutdown(self, *_args) -> None:
        # Signal handler: only flip the flag here. Network I/O belongs in
        # report_cancelled_jobs, called from the main thread after poll_loop
        # returns, never from inside the signal handler itself.
        self.stop_event.set()

    def report_cancelled_jobs(self) -> None:
        print("shutting down: reporting running jobs as cancelled")
        with self.running_jobs_lock:
            pending = dict(self.running_jobs)
        for job_id, info in pending.items():
            self.post_result(
                job_id,
                info["attempt"],
                {
                    "status": "cancelled",
                    "exit_code": None,
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "metrics": {},
                    "files": [],
                },
            )
            with self.running_jobs_lock:
                self.running_jobs.pop(job_id, None)


def install_signal_handlers(worker: "Worker") -> None:
    """SIGINT and SIGTERM everywhere they exist; SIGBREAK too on Windows
    (sent for Ctrl+Break there, where SIGTERM doesn't exist as a signal a
    process can catch). KeyboardInterrupt is also caught in main() directly,
    since Windows consoles deliver Ctrl+C that way even when a SIGINT
    handler is installed, depending on how the process was started.
    """
    signal.signal(signal.SIGINT, worker.request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, worker.request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, worker.request_shutdown)


def main() -> None:
    config = load_config()
    worker = Worker(config)
    worker.register()
    if worker.token is None:
        return  # stop_event set during backoff before completing registration

    install_signal_handlers(worker)

    heartbeat_thread = threading.Thread(target=worker.heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    try:
        worker.poll_loop()
    except KeyboardInterrupt:
        # Some Windows console configurations deliver Ctrl+C as a raised
        # KeyboardInterrupt rather than (or in addition to) a caught SIGINT;
        # handle both paths the same way.
        worker.request_shutdown()
    worker.report_cancelled_jobs()

    if worker.auth_error is not None:
        print(f"error: {worker.auth_error}. Get a new pairing code and re-run.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
