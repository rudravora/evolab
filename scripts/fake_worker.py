"""Fake worker for exercising the backend's worker protocol (API.md section 9)
without running real jobs. Standard library plus `requests` only.

Usage:
    BACKEND_URL=http://localhost:8000 PAIRING_CODE=ABCD-1234 python scripts/fake_worker.py
    BACKEND_URL=http://localhost:8000 PAIRING_CODE=ABCD-1234 python scripts/fake_worker.py --fail-every 3

Canned results are read from shared/examples/worker/<job type>.json. The worker
token is kept in memory only and is never printed or logged.
"""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "shared" / "examples" / "worker"

HEARTBEAT_INTERVAL_S = 10
POLL_INTERVAL_S = 2
LOG_CHUNK_DELAY_S = 1


def load_canned_result(job_type: str) -> dict:
    path = EXAMPLES_DIR / f"{job_type}.json"
    if not path.exists():
        # python_script jobs running profile_dataset.py use a dedicated example
        # (ARCHITECTURE.md section 5); fall back to the plain python_script canned result.
        path = EXAMPLES_DIR / "python_script.json"
    with open(path) as f:
        return json.load(f)["result"]


class FakeWorker:
    def __init__(self, backend_url: str, pairing_code: str, fail_every: int | None):
        self.backend_url = backend_url.rstrip("/")
        self.pairing_code = pairing_code
        self.fail_every = fail_every
        self.token: str | None = None
        self.worker_id: str | None = None
        self.poll_interval_s = POLL_INTERVAL_S
        self.heartbeat_interval_s = HEARTBEAT_INTERVAL_S
        self.jobs_claimed = 0
        self.stop_event = threading.Event()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def register(self) -> None:
        resp = requests.post(
            f"{self.backend_url}/api/v1/worker/register",
            json={
                "pairing_code": self.pairing_code,
                "name": "fake-worker",
                "platform": sys.platform,
                "capabilities": {
                    "cpu_cores": os.cpu_count() or 1,
                    "ram_gb": 0,
                    "gpu": False,
                    "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["worker_token"]  # kept in memory only, never printed
        self.worker_id = data["worker_id"]
        self.poll_interval_s = data.get("poll_interval_s", POLL_INTERVAL_S)
        self.heartbeat_interval_s = data.get("heartbeat_interval_s", HEARTBEAT_INTERVAL_S)
        print(f"registered worker_id={self.worker_id}")

    def heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                resp = requests.post(
                    f"{self.backend_url}/api/v1/worker/heartbeat",
                    json={"status": "idle", "cpu_pct": 0.0, "ram_pct": 0.0, "running_job_ids": []},
                    headers=self._headers(),
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("stop"):
                    print("backend requested stop")
                    self.stop_event.set()
                    return
                for cancel_job_id in data.get("cancel_job_ids", []):
                    # This fake worker runs jobs synchronously to completion
                    # (see poll_loop/run_job) rather than tracking them as
                    # running, so there is no in-flight job to actually
                    # kill here -- just acknowledge the request for realism.
                    print(f"backend requested cancel for job_id={cancel_job_id} (no-op: fake worker has no long-running jobs)")
            except requests.RequestException as exc:
                print(f"heartbeat failed: {exc}")
            self.stop_event.wait(self.heartbeat_interval_s)

    def claim_job(self) -> dict | None:
        resp = requests.get(
            f"{self.backend_url}/api/v1/worker/jobs/next",
            headers=self._headers(),
            timeout=15,
        )
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()

    def start_job(self, job_id: str, attempt: int) -> None:
        resp = requests.post(
            f"{self.backend_url}/api/v1/worker/jobs/{job_id}/start",
            json={"attempt": attempt},
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()

    def post_logs(self, job_id: str, attempt: int) -> None:
        canned_lines = [
            "starting job",
            "running...",
            "finishing up",
        ]
        for seq, text in enumerate(canned_lines, start=1):
            resp = requests.post(
                f"{self.backend_url}/api/v1/worker/jobs/{job_id}/logs",
                json={"attempt": attempt, "chunks": [{"seq": seq, "stream": "stdout", "text": text}]},
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            time.sleep(LOG_CHUNK_DELAY_S)

    def post_result(self, job_id: str, attempt: int, job_type: str, force_fail: bool) -> None:
        result = dict(load_canned_result(job_type))
        result["attempt"] = attempt
        if force_fail:
            result["status"] = "failed"
            result["exit_code"] = 1
            result["stderr_tail"] = "fake_worker: forced failure (--fail-every)"
        resp = requests.post(
            f"{self.backend_url}/api/v1/worker/jobs/{job_id}/result",
            json=result,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()

    def run_job(self, job: dict) -> None:
        job_id = job["job_id"]
        project_id = job.get("project_id")
        attempt = job["attempt"]
        job_type = job["type"]
        self.jobs_claimed += 1
        force_fail = bool(self.fail_every) and self.jobs_claimed % self.fail_every == 0

        print(f"claimed job_id={job_id} project_id={project_id} type={job_type} attempt={attempt}")
        self.start_job(job_id, attempt)
        self.post_logs(job_id, attempt)
        self.post_result(job_id, attempt, job_type, force_fail)
        print(f"finished job_id={job_id} failed={force_fail}")

    def poll_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.claim_job()
            except requests.RequestException as exc:
                print(f"poll failed: {exc}")
                self.stop_event.wait(self.poll_interval_s)
                continue
            if job is None:
                self.stop_event.wait(self.poll_interval_s)
                continue
            self.run_job(job)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake worker for backend testing")
    parser.add_argument("--fail-every", type=int, default=None, help="Force every Nth claimed job to fail")
    args = parser.parse_args()

    backend_url = os.environ.get("BACKEND_URL")
    pairing_code = os.environ.get("PAIRING_CODE")
    if not backend_url or not pairing_code:
        print("BACKEND_URL and PAIRING_CODE env vars are required", file=sys.stderr)
        sys.exit(1)

    worker = FakeWorker(backend_url, pairing_code, args.fail_every)
    worker.register()

    heartbeat_thread = threading.Thread(target=worker.heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    try:
        worker.poll_loop()
    except KeyboardInterrupt:
        print("stopping fake worker")
        worker.stop_event.set()


if __name__ == "__main__":
    main()
