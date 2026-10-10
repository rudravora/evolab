"""Approvals inbox (API.md section 8). M1 handles job approvals (risky_command, new_package,
expensive_run); plan, evolution and the other types are decided here too once M2-M4 create them."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..events import emit
from ..ids import now_iso
from ..jobs import finish_job, job_event
from ..models import Approval, Job
from ..security import current_user

router = APIRouter(prefix="/approvals", tags=["approvals"], dependencies=[Depends(current_user)])
JOB_APPROVALS = {"risky_command", "new_package", "expensive_run"}


class ApprovalOut(BaseModel):
    id: str
    run_id: str | None
    type: str
    status: str
    payload: dict
    requested_by: str | None
    decided_via: str | None
    comment: str | None
    expires_at: str | None
    decided_at: str | None
    created_at: str


def _out(a: Approval) -> ApprovalOut:
    return ApprovalOut(id=a.id, run_id=a.run_id, type=a.type, status=a.status, payload=a.payload_json,
                       requested_by=a.requested_by, decided_via=a.decided_via, comment=a.comment,
                       expires_at=a.expires_at, decided_at=a.decided_at, created_at=a.created_at)


@router.get("", response_model=list[ApprovalOut])
def list_approvals(status: str | None = None, run_id: str | None = None, db: Session = Depends(get_db)) -> list[ApprovalOut]:
    q = select(Approval).order_by(Approval.created_at.desc())
    if status:
        q = q.where(Approval.status == status)
    if run_id:
        q = q.where(Approval.run_id == run_id)
    return [_out(a) for a in db.scalars(q)]


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: str, db: Session = Depends(get_db)) -> ApprovalOut:
    a = db.get(Approval, approval_id)
    if a is None:
        raise ApiError(404, "not_found", "Approval not found")
    return _out(a)


class DecideIn(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    comment: str | None = Field(default=None, max_length=2000)
    edited_payload: dict | None = None


def apply_decision(db: Session, a: Approval, status: str, via: str, comment: str | None = None) -> None:
    """Shared by the dashboard route, the expiry sweeper and (M5) the n8n hook."""
    a.status, a.decided_via, a.comment, a.decided_at = status, via, comment, now_iso()
    emit(db, a.run_id, via, "approval.decided", {"approval_id": a.id, "status": status})
    if a.type in JOB_APPROVALS:
        job = db.get(Job, a.payload_json.get("job_id"))
        if job is None or job.status != "awaiting_approval":
            return
        if status == "approved":
            job.approved, job.status = True, "pending"
            job_event(db, job)
        else:
            finish_job(db, job, "cancelled", stderr_tail=f"approval {status}: {comment or 'no comment'}")


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
def decide(approval_id: str, body: DecideIn, db: Session = Depends(get_db)) -> ApprovalOut:
    a = db.get(Approval, approval_id)
    if a is None:
        raise ApiError(404, "not_found", "Approval not found")
    if a.status != "pending":
        raise ApiError(409, "invalid_state", f"Approval is already {a.status}")
    if body.decision == "edit":
        # Editing a job means a new job through the policy again; plan edits arrive in M2.
        raise ApiError(409, "invalid_state", f"Edit is not supported for {a.type} approvals yet; approve or reject")
    apply_decision(db, a, "approved" if body.decision == "approve" else "rejected", "dashboard", body.comment)
    db.commit()
    return _out(a)
