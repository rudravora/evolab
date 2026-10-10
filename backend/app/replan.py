"""Re-planning (ARCHITECTURE 3.9, D-032). The orchestrator calls the Meta-Controller in
`replan` mode only on listed triggers; the returned diff is classified in code:

- minor (add a debug/data-fix task, reorder, drop a crashed branch): applied at once, logged;
- major (activate an agent, new reference target, budget increase, mode change): a `plan`
  approval showing the diff; unaffected tasks keep running.

Every revision is a plan_revisions row and a `plan.revised` event.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import activation
from .events import emit
from .ids import new_id
from .models import AgentTask, Approval, PlanRevision, Run

MAX_REPLANS = 15
NOT_STARTED = ("blocked", "queued")


def request_replan(db: Session, run: Run, trigger: dict, message: str | None = None) -> AgentTask | None:
    """Queue one Meta-Controller replan task; triggers arriving while one is pending are merged into it."""
    pending = db.scalar(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.task_type == "replan",
                                                AgentTask.status == "queued").limit(1))
    if pending is not None:
        inp = dict(pending.input_json or {})
        inp["more_triggers"] = (inp.get("more_triggers") or []) + [trigger]
        if message:
            inp["message"] = ((inp.get("message") or "") + "\n" + message).strip()
        pending.input_json = inp
        return pending
    if run.replan_count >= MAX_REPLANS:
        emit(db, run.id, "orchestrator", "replan.skipped", {"reason": "replan limit reached", "trigger": trigger.get("type")})
        return None
    run.replan_count += 1
    task = AgentTask(id=new_id("tsk"), run_id=run.id, task_type="replan", agent_id="agt_meta_controller", status="queued",
                     required_tags_json=["replan"], input_json={"trigger": trigger, "message": message})
    db.add(task)
    db.flush()
    return task


def classify(diff: dict) -> str:
    major = bool(diff.get("activate") or diff.get("targets_added") or diff.get("mode_change") or diff.get("budget_change"))
    return "major" if major else "minor"


def handle_output(db: Session, services, run: Run, task: AgentTask) -> None:
    from .orchestrator import _branch_decisions, reply

    out = task.output_json or {}
    diff = out.get("diff") or {}
    reason = out.get("reason") or "no reason given"
    trigger = (task.input_json or {}).get("trigger") or {}
    if out.get("branch_decisions"):
        _branch_decisions(db, run, out["branch_decisions"], final=False)
    if trigger.get("type") == "researcher_chat":
        reply(db, run, reason)
    if not any(diff.get(k) for k in ("add_tasks", "remove_tasks", "activate", "deactivate", "targets_added",
                                      "mode_change", "budget_change")):
        return
    if classify(diff) == "minor":
        apply_diff(db, services, run, diff, trigger=trigger.get("type", "replan"), kind="minor", reason=reason)
        return
    a = Approval(id=new_id("apr"), run_id=run.id, type="plan", requested_by="agt_meta_controller",
                 payload_json={"summary": reason[:300], "trigger": trigger.get("type", "replan"), "diff": diff, "reason": reason,
                               "initial": False})
    db.add(a)
    db.flush()
    emit(db, run.id, "agt_meta_controller", "approval.requested", {"approval_id": a.id, "type": "plan", "summary": a.payload_json["summary"]})
    services.notify(db, "approval_requested", a)


def apply_diff(db: Session, services, run: Run, diff: dict, *, trigger: str, kind: str, reason: str,
               approval_id: str | None = None) -> None:
    existing = {t.graph_key: t for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id,
                                                                          AgentTask.graph_key.is_not(None)))}
    added = []
    new_tasks = [t for t in (diff.get("add_tasks") or []) if isinstance(t, dict) and t.get("task_type") in activation.TASK_TYPES]
    for t in new_tasks:
        key = t.get("task_id") or t["task_type"]
        while key in existing:
            key = f"{key}_{len(existing)}"
        t = {**t, "task_id": key, "required_tags": t.get("required_tags") or activation.TASK_TYPES[t["task_type"]][1],
             "depends_on": [d for d in (t.get("depends_on") or []) if d in existing or d in {x.get("task_id") for x in new_tasks}]}
        activation.assign(db, [t], {r["agent_id"] for r in (run.activation_json or []) if r["active"]} |
                          set((diff.get("activate") or [])))
        row = AgentTask(id=new_id("tsk"), run_id=run.id, task_type=t["task_type"], graph_key=key, agent_id=t.get("agent_id"),
                        required_tags_json=t["required_tags"], depends_on_json=t["depends_on"], input_json=t.get("input") or {},
                        status="blocked")
        db.add(row)
        existing[key] = row
        added.append(key)
        if not row.agent_id and row.task_type not in activation.SERVICE_TASKS:
            from .evolution import open_gap
            open_gap(db, services, run, set(row.required_tags_json), source="planning",
                     reason=f"re-plan task {key} needs {row.required_tags_json}", task_key=key)
    removed = []
    for key in diff.get("remove_tasks") or []:
        t = existing.get(key)
        if t is not None and t.status in NOT_STARTED:
            t.status, t.error = "cancelled", f"removed by re-plan: {reason[:200]}"
            removed.append(key)
    if diff.get("activate") or diff.get("deactivate"):
        act = {r["agent_id"]: r for r in (run.activation_json or [])}
        for aid in diff.get("activate") or []:
            act[aid] = {"agent_id": aid, "active": True, "reason": reason[:200]}
            emit(db, run.id, "agt_meta_controller", "agent.activation", act[aid])
        for aid in diff.get("deactivate") or []:
            act[aid] = {"agent_id": aid, "active": False, "reason": reason[:200]}
            emit(db, run.id, "agt_meta_controller", "agent.activation", act[aid])
        run.activation_json = list(act.values())
    if diff.get("targets_added"):
        brief = run.brief_json or {}
        targets = list(brief.get("reference_targets") or [])
        for t in diff["targets_added"]:
            if isinstance(t, dict) and t.get("type") and t not in targets:
                targets.append({**t, "rank": t.get("rank") or len(targets) + 1})
        run.brief_json = {**brief, "reference_targets": targets}
    if diff.get("mode_change") in ("A", "B", "C"):
        run.mode = diff["mode_change"]
    if isinstance(diff.get("budget_change"), dict):
        run.budget_json = {**(run.budget_json or {}), **{k: v for k, v in diff["budget_change"].items()
                                                         if k in ("max_wall_min", "max_tokens")}}
    run.plan_version += 1
    applied = {**diff, "add_tasks": added, "remove_tasks": removed}
    db.add(PlanRevision(id=new_id("prv"), run_id=run.id, version=run.plan_version, trigger=trigger, kind=kind,
                        diff_json=applied, reason=reason[:2000], approval_id=approval_id))
    emit(db, run.id, "orchestrator", "plan.revised", {"version": run.plan_version, "trigger": trigger, "kind": kind,
                                                      "reason": reason[:300], "approval_id": approval_id})


def replan_count(db: Session, run_id: str) -> int:
    return db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.run_id == run_id,
                                                                       AgentTask.task_type == "replan")) or 0
