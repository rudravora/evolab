"""M1: the job pipe end to end over HTTP (dashboard -> fake agent -> worker -> logs -> result),
plus claim atomicity, attempts, approvals, cancel, pause, offline requeue and the SSE stream."""

from datetime import datetime, timedelta, timezone

import pytest

API = "/api/v1"


class WorkerClient:
    def __init__(self, client, token):
        self.c, self.h = client, {"Authorization": f"Bearer {token}"}

    def claim(self):
        return self.c.get(f"{API}/worker/jobs/next", headers=self.h)

    def start(self, job):
        return self.c.post(f"{API}/worker/jobs/{job['job_id']}/start", json={"attempt": job["attempt"]}, headers=self.h)

    def logs(self, job, lines, first_seq=0):
        chunks = [{"seq": first_seq + i, "stream": "stdout", "text": t} for i, t in enumerate(lines)]
        return self.c.post(f"{API}/worker/jobs/{job['job_id']}/logs", json={"attempt": job["attempt"], "chunks": chunks},
                           headers=self.h)

    def result(self, job, status="done", **extra):
        body = {"attempt": job["attempt"], "status": status, "exit_code": 0 if status == "done" else 1, **extra}
        return self.c.post(f"{API}/worker/jobs/{job['job_id']}/result", json=body, headers=self.h)

    def heartbeat(self):
        return self.c.post(f"{API}/worker/heartbeat", json={"status": "busy", "cpu_pct": 10, "ram_pct": 20}, headers=self.h)

    def run_one(self, lines=("ok",), status="done"):
        r = self.claim()
        assert r.status_code == 200, r.text
        job = r.json()
        assert self.start(job).status_code == 200
        assert self.logs(job, list(lines)).status_code == 200
        assert self.result(job, status).status_code == 200
        return job


