"""Worker process: registers with the backend, heartbeats, pulls and runs jobs.

API.md section 9 is the contract. ARCHITECTURE.md sections 3.1 (pairing),
3.2 (job lifecycle) and 6 (safety) govern behaviour.

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

import requests

try:
    import psutil
except ImportError:
    psutil = None

TOKEN_PATH = Path(__file__).resolve().parent / ".worker_token"
API_PREFIX = "/api/v1"

BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 60.0
LOG_FLUSH_INTERVAL_S = 1.0


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
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass  # best-effort; not all filesystems support chmod (e.g. some Windows setups)


def load_token() -> str | None:
    if not TOKEN_PATH.exists():
        return None
    return TOKEN_PATH.read_text().strip() or None


class JailViolation(Exception):
    pass


def resolve_job_cwd(workspace_root: Path, cwd: str) -> Path:
    """Reject absolute paths and '..' segments; resolve inside workspace_root.

    API.md's jobs/next example shows `cwd` as a path like "runs/<project>/code"
    with no separate project_id field in the job payload (see docs notes below
    for the assumption this implies). The whole cwd is jailed under
    WORKSPACE_ROOT.
    """
    if not cwd:
        raise JailViolation("cwd is required")
    if Path(cwd).is_absolute():
        raise JailViolation(f"cwd must be relative: {cwd!r}")
    if ".." in Path(cwd).parts:
        raise JailViolation(f"cwd must not contain '..': {cwd!r}")
    resolved = (workspace_root / cwd).resolve()
    try:
        resolved.relative_to(workspace_root.resolve())
    except ValueError:
        raise JailViolation(f"cwd escapes workspace root: {cwd!r}")
    return resolved


def run_job(job: dict, workspace_root: Path) -> dict:
    """Stub runner: validates the jail, returns a canned success result.

    The real command runner and policy modules fill this in later. For now
    this proves the pull loop end to end and enforces the jail rule.
    """
    payload = job.get("payload", {})
    cwd = payload.get("cwd")
    if cwd is not None:
        resolve_job_cwd(workspace_root, cwd)  # raises JailViolation on violation
    return {
        "status": "done",
        "exit_code": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "metrics": {},
        "files": [],
    }


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

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _url(self, path: str) -> str:
        return f"{self.backend_url}{API_PREFIX}{path}"

    def _backoff_request(self, fn, *, what: str):
        """Call fn() with exponential backoff on connection errors. Never raises;
        returns None if stop_event is set while backing off."""
        delay = BACKOFF_INITIAL_S
        while not self.stop_event.is_set():
            try:
                return fn()
            except requests.RequestException as exc:
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
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1) if psutil else 0,
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

        data = self._backoff_request(do_register, what="register")
        if data is None:
            return  # stop_event was set during backoff
        self.token = data["worker_token"]  # never printed or logged
        self.worker_id = data["worker_id"]
        self.poll_interval_s = data.get("poll_interval_s", self.poll_interval_s)
        self.heartbeat_interval_s = data.get("heartbeat_interval_s", self.heartbeat_interval_s)
        save_token(self.token)
        print(f"registered worker_id={self.worker_id}")

    def _cpu_ram_pct(self) -> tuple[float, float]:
        if psutil is None:
            return 0.0, 0.0
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
            data = self.heartbeat_once()
            if data:
                if data.get("stop"):
                    print("backend requested stop")
                    self.stop_event.set()
                    return
                for job_id in data.get("cancel_job_ids", []):
                    with self.running_jobs_lock:
                        self.running_jobs.pop(job_id, None)
                    print(f"job_id={job_id} marked for cancellation by backend")
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

        self._backoff_request(do_start, what="start")

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

        self._backoff_request(do_logs, what="logs")

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

        self._backoff_request(do_result, what="result")

    def _run_one_job(self, job: dict) -> None:
        job_id = job["job_id"]
        attempt = job["attempt"]

        with self.running_jobs_lock:
            self.running_jobs[job_id] = {"attempt": attempt}

        self.start_job(job_id, attempt)

        seq = [0]

        def make_chunk(stream: str, text: str) -> dict:
            seq[0] += 1
            return {"seq": seq[0], "stream": stream, "text": text}

        try:
            try:
                result = run_job(job, self.workspace_root)
                self.post_logs(job_id, attempt, [make_chunk("stdout", "job completed")])
            except JailViolation as exc:
                result = {
                    "status": "failed",
                    "exit_code": 1,
                    "stdout_tail": "",
                    "stderr_tail": f"policy_denied: {exc}",
                    "metrics": {},
                    "files": [],
                }
                self.post_logs(job_id, attempt, [make_chunk("stderr", str(exc))])

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

            job = self.claim_job()
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


def main() -> None:
    config = load_config()
    worker = Worker(config)
    worker.register()
    if worker.token is None:
        return  # stop_event set during backoff before completing registration

    signal.signal(signal.SIGINT, worker.request_shutdown)
    signal.signal(signal.SIGTERM, worker.request_shutdown)

    heartbeat_thread = threading.Thread(target=worker.heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    worker.poll_loop()
    worker.report_cancelled_jobs()


if __name__ == "__main__":
    main()
