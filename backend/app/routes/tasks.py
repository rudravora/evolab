"""Agent tasks, transcripts, feedback, council scores and the team graph (API.md section 6)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..models import Agent, AgentMessage, AgentTask, CouncilScore, Run
from ..security import current_user

router = APIRouter(tags=["tasks"], dependencies=[Depends(current_user)])


def _task_out(db: Session, t: AgentTask, tracer=None, detail: bool = False) -> dict:
    agent = db.get(Agent, t.agent_id) if t.agent_id else None
    out = {"id": t.id, "run_id": t.run_id, "task_type": t.task_type, "graph_key": t.graph_key, "agent_id": t.agent_id,
           "agent_name": agent.name if agent else ("Executor" if t.task_type in ("run_baseline", "run_branches") else None),
           "agent_version_id": t.agent_version_id, "status": t.status, "required_tags": t.required_tags_json or [],
           "depends_on": t.depends_on_json or [], "steps": t.steps, "error": t.error, "created_at": t.created_at,
           "ended_at": t.ended_at,
           "reward": {"reward": t.reward, "outcome": t.outcome_score, "outcome_det": t.outcome_det, "council_q": t.council_q,
                      "council_judges": t.council_judges, "council_disagreement": t.council_disagreement,
                      "council_split": t.council_split, "cost": t.cost_norm, "feedback": t.feedback,
                      "tokens_in": t.tokens_in, "tokens_out": t.tokens_out, "wall_s": t.wall_s},
           "failure_origin_agent_id": t.failure_origin_agent_id}
    if detail:
        out.update(input=t.input_json, output=t.output_json, signals=t.signals_json or [],
                   langsmith_trace_url=tracer.url(t.langsmith_trace_id) if tracer else None,
                   langsmith_trace_id=t.langsmith_trace_id)
    return out


@router.get("/runs/{run_id}/tasks")
def list_tasks(run_id: str, agent_id: str | None = None, status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Run, run_id) is None:
        raise ApiError(404, "not_found", "Run not found")
    q = select(AgentTask).where(AgentTask.run_id == run_id).order_by(AgentTask.created_at)
    if agent_id:
        q = q.where(AgentTask.agent_id == agent_id)
    if status:
        q = q.where(AgentTask.status == status)
    return [_task_out(db, t) for t in db.scalars(q)]


def _get(db: Session, task_id: str) -> AgentTask:
    t = db.get(AgentTask, task_id)
    if t is None:
        raise ApiError(404, "not_found", "Task not found")
    return t


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    return _task_out(db, _get(db, task_id), request.app.state.services.tracer, detail=True)


@router.get("/tasks/{task_id}/messages")
def task_messages(task_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get(db, task_id)
    return [{"seq": m.seq, "role": m.role, "content": m.content, "tool_name": m.tool_name, "tool_args": m.tool_args_json,
             "tool_result": m.tool_result_json, "ts": m.ts}
            for m in db.scalars(select(AgentMessage).where(AgentMessage.task_id == task_id).order_by(AgentMessage.seq))]


class FeedbackIn(BaseModel):
    value: Literal["up", "down"]


@router.post("/tasks/{task_id}/feedback")
def feedback(task_id: str, body: FeedbackIn, request: Request, db: Session = Depends(get_db)) -> dict:
    from ..evolution import after_task
    from ..rewards import score

    t = _get(db, task_id)
    if not t.agent_id or t.status not in ("done", "failed"):
        raise ApiError(409, "invalid_state", "Feedback applies to finished agent tasks")
    t.feedback = body.value
    score(db, t, final=db.get(Run, t.run_id).status in ("done", "failed", "cancelled"))
    after_task(db, request.app.state.services, t)
    db.commit()
    return _task_out(db, t)["reward"]


@router.get("/tasks/{task_id}/council")
def task_council(task_id: str, db: Session = Depends(get_db)) -> dict:
    t = _get(db, task_id)
    judges = [{"judge_agent_id": c.judge_agent_id, "tier": c.tier, "scores": c.scores_json, "overall": c.overall,
               "rationale": c.rationale, "failure_pattern": c.failure_pattern, "confidence": c.confidence}
              for c in db.scalars(select(CouncilScore).where(CouncilScore.task_id == task_id).order_by(CouncilScore.tier))]
    return {"task_id": t.id, "status": (t.state_json or {}).get("council", "not_scheduled"), "judges": judges,
            "q": t.council_q, "disagreement": t.council_disagreement, "split": t.council_split}


@router.get("/runs/{run_id}/agent-graph")
def agent_graph(run_id: str, db: Session = Depends(get_db)) -> dict:
    from ..rewards import rolling_reward

    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Run not found")
    act = {r["agent_id"]: r for r in (run.activation_json or [])}
    nodes, edges = [], []
    for a in db.scalars(select(Agent).order_by(Agent.created_at)):
        row = act.get(a.id)
        nodes.append({"id": a.id, "name": a.name, "role": a.role, "kind": a.kind, "status": a.status, "origin": a.origin,
                      "active_in_run": row["active"] if row else a.kind == "spawned" and a.status == "active",
                      "activation_reason": row["reason"] if row else None, "rolling_reward": rolling_reward(db, a.id)})
        for parent in a.parent_ids_json or []:
            kind = "specialised-from" if a.origin.startswith("specialised") else \
                "instantiated-from" if a.origin.startswith("template") else "merged-into" if a.status == "retired" else "spawned-from"
            edges.append({"from": parent, "to": a.id, "kind": kind})
    return {"nodes": nodes, "edges": edges}
