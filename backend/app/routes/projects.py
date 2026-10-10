"""Projects, runs and run controls (API.md section 3). Intake facts, the Brief and planning arrive in M2;
in M1 a new run goes straight to the fake agent's pipe check."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import fake_agent, runs
from ..deps import get_db
from ..errors import ApiError
from ..events import emit
from ..ids import new_id
from ..jobs import cancel_run_jobs
from ..models import AgentTask, Approval, Input, Job, Project, Run, Worker
from ..security import OWNER_ID, current_user

router = APIRouter(tags=["projects"], dependencies=[Depends(current_user)])

DEFAULT_BUDGET = {"max_wall_min": 90, "max_tokens": 1_500_000, "max_concurrent_jobs": 3, "max_concurrent_agents": 2,
                  "per_job_timeout_s": 900, "long_run_approval_s": 600}
EXAMPLE_INPUTS = [
    {"kind": "paper", "source": "url", "ref": "https://arxiv.org/abs/2404.19756"},
    {"kind": "repo", "source": "url", "ref": "https://github.com/KindXiaoming/pykan"},
    {"kind": "question", "source": "text", "ref": "Do KANs beat parameter-matched MLPs on real tabular data?"},
]
EXAMPLE_GOAL = "Do KANs beat parameter-matched MLPs on real tabular data?"


class InputIn(BaseModel):
    kind: Literal["paper", "question", "repo", "dataset", "note"]
    source: Literal["url", "text", "worker_path"]   # "upload" goes through POST /projects/{id}/inputs (M2)
    ref: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _check(self):
        if self.source == "url" and not self.ref.lower().startswith(("http://", "https://")):
            raise ValueError("url inputs must be http(s) URLs")
        if self.kind in ("paper", "repo") and self.source not in ("url",):
            raise ValueError(f"{self.kind} inputs must be URLs (uploads come in M2)")
        if self.kind in ("question", "note") and self.source != "text":
            raise ValueError(f"{self.kind} inputs must be text")
        if self.kind == "dataset" and self.source == "text":
            raise ValueError("dataset inputs are a URL or a worker_path")
        return self


class Budget(BaseModel):
    max_wall_min: int = Field(default=90, ge=1, le=24 * 60)
    max_tokens: int = Field(default=1_500_000, ge=1000)


class ProjectIn(BaseModel):
    goal: str | None = Field(default=None, min_length=1, max_length=2000)
    inputs: list[InputIn] = Field(default=[], max_length=20)
    budget: Budget = Budget()
    approval_policy: dict = {}
    example: bool = False


class ProjectCreated(BaseModel):
    project_id: str
    run_id: str
    status: str
    entry_types: list[str]
    worker_online: bool


class RunOut(BaseModel):
    id: str
    project_id: str
    goal: str | None
    status: str
    budget: dict
    usage: dict
    counts: dict
    started_at: str
    ended_at: str | None


class ProjectOut(BaseModel):
    id: str
    name: str
    goal: str | None
    created_at: str
    inputs: list[dict]
    latest_run: RunOut | None


def _worker_online(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(Worker).where(Worker.status == "online",
                                                                    Worker.token_hash.is_not(None))) > 0


def _run_out(db: Session, run: Run) -> RunOut:
    jobs = db.scalar(select(func.count()).select_from(Job).where(Job.run_id == run.id))
    pending = db.scalar(select(func.count()).select_from(Approval).where(Approval.run_id == run.id,
                                                                         Approval.status == "pending"))
    return RunOut(id=run.id, project_id=run.project_id, goal=run.goal, status=run.status,
                  budget=run.budget_json or {}, usage={**(run.usage_json or {}), "jobs": jobs},
                  counts={"pending_approvals": pending}, started_at=run.started_at, ended_at=run.ended_at)


def _get_run(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Run not found")
    return run


def _start_run(db: Session, project: Project, goal: str | None, budget: dict) -> Run:
    entry_types = sorted({i.kind for i in db.scalars(select(Input).where(Input.project_id == project.id))} - {"note"})
    run = Run(id=new_id("run"), project_id=project.id, goal=goal, status="planning", entry_types_json=entry_types,
              budget_json={**DEFAULT_BUDGET, **budget}, usage_json={"wall_min": 0, "tokens": 0})
    db.add(run)
    db.flush()
    emit(db, run.id, "orchestrator", "run.status", {"status": "planning"})
    fake_agent.start(db, run)
    return run


@router.post("/projects", response_model=ProjectCreated, status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db)) -> ProjectCreated:
    inputs = [i.model_dump() for i in body.inputs]
    goal = body.goal
    if body.example:
        inputs, goal = EXAMPLE_INPUTS, EXAMPLE_GOAL
    if not inputs and goal and goal.strip().endswith("?"):
        inputs = [{"kind": "question", "source": "text", "ref": goal}]
    if not inputs:
        raise ApiError(422, "validation_error", "Give at least one input, or a goal that is a question")
    project = Project(id=new_id("proj"), owner_id=OWNER_ID, name=(goal or inputs[0]["ref"])[:200], goal=goal)
    db.add(project)
    db.flush()
    project.workspace_path = project.id            # jail on the worker: WORKSPACE_ROOT/<project_id>/ (D-042)
    for i in inputs:
        db.add(Input(id=new_id("inp"), project_id=project.id, kind=i["kind"], ref=i["ref"], source=i["source"],
                     meta_json={"untrusted": True}))
    db.flush()
    run = _start_run(db, project, goal, body.budget.model_dump())
    db.commit()
    return ProjectCreated(project_id=project.id, run_id=run.id, status=run.status,
                          entry_types=run.entry_types_json, worker_online=_worker_online(db))


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    return [_project_out(db, p) for p in db.scalars(select(Project).order_by(Project.created_at.desc()))]


def _project_out(db: Session, p: Project) -> ProjectOut:
    latest = db.scalar(select(Run).where(Run.project_id == p.id).order_by(Run.started_at.desc()).limit(1))
    inputs = [{"id": i.id, "kind": i.kind, "source": i.source, "ref": i.ref}
              for i in db.scalars(select(Input).where(Input.project_id == p.id).order_by(Input.created_at))]
    return ProjectOut(id=p.id, name=p.name, goal=p.goal, created_at=p.created_at, inputs=inputs,
                      latest_run=_run_out(db, latest) if latest else None)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    p = db.get(Project, project_id)
    if p is None:
        raise ApiError(404, "not_found", "Project not found")
    return _project_out(db, p)


class NewRunIn(BaseModel):
    goal: str | None = Field(default=None, min_length=1, max_length=2000)
    budget: Budget = Budget()


@router.post("/projects/{project_id}/runs", response_model=RunOut, status_code=201)
def new_run(project_id: str, body: NewRunIn, db: Session = Depends(get_db)) -> RunOut:
    p = db.get(Project, project_id)
    if p is None:
        raise ApiError(404, "not_found", "Project not found")
    run = _start_run(db, p, body.goal or p.goal, body.budget.model_dump())
    db.commit()
    return _run_out(db, run)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)) -> RunOut:
    return _run_out(db, _get_run(db, run_id))


@router.post("/runs/{run_id}/pause", response_model=RunOut)
def pause_run(run_id: str, db: Session = Depends(get_db)) -> RunOut:
    run = _get_run(db, run_id)
    runs.set_status(db, run, "paused", "researcher")
    db.commit()
    return _run_out(db, run)


@router.post("/runs/{run_id}/resume", response_model=RunOut)
def resume_run(run_id: str, db: Session = Depends(get_db)) -> RunOut:
    run = _get_run(db, run_id)
    if run.status != "paused":
        raise ApiError(409, "invalid_state", "Run is not paused")
    runs.set_status(db, run, "running", "researcher")
    fake_agent.resume(db, run)
    db.commit()
    return _run_out(db, run)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: str, db: Session = Depends(get_db)) -> RunOut:
    run = _get_run(db, run_id)
    runs.set_status(db, run, "cancelled", "researcher")
    cancel_run_jobs(db, run)
    for task in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id,
                                                   AgentTask.status.not_in(("done", "failed", "cancelled")))):
        task.status = "cancelled"
    db.commit()
    return _run_out(db, run)


# --- jobs (read-only for the dashboard) ------------------------------------------------

class JobOut(BaseModel):
    id: str
    run_id: str
    project_id: str
    task_id: str | None
    worker_id: str | None
    type: str
    payload: dict
    risk: str
    approved: bool
    status: str
    attempt: int
    timeout_s: int
    policy_reason: str | None
    created_at: str
    claimed_at: str | None
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    stdout_tail: str | None
    stderr_tail: str | None
    metrics: dict | None
    files: list | None


def _job_out(j: Job) -> JobOut:
    return JobOut(id=j.id, run_id=j.run_id, project_id=j.project_id, task_id=j.task_id, worker_id=j.worker_id,
                  type=j.type, payload=j.payload_json, risk=j.risk, approved=j.approved, status=j.status,
                  attempt=j.attempt, timeout_s=j.timeout_s, policy_reason=j.policy_reason, created_at=j.created_at,
                  claimed_at=j.claimed_at, started_at=j.started_at, finished_at=j.finished_at, exit_code=j.exit_code,
                  stdout_tail=j.stdout_tail, stderr_tail=j.stderr_tail, metrics=j.metrics_json, files=j.files_json)


@router.get("/runs/{run_id}/jobs", response_model=list[JobOut])
def list_jobs(run_id: str, status: str | None = None, db: Session = Depends(get_db)) -> list[JobOut]:
    _get_run(db, run_id)
    q = select(Job).where(Job.run_id == run_id).order_by(Job.created_at, Job.id)
    if status:
        q = q.where(Job.status == status)
    return [_job_out(j) for j in db.scalars(q)]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    j = db.get(Job, job_id)
    if j is None:
        raise ApiError(404, "not_found", "Job not found")
    return _job_out(j)


class LogOut(BaseModel):
    seq: int
    attempt: int
    stream: str
    chunk: str
    ts: str


@router.get("/jobs/{job_id}/logs", response_model=list[LogOut])
def job_logs(job_id: str, after_seq: int = Query(default=-1), db: Session = Depends(get_db)) -> list[LogOut]:
    from ..models import JobLog

    j = db.get(Job, job_id)
    if j is None:
        raise ApiError(404, "not_found", "Job not found")
    q = (select(JobLog).where(JobLog.job_id == job_id, JobLog.attempt == j.attempt, JobLog.seq > after_seq)
         .order_by(JobLog.seq))
    return [LogOut(seq=l.seq, attempt=l.attempt, stream=l.stream, chunk=l.chunk, ts=l.ts) for l in db.scalars(q)]
