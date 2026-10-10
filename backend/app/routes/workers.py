"""Worker pairing and the worker-facing job API (API.md section 9, ARCHITECTURE 3.1-3.2, D-042)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..deps import get_db
from ..errors import ApiError
from ..events import emit
from ..ids import new_id, now_iso
from ..jobs import TERMINAL, finish_job, job_event, requeue_or_fail
from ..models import Job, JobLog, Run, Worker, WorkerPairing
from ..scrub import scrub
from ..security import OWNER_ID, RateLimiter, current_user

dashboard = APIRouter(tags=["workers"], dependencies=[Depends(current_user)])
worker_api = APIRouter(prefix="/worker", tags=["worker"])

PAIRING_TTL = timedelta(minutes=10)
POLL_INTERVAL_S = 2
HEARTBEAT_INTERVAL_S = 10
MAX_CHUNK_CHARS = 65_536
TAIL_CHARS = 20_000
log_limiter = RateLimiter(10, 1.0, "Too many log uploads")
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --- dashboard ------------------------------------------------------------------

class PairingOut(BaseModel):
    pairing_code: str
    expires_at: str
    command: str


class WorkerOut(BaseModel):
    id: str
    name: str
    status: str
    platform: str | None
    last_heartbeat: str | None
    cpu_pct: float | None
    ram_pct: float | None
    capabilities: dict | None
    revoked: bool


@dashboard.post("/workers/pairing", response_model=PairingOut, status_code=201)
def create_pairing(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> PairingOut:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    code = f"{raw[:4]}-{raw[4:]}"
    expires = _iso(datetime.now(timezone.utc) + PAIRING_TTL)
    db.add(WorkerPairing(id=new_id("pair"), owner_id=OWNER_ID, code_hash=sha256(code), expires_at=expires))
    db.commit()
    command = f"BACKEND_URL={settings.public_base_url} PAIRING_CODE={code} python worker.py"
    return PairingOut(pairing_code=code, expires_at=expires, command=command)


def _worker_out(w: Worker) -> WorkerOut:
    return WorkerOut(id=w.id, name=w.name, status=w.status, platform=w.platform, last_heartbeat=w.last_heartbeat,
                     cpu_pct=w.cpu_pct, ram_pct=w.ram_pct, capabilities=w.capabilities_json,
                     revoked=w.token_hash is None)


@dashboard.get("/workers", response_model=list[WorkerOut])
def list_workers(db: Session = Depends(get_db)) -> list[WorkerOut]:
    return [_worker_out(w) for w in db.scalars(select(Worker).order_by(Worker.created_at))]


@dashboard.delete("/workers/{worker_id}", status_code=204)
def revoke_worker(worker_id: str, db: Session = Depends(get_db)) -> Response:
    w = db.get(Worker, worker_id)
    if w is None:
        raise ApiError(404, "not_found", "Worker not found")
    w.token_hash, w.status = None, "offline"
    emit(db, None, "dashboard", "worker.status", {"worker_id": w.id, "status": "offline", "revoked": True})
    for job in db.scalars(select(Job).where(Job.worker_id == w.id, Job.status.in_(("claimed", "running")))):
        requeue_or_fail(db, job, "worker revoked")
    db.commit()
    return Response(status_code=204)


# --- worker auth ------------------------------------------------------------------

def current_worker(request: Request, db: Session = Depends(get_db)) -> Worker:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    worker = db.scalar(select(Worker).where(Worker.token_hash == sha256(token))) if token else None
    if worker is None:
        raise ApiError(401, "unauthorized", "Unknown or revoked worker token; pair again with a new code")
    return worker


def _own_job(db: Session, worker: Worker, job_id: str, attempt: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.worker_id != worker.id:
        raise ApiError(404, "not_found", "Job not found for this worker")
    if attempt != job.attempt:
        raise ApiError(409, "conflict", f"Stale attempt {attempt}; current attempt is {job.attempt}")
    return job


# --- worker endpoints ------------------------------------------------------------------

class Capabilities(BaseModel):
    cpu_cores: int | None = None
    ram_gb: float | None = None
    gpu: bool | None = None
    python: str | None = None


class RegisterIn(BaseModel):
    pairing_code: str = Field(min_length=4, max_length=32)
    name: str = Field(default="worker", min_length=1, max_length=100)
    platform: str | None = Field(default=None, max_length=64)
    capabilities: Capabilities = Capabilities()


class RegisterOut(BaseModel):
    worker_id: str
    worker_token: str
    poll_interval_s: int
    heartbeat_interval_s: int


@worker_api.post("/register", response_model=RegisterOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> RegisterOut:
    pairing = db.scalar(select(WorkerPairing).where(WorkerPairing.code_hash == sha256(body.pairing_code.strip().upper())))
    if pairing is None or pairing.used_at is not None or pairing.expires_at <= now_iso():
        raise ApiError(403, "forbidden", "Invalid, used or expired pairing code")
    token = secrets.token_urlsafe(32)
    w = Worker(id=new_id("wrk"), owner_id=pairing.owner_id, name=body.name, token_hash=sha256(token),
               status="online", platform=body.platform, last_heartbeat=now_iso(),
               capabilities_json=body.capabilities.model_dump())
    db.add(w)
    db.flush()
    pairing.used_at, pairing.worker_id = now_iso(), w.id
    emit(db, None, "worker", "worker.status", {"worker_id": w.id, "status": "online", "cpu_pct": None, "ram_pct": None})
    db.commit()
    return RegisterOut(worker_id=w.id, worker_token=token, poll_interval_s=POLL_INTERVAL_S,
                       heartbeat_interval_s=HEARTBEAT_INTERVAL_S)


class HeartbeatIn(BaseModel):
    status: Literal["idle", "busy"] = "idle"
    cpu_pct: float | None = Field(default=None, ge=0, le=100)
    ram_pct: float | None = Field(default=None, ge=0, le=100)
    running_job_ids: list[str] = []


class HeartbeatOut(BaseModel):
    cancel_job_ids: list[str]
    stop: bool


@worker_api.post("/heartbeat", response_model=HeartbeatOut)
def heartbeat(body: HeartbeatIn, worker: Worker = Depends(current_worker), db: Session = Depends(get_db)) -> HeartbeatOut:
    was_offline = worker.status != "online"
    worker.status, worker.last_heartbeat = "online", now_iso()
    worker.cpu_pct, worker.ram_pct = body.cpu_pct, body.ram_pct
    if was_offline:
        emit(db, None, "worker", "worker.status",
             {"worker_id": worker.id, "status": "online", "cpu_pct": body.cpu_pct, "ram_pct": body.ram_pct})
    cancel = db.scalars(select(Job.id).where(Job.worker_id == worker.id, Job.cancel_requested.is_(True),
                                             Job.status.in_(("claimed", "running")))).all()
    db.commit()
    return HeartbeatOut(cancel_job_ids=list(cancel), stop=False)


class ClaimOut(BaseModel):
    job_id: str
    project_id: str
    attempt: int
    type: str
    payload: dict
    approved: bool
    timeout_s: int
    max_output_bytes: int


@worker_api.get("/jobs/next", response_model=ClaimOut, responses={204: {"description": "No job available"}})
def claim_next(worker: Worker = Depends(current_worker), db: Session = Depends(get_db)):
    """Atomic claim: one UPDATE ... WHERE status='pending' RETURNING, so two workers never get the same job.
    Jobs of paused, cancelled or finished runs are not handed out."""
    worker.status, worker.last_heartbeat = "online", now_iso()
    candidate = (select(Job.id).join(Run, Run.id == Job.run_id)
                 .where(Job.status == "pending", Run.status == "running")
                 .order_by(Job.created_at, Job.id).limit(1).scalar_subquery())
    job_id = db.scalar(update(Job).where(Job.id == candidate, Job.status == "pending")
                       .values(status="claimed", worker_id=worker.id, claimed_at=now_iso())
                       .returning(Job.id))
    if job_id is None:
        db.commit()
        return Response(status_code=204)
    job = db.get(Job, job_id)
    db.refresh(job)
    job_event(db, job)
    db.commit()
    return ClaimOut(job_id=job.id, project_id=job.project_id, attempt=job.attempt, type=job.type,
                    payload=job.payload_json, approved=job.approved, timeout_s=job.timeout_s,
                    max_output_bytes=job.max_output_bytes)


class AttemptIn(BaseModel):
    attempt: int = Field(ge=1)


class Ok(BaseModel):
    ok: bool = True


@worker_api.post("/jobs/{job_id}/start", response_model=Ok)
def start_job(job_id: str, body: AttemptIn, worker: Worker = Depends(current_worker), db: Session = Depends(get_db)) -> Ok:
    job = _own_job(db, worker, job_id, body.attempt)
    if job.status == "claimed":
        job.status, job.started_at = "running", now_iso()
        job_event(db, job)
    elif job.status != "running":
        raise ApiError(409, "invalid_state", f"Job is {job.status}")
    db.commit()
    return Ok()


class LogChunk(BaseModel):
    seq: int = Field(ge=0)
    stream: Literal["stdout", "stderr"]
    text: str


class LogsIn(BaseModel):
    attempt: int = Field(ge=1)
    chunks: list[LogChunk] = Field(max_length=500)


@worker_api.post("/jobs/{job_id}/logs", response_model=Ok)
def post_logs(job_id: str, body: LogsIn, worker: Worker = Depends(current_worker), db: Session = Depends(get_db)) -> Ok:
    log_limiter.check(worker.id)
    job = _own_job(db, worker, job_id, body.attempt)
    if job.status in TERMINAL:
        raise ApiError(409, "invalid_state", f"Job is {job.status}")
    seen = set(db.scalars(select(JobLog.seq).where(JobLog.job_id == job.id, JobLog.attempt == job.attempt)))
    for chunk in body.chunks:
        if chunk.seq in seen:
            continue                                   # idempotent retries
        seen.add(chunk.seq)
        text = scrub(chunk.text[:MAX_CHUNK_CHARS])
        db.add(JobLog(id=new_id("log"), job_id=job.id, attempt=job.attempt, seq=chunk.seq, stream=chunk.stream, chunk=text))
        emit(db, job.run_id, "worker", "job.log", {"job_id": job.id, "seq": chunk.seq, "stream": chunk.stream, "chunk": text})
    db.commit()
    return Ok()


class FileRef(BaseModel):
    path: str
    sha256: str | None = None


class ResultIn(BaseModel):
    attempt: int = Field(ge=1)
    status: Literal["done", "failed", "timed_out", "cancelled"]
    exit_code: int | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None
    metrics: dict = {}
    files: list[FileRef] = []


@worker_api.post("/jobs/{job_id}/result", response_model=Ok)
def post_result(job_id: str, body: ResultIn, worker: Worker = Depends(current_worker), db: Session = Depends(get_db)) -> Ok:
    job = _own_job(db, worker, job_id, body.attempt)
    if job.status in TERMINAL:
        return Ok()                                    # idempotent per job_id + attempt
    finish_job(db, job, body.status, exit_code=body.exit_code,
               stdout_tail=scrub((body.stdout_tail or "")[-TAIL_CHARS:]),
               stderr_tail=scrub((body.stderr_tail or "")[-TAIL_CHARS:]),
               metrics=body.metrics, files=[f.model_dump() for f in body.files])
    db.commit()
    return Ok()
