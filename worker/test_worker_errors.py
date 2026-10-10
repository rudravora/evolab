"""Tests for worker.py's HTTP error handling (connection errors/429/5xx
retry with backoff; 401/403 stop and exit; other 4xx on a job call fails
just that job) and the Windows platform guard.

Run: python worker/test_worker_errors.py
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

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def make_worker(port: int, workspace_root, *, max_jobs: int = 1) -> "worker_module.Worker":
    config = {
        "backend_url": f"http://127.0.0.1:{port}",
        "pairing_code": "TEST-CODE",
        "workspace_root": workspace_root,
        "max_jobs": max_jobs,
        "concurrency": max_jobs,
    }
    if worker_module.TOKEN_PATH.exists():
        worker_module.TOKEN_PATH.unlink()
    return worker_module.Worker(config)


class ScriptedHandler(BaseHTTPRequestHandler):
    """Serves responses from a shared, mutable script: SCRIPT[path] is
    either a fixed response dict, or a list of responses consumed in order
    (one per request to that path), so a test can simulate "fails twice
    then succeeds" or "every request to this path returns 401" etc.
    """

    def log_message(self, fmt, *args):
        pass

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _respond(self, status: int, body: dict | None) -> None:
        data = json.dumps(body or {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self):
        self._read_json()
        script = self.server.script  # type: ignore[attr-defined]
        entry = script.get(self.path)
        if entry is None:
            self._respond(404, {"error": {"code": "not_found", "message": "unscripted path"}})
            return
        if isinstance(entry, list):
            response = entry.pop(0) if entry else entry_default_204()
        else:
            response = entry
        status, body = response
        if status == 204:
            self.send_response(204)
            self.end_headers()
            return
        self._respond(status, body)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()


def entry_default_204():
    return (204, None)


def start_server(script: dict):
    server = HTTPServer(("127.0.0.1", 0), ScriptedHandler)
    server.script = script
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


# ---------------------------------------------------------------------------
# 1. 401 on heartbeat: worker stops, records auth_error, never retries forever
# ---------------------------------------------------------------------------

def test_401_on_heartbeat_stops_worker() -> None:
    script = {
        "/api/v1/worker/register": (200, {"worker_id": "wrk_x", "worker_token": "tok", "poll_interval_s": 1, "heartbeat_interval_s": 1}),
        "/api/v1/worker/heartbeat": (401, {"error": {"code": "unauthorized", "message": "bad token"}}),
        "/api/v1/worker/jobs/next": (204, None),
    }
    server, port = start_server(script)
    tmp = tempfile.mkdtemp()
    try:
        w = make_worker(port, worker_module.Path(tmp))
        w.register()
        check("auth_401_heartbeat.registered", w.token == "tok", w.token)

        start = time.monotonic()
        w.heartbeat_loop()  # not threaded: call directly and expect it to return promptly
        elapsed = time.monotonic() - start

        check("auth_401_heartbeat.stop_event_set", w.stop_event.is_set(), "stop_event should be set after a 401")
        check("auth_401_heartbeat.auth_error_recorded", isinstance(w.auth_error, worker_module.AuthError), w.auth_error)
        check("auth_401_heartbeat.returned_promptly", elapsed < 5, f"heartbeat_loop took {elapsed:.1f}s, expected it to stop immediately on 401, not retry")
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        if worker_module.TOKEN_PATH.exists():
            worker_module.TOKEN_PATH.unlink()


# ---------------------------------------------------------------------------
# 2. 403 on claim_job: same stop-immediately behaviour
# ---------------------------------------------------------------------------

def test_403_on_claim_raises_autherror() -> None:
    script = {
        "/api/v1/worker/register": (200, {"worker_id": "wrk_x", "worker_token": "tok", "poll_interval_s": 1, "heartbeat_interval_s": 1}),
        "/api/v1/worker/jobs/next": (403, {"error": {"code": "forbidden", "message": "revoked"}}),
    }
    server, port = start_server(script)
    tmp = tempfile.mkdtemp()
    try:
        w = make_worker(port, worker_module.Path(tmp))
        w.register()

        raised = False
        try:
            w.claim_job()
        except worker_module.AuthError:
            raised = True
        check("auth_403_claim.raised_autherror", raised, "claim_job should raise AuthError on 403")
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        if worker_module.TOKEN_PATH.exists():
            worker_module.TOKEN_PATH.unlink()


# ---------------------------------------------------------------------------
# 3. Connection error then success: retries with backoff, eventually succeeds
# ---------------------------------------------------------------------------

def test_connection_refused_then_recovers() -> None:
    """Point the worker at a port nobody is listening on yet, then start the
    real server shortly after -- _backoff_request must retry through the
    connection-refused errors and succeed once the server comes up."""
    import socket

    # Find a free port, but don't bind it yet.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    script = {
        "/api/v1/worker/register": (200, {"worker_id": "wrk_x", "worker_token": "tok", "poll_interval_s": 1, "heartbeat_interval_s": 1}),
    }

    tmp = tempfile.mkdtemp()
    server_holder = {}

    def start_late():
        time.sleep(1.5)
        server, actual_port = start_server(script)
        server_holder["server"] = server
        # The HTTPServer we just created may not land on the same free port
        # (another process could grab it in the gap), so this test accepts
        # that rare flake rather than engineering around it.

    try:
        w = make_worker(port, worker_module.Path(tmp))
        # Patch the worker's backend_url after the fact is not needed since
        # we pre-selected the port above and will bind the real server to
        # that exact port using SO_REUSEADDR semantics via HTTPServer.
        t = threading.Thread(target=_bind_server_to_port, args=(script, port, server_holder), daemon=True)
        t.start()

        start = time.monotonic()
        w.register()
        elapsed = time.monotonic() - start

        check("connection_refused.eventually_registered", w.token == "tok", w.token)
        check("connection_refused.took_some_backoff_time", elapsed >= 0.8, f"registered in {elapsed:.2f}s, expected at least one backoff wait")
    finally:
        if "server" in server_holder:
            server_holder["server"].shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        if worker_module.TOKEN_PATH.exists():
            worker_module.TOKEN_PATH.unlink()


def _bind_server_to_port(script: dict, port: int, holder: dict) -> None:
    time.sleep(1.0)
    server = HTTPServer(("127.0.0.1", port), ScriptedHandler)
    server.script = script
    holder["server"] = server
    server.serve_forever()


# ---------------------------------------------------------------------------
# 4. Other 4xx (422) on a job call: that job fails, worker keeps running
# ---------------------------------------------------------------------------

def test_422_on_job_result_fails_job_not_worker() -> None:
    job = {
        "job_id": "job_422",
        "project_id": "proj1",
        "attempt": 1,
        "type": "shell",
        "payload": {"argv": ["cat", "greeting.txt"], "cwd": "code", "env": {}},
        "approved": False,
        "timeout_s": 10,
        "max_output_bytes": 10000,
    }
    script = {
        "/api/v1/worker/register": (200, {"worker_id": "wrk_x", "worker_token": "tok", "poll_interval_s": 1, "heartbeat_interval_s": 1}),
        "/api/v1/worker/heartbeat": (200, {"cancel_job_ids": [], "stop": False}),
        "/api/v1/worker/jobs/next": [(200, job), (204, None)],
        "/api/v1/worker/jobs/job_422/start": (200, {}),
        "/api/v1/worker/jobs/job_422/logs": (200, {}),
        "/api/v1/worker/jobs/job_422/result": (422, {"error": {"code": "validation_error", "message": "bad attempt"}}),
    }
    server, port = start_server(script)
    tmp = tempfile.mkdtemp()
    try:
        workspace_root = os.path.join(tmp, "workspace")
        os.makedirs(os.path.join(workspace_root, "proj1", "code"), exist_ok=True)
        with open(os.path.join(workspace_root, "proj1", "code", "greeting.txt"), "w") as f:
            f.write("hi\n")

        w = make_worker(port, worker_module.Path(workspace_root))
        w.register()

        start = time.monotonic()
        w._run_one_job(job)
        elapsed = time.monotonic() - start

        check("job_422.did_not_retry_forever", elapsed < 5, f"took {elapsed:.1f}s, expected a fast non-retried failure")
        check("job_422.worker_not_stopped", not w.stop_event.is_set(), "a 422 on one job's result must not stop the whole worker")
        check("job_422.auth_error_not_set", w.auth_error is None, w.auth_error)
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        if worker_module.TOKEN_PATH.exists():
            worker_module.TOKEN_PATH.unlink()


# ---------------------------------------------------------------------------
# 5. 500 retries with backoff, then a later success is picked up
# ---------------------------------------------------------------------------

def test_5xx_retries_then_succeeds() -> None:
    script = {
        "/api/v1/worker/register": [
            (500, {"error": {"code": "internal_error", "message": "try again"}}),
            (500, {"error": {"code": "internal_error", "message": "try again"}}),
            (200, {"worker_id": "wrk_x", "worker_token": "tok", "poll_interval_s": 1, "heartbeat_interval_s": 1}),
        ],
    }
    server, port = start_server(script)
    tmp = tempfile.mkdtemp()
    try:
        w = make_worker(port, worker_module.Path(tmp))
        start = time.monotonic()
        w.register()
        elapsed = time.monotonic() - start
        check("5xx_retry.eventually_succeeded", w.token == "tok", w.token)
        check("5xx_retry.backoff_happened", elapsed >= 1.5, f"took {elapsed:.2f}s, expected at least two backoff waits (1s + 2s)")
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        if worker_module.TOKEN_PATH.exists():
            worker_module.TOKEN_PATH.unlink()


# ---------------------------------------------------------------------------
# 6. Platform guard: simulated Windows exits with the exact message
# ---------------------------------------------------------------------------

def test_platform_guard_exits_on_windows() -> None:
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        exited = False
        message = None
        try:
            import io
            captured = io.StringIO()
            old_stderr = sys.stderr
            sys.stderr = captured
            try:
                worker_module.check_platform()
            finally:
                sys.stderr = old_stderr
            message = captured.getvalue()
        except SystemExit as exc:
            exited = True
            check("platform_guard.exit_code_nonzero", exc.code != 0, exc.code)
        check("platform_guard.exits", exited, "check_platform() did not call sys.exit on win32")
    finally:
        sys.platform = original_platform


def test_platform_guard_message_exact() -> None:
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        import io

        captured = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured
        try:
            worker_module.check_platform()
        except SystemExit:
            pass
        finally:
            sys.stderr = old_stderr
        message = captured.getvalue().strip()
        check(
            "platform_guard.exact_message",
            message == "Worker supports macOS and Linux only. On Windows use WSL.",
            repr(message),
        )
    finally:
        sys.platform = original_platform


def test_platform_guard_does_not_exit_on_macos_linux() -> None:
    for plat in ("darwin", "linux"):
        original_platform = sys.platform
        try:
            sys.platform = plat
            try:
                worker_module.check_platform()
                check(f"platform_guard.no_exit_on_{plat}", True)
            except SystemExit:
                check(f"platform_guard.no_exit_on_{plat}", False, f"check_platform() exited on {plat!r}")
        finally:
            sys.platform = original_platform


# ---------------------------------------------------------------------------
# 7. Import safety: runner.py must not raise at import time when `resource`
#    is unavailable (simulating Windows).
# ---------------------------------------------------------------------------

def test_runner_import_survives_missing_resource_module() -> None:
    import builtins
    import importlib

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "resource":
            raise ModuleNotFoundError("No module named 'resource'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        import runner as runner_module

        importlib.reload(runner_module)
        check("import_safety.resource_is_none", runner_module.resource is None, runner_module.resource)
    except Exception as exc:
        check("import_safety.reload_did_not_raise", False, f"reloading runner.py without 'resource' raised: {exc}")
    finally:
        builtins.__import__ = real_import
        import runner as runner_module

        importlib.reload(runner_module)  # restore normal state for any later test


def main() -> None:
    tests = [
        test_401_on_heartbeat_stops_worker,
        test_403_on_claim_raises_autherror,
        test_connection_refused_then_recovers,
        test_422_on_job_result_fails_job_not_worker,
        test_5xx_retries_then_succeeds,
        test_platform_guard_exits_on_windows,
        test_platform_guard_message_exact,
        test_platform_guard_does_not_exit_on_macos_linux,
        test_runner_import_survives_missing_resource_module,
    ]
    for t in tests:
        print(f"running {t.__name__} ...")
        t()

    if FAILURES:
        print(f"FAILED {len(FAILURES)} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"ALL CHECKS PASSED ({len(tests)} scenarios)")


if __name__ == "__main__":
    main()
