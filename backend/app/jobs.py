"""Job creation and lifecycle (ARCHITECTURE sections 3.2 and 5).

create_job() is the only way anything reaches a worker. It runs the policy:
denied jobs are never created, risky ones wait for an approval, the rest are
claimable at once. finish_job() records a terminal status and hands the job
back to whatever created it (the M1 fake agent now, the agent loop in M2).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import policy
from .errors import ApiError
from .events import emit
from .ids import new_id, now_iso
from .models import Approval, Job, Run

TERMINAL = {"done", "failed", "timed_out", "cancelled"}
MAX_ATTEMPT = 3                 # attempt 1 plus at most 2 requeues (D-042)
APPROVAL_TTL = timedelta(minutes=30)


def job_event(db: Session, job: Job) -> None:
    emit(db, job.run_id, "executor", "job.status", {"job_id": job.id, "status": job.status, "worker_id": job.worker_id})


def create_job(db: Session, run: Run, job_type: str, payload: dict, *, task_id: str | None = None,
               timeout_s: int = 900, max_output_bytes: int = 5_000_000, actor: str = "executor") -> Job:
    verdict = policy.classify(job_type, payload, timeout_s)
    if verdict.kind == "deny":
        emit(db, run.id, actor, "job.denied", {"type": job_type, "reason": verdict.reason, "task_id": task_id})
        raise ApiError(403, "policy_denied", verdict.reason)

    job = Job(id=new_id("job"), run_id=run.id, project_id=run.project_id, task_id=task_id, type=job_type,
              payload_json=payload, timeout_s=timeout_s, max_output_bytes=max_output_bytes,
              policy_reason=verdict.reason)
    if verdict.kind == "approval":
        job.risk, job.status = "high", "awaiting_approval"
    db.add(job)
    db.flush()
    job_event(db, job)

    if verdict.kind == "approval":
        expires = (datetime.now(timezone.utc) + APPROVAL_TTL).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        approval = Approval(id=new_id("apr"), run_id=run.id, type=verdict.approval_type,
                            payload_json={"summary": f"{job_type}: {verdict.reason}", "job_id": job.id,
                                          "job_type": job_type, "payload": payload, "reason": verdict.reason,
                                          "risk": "high"},
                            requested_by=actor, expires_at=expires)
        db.add(approval)
        db.flush()
        emit(db, run.id, actor, "approval.requested",
             {"approval_id": approval.id, "type": approval.type, "summary": approval.payload_json["summary"]})
    return job


# Set by the app at startup: hands a finished job back to whatever created it
# (agent loop, Executor, or the M1 pipe check). Kept as a hook so this module has no
# import cycle with the orchestrator.
on_finished = None


def finish_job(db: Session, job: Job, status: str, *, exit_code: int | None = None, stdout_tail: str | None = None,
               stderr_tail: str | None = None, metrics: dict | None = None, files: list | None = None) -> None:
    job.status = status
    job.finished_at = now_iso()
    job.exit_code = exit_code
    if stdout_tail is not None:
        job.stdout_tail = stdout_tail
    if stderr_tail is not None:
        job.stderr_tail = stderr_tail
    job.metrics_json = metrics or {}
    job.files_json = files or []
    job_event(db, job)
    db.flush()
    if on_finished is not None:
        on_finished(db, job)
    else:
        from . import fake_agent
        fake_agent.on_job_finished(db, job)


def requeue_or_fail(db: Session, job: Job, reason: str) -> None:
    """A job lost with its worker goes back to pending (attempt + 1), at most twice."""
    if job.attempt < MAX_ATTEMPT and not job.cancel_requested:
        job.status, job.worker_id, job.attempt = "pending", None, job.attempt + 1
        job.claimed_at = job.started_at = None
        emit(db, job.run_id, "executor", "job.requeued", {"job_id": job.id, "attempt": job.attempt, "reason": reason})
        job_event(db, job)
    else:
        finish_job(db, job, "cancelled" if job.cancel_requested else "failed", stderr_tail=reason)


def cancel_run_jobs(db: Session, run: Run) -> None:
    for job in db.scalars(select(Job).where(Job.run_id == run.id, Job.status.not_in(TERMINAL))):
        if job.status in ("claimed", "running"):
            job.cancel_requested = True           # worker learns it from the next heartbeat
        else:
            job.status, job.finished_at = "cancelled", now_iso()
            job_event(db, job)
