"""Exploration tree, branch controls, ledger, report and artifacts (API.md section 7)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..executor import set_branch
from ..jobs import TERMINAL, job_event
from ..models import Artifact, Branch, Experiment, Job, Run
from ..security import current_user
from ..stats import run_stats
from ..tools import ledger_rows

router = APIRouter(tags=["experiments"], dependencies=[Depends(current_user)])


def _run(db: Session, run_id: str) -> Run:
    r = db.get(Run, run_id)
    if r is None:
        raise ApiError(404, "not_found", "Run not found")
    return r


@router.get("/runs/{run_id}/tree")
def tree(run_id: str, db: Session = Depends(get_db)) -> dict:
    _run(db, run_id)
    stats = {b["branch_id"]: b for b in run_stats(db, run_id)["branches"]}
    branches = list(db.scalars(select(Branch).where(Branch.run_id == run_id).order_by(Branch.created_at)))
    nodes = {b.id: {"id": b.id, "hypothesis": b.hypothesis, "kind": b.kind, "status": b.status, "decision": b.decision,
                    "decision_reason": b.decision_reason, "priority_score": b.priority_score,
                    "metrics": {k: v.get("mean") for k, v in stats.get(b.id, {}).get("metrics", {}).items()},
                    "seeds": stats.get(b.id, {}).get("seeds", []), "delta_vs_baseline": stats.get(b.id, {}).get("delta_vs_baseline"),
                    "children": []} for b in branches}
    roots = []
    for b in branches:
        (nodes[b.parent_branch_id]["children"] if b.parent_branch_id in nodes else roots).append(nodes[b.id])
    return {"root": roots[0] if len(roots) == 1 else None, "roots": roots}


def _branch(db: Session, branch_id: str) -> Branch:
    b = db.get(Branch, branch_id)
    if b is None:
        raise ApiError(404, "not_found", "Branch not found")
    return b


@router.get("/branches/{branch_id}")
def get_branch(branch_id: str, db: Session = Depends(get_db)) -> dict:
    b = _branch(db, branch_id)
    exps = [{"id": e.id, "seed": e.seed, "status": e.status, "job_id": e.job_id, "metrics": e.metrics_json,
             "config": e.config_json, "cost_s": e.cost_s, "debug_cycles": e.debug_cycles}
            for e in db.scalars(select(Experiment).where(Experiment.branch_id == b.id).order_by(Experiment.seed))]
    return {"id": b.id, "run_id": b.run_id, "parent_branch_id": b.parent_branch_id, "hypothesis": b.hypothesis, "kind": b.kind,
            "status": b.status, "spec": {k: v for k, v in (b.spec_json or {}).items() if not k.startswith("_")},
            "decision": b.decision, "decision_reason": b.decision_reason, "experiments": exps}


def _branch_jobs(db: Session, b: Branch) -> list[Job]:
    ids = [e.job_id for e in db.scalars(select(Experiment).where(Experiment.branch_id == b.id)) if e.job_id]
    return list(db.scalars(select(Job).where(Job.id.in_(ids)))) if ids else []


@router.post("/branches/{branch_id}/pause")
def pause_branch(branch_id: str, db: Session = Depends(get_db)) -> dict:
    """Running experiments finish; pending ones are held until the branch is expanded again."""
    b = _branch(db, branch_id)
    for j in _branch_jobs(db, b):
        if j.status == "pending":
            j.status = "awaiting_approval"
            job_event(db, j)
    b.decision_reason = "paused by the researcher"
    db.commit()
    return get_branch(branch_id, db)


@router.post("/branches/{branch_id}/kill")
def kill_branch(branch_id: str, db: Session = Depends(get_db)) -> dict:
    from ..ids import now_iso
    b = _branch(db, branch_id)
    for j in _branch_jobs(db, b):
        if j.status in ("claimed", "running"):
            j.cancel_requested = True
        elif j.status not in TERMINAL:
            j.status, j.finished_at = "cancelled", now_iso()
            job_event(db, j)
    for e in db.scalars(select(Experiment).where(Experiment.branch_id == b.id, Experiment.status.in_(("queued", "running")))):
        e.status = "cancelled"
    set_branch(db, b, "killed", "pruned", "killed by the researcher", "researcher")
    db.commit()
    return get_branch(branch_id, db)


class ExpandIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/branches/{branch_id}/expand")
def expand_branch(branch_id: str, body: ExpandIn, db: Session = Depends(get_db)) -> dict:
    """Researcher override: resume a paused branch, or run a proposed/pruned one if branches still run in this plan."""
    b = _branch(db, branch_id)
    for j in _branch_jobs(db, b):
        if j.status == "awaiting_approval" and j.risk != "high":
            j.status = "pending"
            job_event(db, j)
    if b.status in ("proposed", "pruned"):
        set_branch(db, b, "queued", "expanded", f"researcher: {body.reason}", "researcher")
    elif b.status in ("done", "expanded"):
        set_branch(db, b, "expanded", "expanded", f"researcher: {body.reason}", "researcher")
    db.commit()
    return get_branch(branch_id, db)


@router.get("/runs/{run_id}/ledger")
def ledger(run_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _run(db, run_id)
    return ledger_rows(db, run_id)


@router.get("/runs/{run_id}/report")
def report(run_id: str, db: Session = Depends(get_db)) -> dict:
    _run(db, run_id)
    art = db.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == "report")
                    .order_by(Artifact.created_at.desc()).limit(1))
    if art is None or not Path(art.path).exists():
        raise ApiError(404, "not_found", "No report yet")
    from ..context import latest_output
    out = latest_output(db, run_id, "write_report") or {}
    return {"artifact_id": art.id, "markdown": Path(art.path).read_text(encoding="utf-8"), "created_at": art.created_at,
            "why_differs": out.get("why_differs", []), "findings": out.get("findings", [])}


@router.get("/runs/{run_id}/artifacts")
def artifacts(run_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _run(db, run_id)
    return [{"id": a.id, "kind": a.kind, "name": Path(a.path).name, "sha256": a.sha256, "size": a.size,
             "created_at": a.created_at} for a in db.scalars(select(Artifact).where(Artifact.run_id == run_id))]


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: str, db: Session = Depends(get_db)):
    a = db.get(Artifact, artifact_id)
    if a is None or not Path(a.path).exists():
        raise ApiError(404, "not_found", "Artifact not found")
    return FileResponse(a.path, filename=Path(a.path).name, media_type="application/octet-stream")
