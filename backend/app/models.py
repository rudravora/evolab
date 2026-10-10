"""SQLAlchemy models: one class per table in docs/ARCHITECTURE.md section 4.

IDs are opaque text, timestamps UTC ISO strings, JSON columns validated at the
API layer. Enum-like columns are plain strings; allowed values are listed in
API.md section 1.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .ids import now_iso

Json = dict[str, Any] | list[Any]


def _ts() -> Mapped[str]:
    return mapped_column(String(32), default=now_iso, nullable=False)


def _opt_ts() -> Mapped[str | None]:
    return mapped_column(String(32), nullable=True)


# --- workers -------------------------------------------------------------

class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    token_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="offline")      # online|offline
    platform: Mapped[str | None] = mapped_column(String(64))
    last_heartbeat: Mapped[str | None] = _opt_ts()
    cpu_pct: Mapped[float | None] = mapped_column(Float)
    ram_pct: Mapped[float | None] = mapped_column(Float)
    capabilities_json: Mapped[Json | None] = mapped_column(JSON)
    created_at: Mapped[str] = _ts()


class WorkerPairing(Base):
    """One-time pairing codes (ARCHITECTURE 3.1). Stored hashed; single use."""
    __tablename__ = "worker_pairings"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[str] = mapped_column(String(32))
    used_at: Mapped[str | None] = _opt_ts()
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    created_at: Mapped[str] = _ts()


# --- projects, inputs, runs ----------------------------------------------

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str | None] = mapped_column(Text)
    workspace_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[str] = _ts()


class Input(Base):
    __tablename__ = "inputs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))      # paper|question|repo|dataset|note
    ref: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))    # url|upload|worker_path|text
    meta_json: Mapped[Json | None] = mapped_column(JSON)
    created_at: Mapped[str] = _ts()


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    goal: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="planning")
    entry_types_json: Mapped[Json | None] = mapped_column(JSON)
    brief_json: Mapped[Json | None] = mapped_column(JSON)
    activation_json: Mapped[Json | None] = mapped_column(JSON)
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    budget_json: Mapped[Json | None] = mapped_column(JSON)
    usage_json: Mapped[Json | None] = mapped_column(JSON)
    started_at: Mapped[str] = _ts()
    ended_at: Mapped[str | None] = _opt_ts()


class PlanRevision(Base):
    __tablename__ = "plan_revisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))      # initial|minor|major
    diff_json: Mapped[Json | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    approval_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = _ts()


# --- agents ----------------------------------------------------------------

class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))      # core|seed|spawned|template
    status: Mapped[str] = mapped_column(String(16))    # active|inactive|retired|dormant
    origin: Mapped[str] = mapped_column(String(128))   # seed|template:<name>|specialised:<id>|fresh|restored
    current_version_id: Mapped[str | None] = mapped_column(String(64))
    parent_ids_json: Mapped[Json | None] = mapped_column(JSON)
    evolvable: Mapped[bool] = mapped_column(default=True)
    council_evaluated: Mapped[bool] = mapped_column(default=True)
    counts_toward_active_cap: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str] = _ts()


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    system_prompt: Mapped[str] = mapped_column(Text)
    tools_json: Mapped[Json] = mapped_column(JSON)
    capability_tags_json: Mapped[Json] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(16))     # strong|code|fast
    output_schema: Mapped[str | None] = mapped_column(String(128))
    max_steps: Mapped[int] = mapped_column(Integer, default=12)
    reason: Mapped[str | None] = mapped_column(Text)
    parent_version_id: Mapped[str | None] = mapped_column(String(64))
    probation_json: Mapped[Json | None] = mapped_column(JSON)
    created_at: Mapped[str] = _ts()


class AgentTask(Base):
    __tablename__ = "agent_tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    agent_version_id: Mapped[str | None] = mapped_column(ForeignKey("agent_versions.id"))
    task_type: Mapped[str] = mapped_column(String(64))
    required_tags_json: Mapped[Json | None] = mapped_column(JSON)
    input_json: Mapped[Json | None] = mapped_column(JSON)
    output_json: Mapped[Json | None] = mapped_column(JSON)
    signals_json: Mapped[Json | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    wall_s: Mapped[float] = mapped_column(Float, default=0.0)
    cost_norm: Mapped[float | None] = mapped_column(Float)
    outcome_det: Mapped[float | None] = mapped_column(Float)
    council_q: Mapped[float | None] = mapped_column(Float)
    council_judges: Mapped[int | None] = mapped_column(Integer)
    council_disagreement: Mapped[float | None] = mapped_column(Float)
    council_split: Mapped[bool | None] = mapped_column()
    outcome_score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(String(8))   # up|down
    reward: Mapped[float | None] = mapped_column(Float)
    failure_origin_agent_id: Mapped[str | None] = mapped_column(String(64))
    langsmith_trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = _ts()
    ended_at: Mapped[str | None] = _opt_ts()


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (UniqueConstraint("task_id", "seq"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str | None] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(64))
    tool_args_json: Mapped[Json | None] = mapped_column(JSON)
    tool_result_json: Mapped[Json | None] = mapped_column(JSON)
    ts: Mapped[str] = _ts()


class CouncilScore(Base):
    __tablename__ = "council_scores"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    judge_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    tier: Mapped[str] = mapped_column(String(16))
    scores_json: Mapped[Json] = mapped_column(JSON)
    overall: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    failure_pattern: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = _ts()


# --- jobs ------------------------------------------------------------------

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_worker_status", "worker_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))   # selects the worker jail (D-042)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("agent_tasks.id"))
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    type: Mapped[str] = mapped_column(String(24))
    payload_json: Mapped[Json] = mapped_column(JSON)
    risk: Mapped[str] = mapped_column(String(8), default="auto")    # auto|high
    approved: Mapped[bool] = mapped_column(default=False)            # researcher approved a high-risk job
    cancel_requested: Mapped[bool] = mapped_column(default=False)    # sent to the worker via heartbeat
    policy_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    timeout_s: Mapped[int] = mapped_column(Integer, default=900)
    max_output_bytes: Mapped[int] = mapped_column(Integer, default=5_000_000)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = _ts()
    claimed_at: Mapped[str | None] = _opt_ts()
    started_at: Mapped[str | None] = _opt_ts()
    finished_at: Mapped[str | None] = _opt_ts()
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout_tail: Mapped[str | None] = mapped_column(Text)
    stderr_tail: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[Json | None] = mapped_column(JSON)
    files_json: Mapped[Json | None] = mapped_column(JSON)


class JobLog(Base):
    __tablename__ = "job_logs"
    __table_args__ = (UniqueConstraint("job_id", "attempt", "seq"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    seq: Mapped[int] = mapped_column(Integer)
    stream: Mapped[str] = mapped_column(String(8))
    chunk: Mapped[str] = mapped_column(Text)
    ts: Mapped[str] = _ts()


# --- experiments -----------------------------------------------------------

class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    parent_branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"))
    hypothesis: Mapped[str] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(String(16))   # whatif|exploratory|baseline|transfer
    spec_json: Mapped[Json | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    priority_score: Mapped[float | None] = mapped_column(Float)
    decision: Mapped[str | None] = mapped_column(String(16))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = _ts()


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    seed: Mapped[int | None] = mapped_column(Integer)
    config_json: Mapped[Json | None] = mapped_column(JSON)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    metrics_json: Mapped[Json | None] = mapped_column(JSON)
    cost_s: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    created_at: Mapped[str] = _ts()


# --- ledger, memory, approvals, notes, artifacts, events -------------------

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("agent_tasks.id"))
    category: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    diff_ref: Mapped[str | None] = mapped_column(String(200))
    before_json: Mapped[Json | None] = mapped_column(JSON)
    after_json: Mapped[Json | None] = mapped_column(JSON)
    created_at: Mapped[str] = _ts()


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    signature: Mapped[str] = mapped_column(String(128), index=True)
    context_json: Mapped[Json | None] = mapped_column(JSON)
    content_json: Mapped[Json] = mapped_column(JSON)
    supermemory_id: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(8))     # seeded|learned
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[str | None] = _opt_ts()
    created_at: Mapped[str] = _ts()


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    type: Mapped[str] = mapped_column(String(24))
    payload_json: Mapped[Json] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[str | None] = mapped_column(String(64))
    decided_via: Mapped[str | None] = mapped_column(String(16))   # dashboard|n8n
    comment: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[str | None] = _opt_ts()
    decided_at: Mapped[str | None] = _opt_ts()
    created_at: Mapped[str] = _ts()


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    markdown: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[str] = _ts()


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = _ts()


class Event(Base):
    """Append-only (ARCHITECTURE section 4): application code never updates or deletes rows."""
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_run_id_id", "run_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # monotonic SSE id
    run_id: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[str] = _ts()
    actor: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(48))
    payload_json: Mapped[Json | None] = mapped_column(JSON)


class AppendOnlyError(RuntimeError):
    pass


@event.listens_for(Event, "before_update")
def _no_event_update(*_args):
    raise AppendOnlyError("events are append-only")


@event.listens_for(Event, "before_delete")
def _no_event_delete(*_args):
    raise AppendOnlyError("events are append-only")