def pair(client, name="Laptop-1"):
    code = client.post(f"{API}/workers/pairing").json()["pairing_code"]
    r = client.post(f"{API}/worker/register", json={"pairing_code": code, "name": name, "platform": "win32",
                                                     "capabilities": {"cpu_cores": 8, "ram_gb": 16, "gpu": False}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["poll_interval_s"] == 2 and body["heartbeat_interval_s"] == 10
    return WorkerClient(client, body["worker_token"]), body["worker_id"]


def new_run(client, **body):
    r = client.post(f"{API}/projects", json=body or {"goal": "Pipe check?", "inputs": []})
    assert r.status_code == 201, r.text
    return r.json()


def get_job_row(app, job_id):
    from app.models import Job
    with app.state.db.sessionmaker() as s:
        return s.get(Job, job_id)


# --- the gate ------------------------------------------------------------------------------

def test_m1_pipe_end_to_end(authed):
    worker, worker_id = pair(authed)
    created = new_run(authed)
    run_id = created["run_id"]
    assert created["status"] == "running" and created["worker_online"] is True
    assert created["entry_types"] == ["question"]

    write = worker.run_one(["wrote m1/hello.py"])
    assert write["type"] == "write_file" and write["project_id"] == created["project_id"]
    assert write["payload"]["path"] == "m1/hello.py" and write["approved"] is False
    assert authed.get(f"{API}/runs/{run_id}").json()["status"] == "running"

    run = worker.run_one([f"evolab pipe check: step {i}/5" for i in range(1, 6)])
    assert run["type"] == "python_script" and run["payload"]["argv"] == ["python", "m1/hello.py"]
    assert worker.claim().status_code == 204

    assert authed.get(f"{API}/runs/{run_id}").json()["status"] == "done"
    jobs = authed.get(f"{API}/runs/{run_id}/jobs").json()
    assert [j["status"] for j in jobs] == ["done", "done"] and all(j["worker_id"] == worker_id for j in jobs)
    logs = authed.get(f"{API}/jobs/{run['job_id']}/logs").json()
    assert [l["chunk"] for l in logs][-1] == "evolab pipe check: step 5/5"

    types = [e["type"] for e in authed.get(f"{API}/runs/{run_id}/events", params={"limit": 1000}).json()]
    for t in ("run.status", "agent.task", "job.status", "job.log", "worker.status"):
        assert t in types

    # The stream replays everything and closes because the run is done.
    with authed.stream("GET", f"{API}/runs/{run_id}/stream") as s:
        assert s.headers["content-type"].startswith("text/event-stream")
        body = "".join(s.iter_text())
    assert "event: job.log" in body and "evolab pipe check: step 5/5" in body
    assert body.rstrip().endswith('{"status":"done"}')
    last_id = int([l for l in body.splitlines() if l.startswith("id: ")][-1][4:])
    with authed.stream("GET", f"{API}/runs/{run_id}/stream", headers={"Last-Event-ID": str(last_id)}) as s:
        assert "".join(s.iter_text()) == ""


def test_stream_needs_auth_and_known_run(client, authed):
    assert authed.get(f"{API}/runs/run_nope/stream").status_code == 404
    authed.cookies.clear()
    assert authed.get(f"{API}/runs/run_nope/stream").status_code == 401


# --- workers ------------------------------------------------------------------------------

def test_pairing_code_is_single_use_and_checked(authed):
    code = authed.post(f"{API}/workers/pairing").json()
    assert code["command"].startswith("BACKEND_URL=http://localhost:8000 PAIRING_CODE=")
    body = {"pairing_code": code["pairing_code"], "name": "w"}
    assert authed.post(f"{API}/worker/register", json=body).status_code == 200
    assert authed.post(f"{API}/worker/register", json=body).json()["error"]["code"] == "forbidden"
    assert authed.post(f"{API}/worker/register", json={"pairing_code": "ZZZZ-ZZZZ"}).status_code == 403


def test_pairing_needs_dashboard_auth(client):
    assert client.post(f"{API}/workers/pairing").status_code == 401


def test_worker_routes_reject_bad_or_revoked_tokens(authed):
    worker, worker_id = pair(authed)
    assert WorkerClient(authed, "nope").claim().json()["error"]["code"] == "unauthorized"
    assert authed.delete(f"{API}/workers/{worker_id}").status_code == 204
    assert worker.heartbeat().status_code == 401
    assert authed.get(f"{API}/workers").json()[0]["revoked"] is True


def test_claim_is_exclusive_and_attempt_checked(authed):
    w1, _ = pair(authed, "a")
    w2, _ = pair(authed, "b")
    new_run(authed)
    job = w1.claim().json()
    assert w2.claim().status_code == 204                      # only one pending job, already claimed
    assert w2.start(job).status_code == 404                   # not w2's job
    stale = {**job, "attempt": job["attempt"] + 1}
    assert w1.start(stale).json()["error"]["code"] == "conflict"
    assert w1.start(job).status_code == 200
    assert w1.logs(job, ["a", "b"]).status_code == 200
    assert w1.logs(job, ["a", "b"]).status_code == 200        # duplicate seqs ignored
    assert w1.result(job).status_code == 200
    assert w1.result(job).status_code == 200                  # idempotent per job_id + attempt


def test_logs_are_scrubbed(authed, app):
    w, _ = pair(authed)
    new_run(authed)
    job = w.claim().json()
    w.start(job)
    w.logs(job, ["OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456", "Authorization: Bearer abcdefghijklmnop1234"])
    chunks = [l["chunk"] for l in authed.get(f"{API}/jobs/{job['job_id']}/logs").json()]
    assert all("abcdefghijklmnop" not in c for c in chunks)
    assert "[REDACTED]" in chunks[0] and "[REDACTED]" in chunks[1]


# --- run controls ------------------------------------------------------------------------------

def test_cancel_running_job_goes_through_heartbeat(authed):
    w, _ = pair(authed)
    run_id = new_run(authed)["run_id"]
    job = w.claim().json()
    w.start(job)
    assert authed.post(f"{API}/runs/{run_id}/cancel").json()["status"] == "cancelled"
    assert w.heartbeat().json()["cancel_job_ids"] == [job["job_id"]]
    assert w.result(job, "cancelled").status_code == 200
    assert authed.get(f"{API}/jobs/{job['job_id']}").json()["status"] == "cancelled"
    assert w.claim().status_code == 204
    assert authed.post(f"{API}/runs/{run_id}/cancel").json()["error"]["code"] == "invalid_state"


def test_pause_holds_new_work_until_resume(authed):
    w, _ = pair(authed)
    run_id = new_run(authed)["run_id"]
    job = w.claim().json()
    w.start(job)
    assert authed.post(f"{API}/runs/{run_id}/pause").json()["status"] == "paused"
    assert w.result(job).status_code == 200                  # running jobs finish
    assert w.claim().status_code == 204                      # no new job while paused
    assert authed.post(f"{API}/runs/{run_id}/resume").json()["status"] == "running"
    assert w.claim().json()["type"] == "python_script"
    assert authed.post(f"{API}/runs/{run_id}/resume").json()["error"]["code"] == "invalid_state"


def test_failed_job_fails_the_run(authed):
    w, _ = pair(authed)
    run_id = new_run(authed)["run_id"]
    w.run_one(status="failed")
    assert authed.get(f"{API}/runs/{run_id}").json()["status"] == "failed"


# --- approvals ------------------------------------------------------------------------------

def _risky_job(app, run_id):
    from app.jobs import create_job
    from app.models import Run
    with app.state.db.sessionmaker() as s:
        job = create_job(s, s.get(Run, run_id), "pip_install", {"packages": ["pykan==0.2.8"]})
        s.commit()
        return job.id


def _drain(w):
    while w.claim().status_code == 200:
        pass


@pytest.mark.parametrize("decision,final", [("approve", "pending"), ("reject", "cancelled")])
def test_risky_job_waits_for_approval(authed, app, decision, final):
    w, _ = pair(authed)
    run_id = new_run(authed)["run_id"]
    _drain(w)
    job_id = _risky_job(app, run_id)
    assert get_job_row(app, job_id).status == "awaiting_approval"
    pending = authed.get(f"{API}/approvals", params={"status": "pending", "run_id": run_id}).json()
    assert len(pending) == 1 and pending[0]["type"] == "new_package" and pending[0]["payload"]["job_id"] == job_id
    r = authed.post(f"{API}/approvals/{pending[0]['id']}/decide", json={"decision": decision})
    assert r.status_code == 200
    assert get_job_row(app, job_id).status == final
    if decision == "approve":
        claimed = w.claim().json()
        assert claimed["job_id"] == job_id and claimed["approved"] is True
    assert authed.post(f"{API}/approvals/{pending[0]['id']}/decide", json={"decision": "approve"}).status_code == 409


def test_denied_job_is_never_created(app, authed):
    from app.errors import ApiError
    from app.jobs import create_job
    from app.models import Job, Run
    run_id = new_run(authed)["run_id"]
    with app.state.db.sessionmaker() as s:
        with pytest.raises(ApiError) as e:
            create_job(s, s.get(Run, run_id), "shell", {"argv": ["sudo", "ls"], "cwd": "."})
        assert e.value.code == "policy_denied"
        s.rollback()
        assert s.query(Job).filter(Job.type == "shell").count() == 0


# --- sweeper ------------------------------------------------------------------------------

def test_offline_worker_jobs_requeue_then_fail(authed, app):
    from app.sweeper import sweep
    w, _ = pair(authed)
    new_run(authed)
    later = datetime.now(timezone.utc) + timedelta(seconds=40)
    for expected_attempt in (2, 3):
        job = w.claim().json()
        w.start(job)
        with app.state.db.sessionmaker() as s:
            sweep(s, now=later)
        row = get_job_row(app, job["job_id"])
        assert row.status == "pending" and row.attempt == expected_attempt and row.worker_id is None
        w.heartbeat()                                        # worker comes back online
    job = w.claim().json()
    assert job["attempt"] == 3
    with app.state.db.sessionmaker() as s:
        sweep(s, now=later)
    assert get_job_row(app, job["job_id"]).status == "failed"     # max attempt 3 (D-042)


def test_expired_approval_counts_as_rejected(authed, app):
    from app.sweeper import sweep
    w, _ = pair(authed)
    run_id = new_run(authed)["run_id"]
    _drain(w)
    job_id = _risky_job(app, run_id)
    with app.state.db.sessionmaker() as s:
        sweep(s, now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert get_job_row(app, job_id).status == "cancelled"
    assert authed.get(f"{API}/approvals", params={"run_id": run_id}).json()[0]["status"] == "expired"


# --- intake validation ------------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"inputs": []},
    {"goal": "not a question", "inputs": []},
    {"inputs": [{"kind": "paper", "source": "url", "ref": "ftp://x"}]},
    {"inputs": [{"kind": "repo", "source": "text", "ref": "pykan"}]},
])
def test_create_project_validation(authed, body):
    assert authed.post(f"{API}/projects", json=body).json()["error"]["code"] == "validation_error"


def test_example_project(authed):
    created = authed.post(f"{API}/projects", json={"example": True}).json()
    assert created["entry_types"] == ["paper", "question", "repo"]
    project = authed.get(f"{API}/projects/{created['project_id']}").json()
    assert len(project["inputs"]) == 3 and project["latest_run"]["id"] == created["run_id"]
