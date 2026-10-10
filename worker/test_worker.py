"""Smoke test: a stdlib mock backend serves one job and we assert the full
call sequence (register, heartbeat, next, start, logs, result) happens, with
correct idempotent attempt numbers and no token leakage into the recorded log.

Run: python worker/test_worker.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import worker as worker_module  # noqa: E402

CALLS: list[tuple[str, str, dict]] = []
CALLS_LOCK = threading.Lock()
TEST_TOKEN = "test-worker-token-should-never-be-logged"
JOB = {
    "job_id": "job_test_1",
    "attempt": 1,
    "type": "shell",
    "payload": {"argv": ["cat", "greeting.txt"], "cwd": "proj1/code", "env": {}},  # "cat" is auto-allowed by policy.py
    "timeout_s": 60,
    "max_output_bytes": 100000,
}
job_served = {"done": False}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence default stderr logging

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self._read_json()
        with CALLS_LOCK:
            CALLS.append(("POST", self.path, body))

        if self.path == "/api/v1/worker/register":
            assert body["pairing_code"] == "TEST-CODE"
            self._send_json(
                200,
                {
                    "worker_id": "wrk_test",
                    "worker_token": TEST_TOKEN,
                    "poll_interval_s": 1,
                    "heartbeat_interval_s": 1,
                },
            )
            return

        if self.path == "/api/v1/worker/heartbeat":
            self._send_json(200, {"cancel_job_ids": [], "stop": False})
            return

        if self.path == "/api/v1/worker/jobs/job_test_1/start":
            assert body["attempt"] == 1
            self._send_json(200, {})
            return

        if self.path == "/api/v1/worker/jobs/job_test_1/logs":
            assert body["attempt"] == 1
            assert "chunks" in body
            self._send_json(200, {})
            return

        if self.path == "/api/v1/worker/jobs/job_test_1/result":
            assert body["attempt"] == 1
            assert body["status"] in ("done", "failed", "cancelled")
            job_served["done"] = True
            self._send_json(200, {})
            return

        self._send_json(404, {"error": {"code": "not_found", "message": "unknown path"}})

    def do_GET(self):
        with CALLS_LOCK:
            CALLS.append(("GET", self.path, {}))

        if self.path == "/api/v1/worker/jobs/next":
            with CALLS_LOCK:
                already_served = any(
                    c[1] == "/api/v1/worker/jobs/next" for c in CALLS[:-1]
                )
            if already_served:
                self.send_response(204)
                self.end_headers()
                return
            self._send_json(200, JOB)
            return

        self._send_json(404, {"error": {"code": "not_found", "message": "unknown path"}})


def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    tmp_dir = tempfile.mkdtemp()
    workspace_root = os.path.join(tmp_dir, "workspace")
    os.makedirs(os.path.join(workspace_root, "proj1", "code"), exist_ok=True)
    with open(os.path.join(workspace_root, "proj1", "code", "greeting.txt"), "w") as f:
        f.write("hi\n")

    config = {
        "backend_url": f"http://127.0.0.1:{port}",
        "pairing_code": "TEST-CODE",
        "workspace_root": worker_module.Path(workspace_root),
        "max_jobs": 1,
        "concurrency": 1,
    }

    # Ensure no leftover token file from a previous run of this test.
    if worker_module.TOKEN_PATH.exists():
        worker_module.TOKEN_PATH.unlink()

    w = worker_module.Worker(config)
    try:
        w.register()
        assert w.token == TEST_TOKEN

        heartbeat_thread = threading.Thread(target=w.heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        poll_thread = threading.Thread(target=w.poll_loop, daemon=True)
        poll_thread.start()

        deadline = time.time() + 10
        while not job_served["done"] and time.time() < deadline:
            time.sleep(0.1)

        w.stop_event.set()
        poll_thread.join(timeout=5)

        assert job_served["done"], "job result was never posted within the timeout"

        with CALLS_LOCK:
            paths = [c[1] for c in CALLS]

        assert "/api/v1/worker/register" in paths, "register was never called"
        assert "/api/v1/worker/heartbeat" in paths, "heartbeat was never called"
        assert "/api/v1/worker/jobs/next" in paths, "jobs/next was never polled"
        assert "/api/v1/worker/jobs/job_test_1/start" in paths, "start was never called"
        assert "/api/v1/worker/jobs/job_test_1/logs" in paths, "logs were never posted"
        assert "/api/v1/worker/jobs/job_test_1/result" in paths, "result was never posted"

        register_idx = paths.index("/api/v1/worker/register")
        next_idx = paths.index("/api/v1/worker/jobs/next")
        start_idx = paths.index("/api/v1/worker/jobs/job_test_1/start")
        logs_idx = paths.index("/api/v1/worker/jobs/job_test_1/logs")
        result_idx = paths.index("/api/v1/worker/jobs/job_test_1/result")
        assert register_idx < next_idx < start_idx < logs_idx < result_idx, (
            f"call order was wrong: {paths}"
        )

        with CALLS_LOCK:
            raw_dump = json.dumps(CALLS)
        assert TEST_TOKEN not in raw_dump, "token leaked into a request body"

        print("ALL CHECKS PASSED")
        print(f"recorded {len(CALLS)} calls, sequence: {paths}")
    finally:
        server.shutdown()
        if worker_module.TOKEN_PATH.exists():
            worker_module.TOKEN_PATH.unlink()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
