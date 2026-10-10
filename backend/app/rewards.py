"""Rewards per agent task (AGENTS.md section 5, D-008, D-040):

    O = 0.5 * O_det + 0.5 * Q      (Q = Performance Council median; O = O_det if unavailable)
    R = 0.6 * O + 0.2 * (1 - C) + 0.2 * F

O_det is the role's objective check. Some checks depend on what happens later in the run
(did the recommended mode work? were the Designer's branches informative?), so a task gets
a provisional reward when it ends and a final one when the run ends.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .events import emit
from .models import Agent, AgentTask, Approval, Branch, Experiment, Job, LedgerEntry, Run

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.council import CouncilResult, blended_outcome, cost, feedback_value, reward  # noqa: E402

PLAN_REQUIRED = ("claim", "metric", "datasets", "architecture", "hyperparams")
ROLLING_WINDOW = 5


def _blamed(db: Session, run_id: str, agent_id: str) -> int:
    return db.scalar(select(func.count()).select_from(AgentTask).where(
        AgentTask.run_id == run_id, AgentTask.task_type == "debug", AgentTask.failure_origin_agent_id == agent_id)) or 0


def _approval_score(db: Session, task: AgentTask, types: tuple[str, ...]) -> float:
    a = db.scalar(select(Approval).where(Approval.run_id == task.run_id, Approval.type.in_(types),
                                         Approval.created_at >= (task.ended_at or task.created_at))
                  .order_by(Approval.created_at).limit(1))
    if a is None:
        return 1.0 if task.task_type != "plan" else 0.5
    return {"approved": 1.0, "edited": 0.5, "rejected": 0.0, "expired": 0.0}.get(a.status, 0.5)


def _run_has_results(db: Session, run_id: str) -> bool:
    return db.scalar(select(func.count()).select_from(Experiment).join(Branch, Branch.id == Experiment.branch_id)
                     .where(Branch.run_id == run_id, Experiment.status == "done")) > 0


def outcome_det(db: Session, task: AgentTask, final: bool = False) -> float:
    if task.status != "done":
        return 0.0
    agent = db.get(Agent, task.agent_id)
    role, out, run_id = agent.role, task.output_json or {}, task.run_id
    penalty = 0.2 * _blamed(db, run_id, agent.id)

    if role == "paper_analyst":
        mode = out.get("mode")
        if mode == "paper":
            present = sum(bool(out.get(k)) for k in PLAN_REQUIRED) / len(PLAN_REQUIRED)
            return max(0.0, present - penalty)
        if mode == "question":
            return _approval_score(db, task, ("candidate_selection",))
        return 1.0 if out.get("baselines") else 0.5
    if role == "repo_auditor":
        if not final:
            return 0.5
        worked = 1.0 if _run_has_results(db, run_id) else 0.0
        if out.get("inferred_claim"):
            ev = _latest(db, run_id, "evaluate_final") or _latest(db, run_id, "evaluate") or {}
            confirmed = any(v.get("target_type") == "repo_reported" and v.get("verdict") in ("reproduced", "partial")
                            for v in ev.get("verdicts", []))
            return (worked + (1.0 if confirmed else 0.0)) / 2
        return worked
    if role == "env_data_engineer":
        retries = db.scalar(select(func.count()).select_from(Job).where(Job.task_id == task.id,
                                                                       Job.status.in_(("failed", "timed_out")))) or 0
        return max(0.0, 1.0 - 0.25 * retries)
    if role == "implementer":
        runs_ok = _run_has_results(db, run_id) if final else True
        return max(0.0, (1.0 if runs_ok else 0.0) - penalty)
    if role == "debugger":
        if not out.get("fixed"):
            return 0.0
        failed_before = db.scalar(select(func.count()).select_from(Job).where(Job.task_id == task.id,
                                                                             Job.status.in_(("failed", "timed_out")))) or 0
        return 1.0 if failed_before == 0 else 0.5 if failed_before == 1 else 0.0
    if role == "experiment_designer":
        if not final:
            return 0.5
        mine = [b for b in db.scalars(select(Branch).where(Branch.run_id == run_id))
                if b.hypothesis in {x.get("hypothesis", "").strip() for x in out.get("branches", [])}]
        if not mine:
            return 0.0
        hyps = [b.hypothesis.lower() for b in mine]
        informative = sum(1 for b in mine if b.status in ("done", "expanded", "pruned") and hyps.count(b.hypothesis.lower()) == 1
                          and db.scalar(select(func.count()).select_from(Experiment).where(
                              Experiment.branch_id == b.id, Experiment.status == "done")) > 0)
        return informative / len(mine)
    if role == "evaluator":
        targets = (db.get(Run, run_id).brief_json or {}).get("reference_targets") or []
        if not targets:
            return 1.0 if out.get("verdicts") else 0.5
        return min(1.0, len(out.get("verdicts", [])) / len(targets))
    if role == "reporter":
        ledger = set(db.scalars(select(LedgerEntry.id).where(LedgerEntry.run_id == run_id)))
        cited = {w.get("ledger_entry_id") for w in out.get("why_differs", [])}
        return 1.0 if not ledger else len(ledger & cited) / len(ledger)
    if role == "meta_controller":
        if task.task_type == "plan":
            return _approval_score(db, task, ("plan",))
        if task.task_type == "evolution_draft":
            return _approval_score(db, task, ("evolution",))
        return 1.0
    return 1.0   # fresh-spawned roles: a valid, schema-checked output


def _latest(db: Session, run_id: str, task_type: str) -> dict | None:
    t = db.scalar(select(AgentTask).where(AgentTask.run_id == run_id, AgentTask.task_type == task_type,
                                          AgentTask.status == "done").order_by(AgentTask.ended_at.desc()).limit(1))
    return t.output_json if t else None


def _cost(db: Session, task: AgentTask) -> float:
    run = db.get(Run, task.run_id)
    b = run.budget_json or {}
    n = max(db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.run_id == run.id,
                                                                      AgentTask.agent_id.is_not(None))) or 1, 1)
    return cost(task.tokens_in + task.tokens_out, int(b.get("max_tokens", 1_500_000) / n), task.wall_s or 0.0,
                b.get("max_wall_min", 90) * 60 / n)


def score(db: Session, task: AgentTask, final: bool = False) -> None:
    task.outcome_det = round(outcome_det(db, task, final), 4)
    council = CouncilResult(task.council_q, task.council_judges or 0, task.council_disagreement, bool(task.council_split), None)
    task.outcome_score = round(blended_outcome(task.outcome_det, council), 4)
    task.cost_norm = round(_cost(db, task), 4)
    task.reward = reward(task.outcome_score, task.cost_norm, feedback_value(task.feedback))
    emit(db, task.run_id, "evolution_engine", "agent.score",
         {"agent_id": task.agent_id, "task_id": task.id, "reward": task.reward, "outcome": task.outcome_score,
          "outcome_det": task.outcome_det, "council_q": task.council_q, "council_split": task.council_split,
          "cost": task.cost_norm, "feedback": task.feedback})


def update_task(db: Session, services, task: AgentTask) -> None:
    agent = db.get(Agent, task.agent_id)
    if agent is None or agent.role == "council_judge":
        return
    score(db, task)
    if services.settings.feature_council and agent.council_evaluated and services.llm.configured():
        task.state_json = {**(task.state_json or {}), "council": "pending"}


def finalize_run(db: Session, services, run: Run) -> None:
    for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.agent_id.is_not(None),
                                                AgentTask.status.in_(("done", "failed")))):
        if db.get(Agent, t.agent_id).role != "council_judge":
            score(db, t, final=True)


def rolling_reward(db: Session, agent_id: str, window: int = ROLLING_WINDOW) -> float | None:
    vals = list(db.scalars(select(AgentTask.reward).where(AgentTask.agent_id == agent_id, AgentTask.reward.is_not(None))
                           .order_by(AgentTask.ended_at.desc()).limit(window)))
    return round(sum(vals) / len(vals), 4) if vals else None


def recent_rewards(db: Session, agent_id: str, window: int = ROLLING_WINDOW) -> list[float]:
    return list(db.scalars(select(AgentTask.reward).where(AgentTask.agent_id == agent_id, AgentTask.reward.is_not(None))
                           .order_by(AgentTask.ended_at.desc()).limit(window)))
