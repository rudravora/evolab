"""Orchestrator (ARCHITECTURE 3.0b, 3.3, 3.9; D-032): plain code that walks the approved task
graph. The Meta-Controller plans up front and is called again only on listed triggers;
no LLM call happens between ordinary handoffs.

tick() is one scheduling pass: intake for new runs, unblock tasks whose dependencies
finished, start Executor service tasks, and hand queued agent tasks to the agent loop
(threads in the server, inline in tests).
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import activation, executor, runs
from .agent_loop import resume_with, run_task
from .events import emit
from .ids import new_id, now_iso
from .models import AgentTask, Approval, Branch, ChatMessage, Experiment, Job, PlanRevision, Run
from .tools import job_result_view

log = logging.getLogger("evolab.orchestrator")
TERMINAL_TASK = {"done", "failed", "cancelled", "skipped"}
PLANNING_TYPES = {"intake", "plan", "replan", "evolution_draft"}
GLOBAL_AGENT_CAP = 4
MAX_REPLANS = 15
BUDGET_TRIGGER = 0.7
APPROVAL_TTL_S = 30 * 60


def _iso_in(seconds: int) -> str:
    return datetime.fromtimestamp(time.time() + seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --- run start ----------------------------------------------------------------------------------

def start_run(db: Session, services, run: Run) -> None:
    """Called by POST /projects and POST /projects/{id}/runs. Intake happens in the background."""
    if services.settings.pipeline == "pipe_check":
        from . import fake_agent
        fake_agent.start(db, run)
        return
    db.add(AgentTask(id=new_id("tsk"), run_id=run.id, task_type="intake", status="queued", input_json={}))


def _intake(services, task_id: str) -> None:
    from .intake import run_intake

    with services.sessionmaker() as db:
        task = db.get(AgentTask, task_id)
        run = db.get(Run, task.run_id)
        try:
            brief = run_intake(db, services, run)
            act = activation.activation(brief)
            run.activation_json = act
            for row in act:
                emit(db, run.id, "activation", "agent.activation", row)
            if any(f["fact"] == "repo_not_linked_to_paper" for f in brief["facts"]):
                _ask(db, services, run, "The codebase you supplied does not cite the paper. Does it belong to this study?")
            task.status, task.ended_at, task.output_json = "done", now_iso(), {"brief": True}
            request_plan(db, run)
        except Exception as exc:  # noqa: BLE001
            log.exception("intake failed")
            task.status, task.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
            runs.set_status(db, run, "failed", "intake")
        db.commit()


def _ask(db: Session, services, run: Run, question: str, task_id: str | None = None) -> Approval:
    a = Approval(id=new_id("apr"), run_id=run.id, type="human_input", requested_by="agt_meta_controller",
                 payload_json={"summary": question[:500], "question": question, "task_id": task_id}, expires_at=_iso_in(APPROVAL_TTL_S))
    db.add(a)
    db.flush()
    emit(db, run.id, "agt_meta_controller", "approval.requested", {"approval_id": a.id, "type": a.type, "summary": a.payload_json["summary"]})
    services.notify(db, "approval_requested", a)
    return a


def request_plan(db: Session, run: Run, comment: str | None = None) -> AgentTask:
    graph = activation.draft_graph(run.brief_json or {})
    active = {r["agent_id"] for r in (run.activation_json or []) if r["active"]}
    activation.assign(db, graph, active)
    task = AgentTask(id=new_id("tsk"), run_id=run.id, task_type="plan", agent_id="agt_meta_controller", status="queued",
                     required_tags_json=["plan"], input_json={"draft_graph": graph, "gaps": activation.gaps(graph),
                                                              "comment": comment})
    db.add(task)
    return task


# --- planning results ----------------------------------------------------------------------------

def _handle_plan(db: Session, services, run: Run, task: AgentTask) -> None:
    out = task.output_json or {}
    graph = out.get("task_graph") or (task.input_json or {}).get("draft_graph") or []
    active = {r["agent_id"] for r in (out.get("activation") or run.activation_json or []) if r["active"]}
    activation.assign(db, graph, active | {"agt_meta_controller", "agt_evaluator", "agt_reporter", "agt_debugger"})
    problem = activation.validate_graph(graph, db)
    if problem:
        log.warning("plan from the Meta-Controller is invalid (%s); falling back to the draft graph", problem)
        graph = (task.input_json or {}).get("draft_graph") or []
        activation.assign(db, graph, active)
    if out.get("activation"):
        run.activation_json = out["activation"]
    est = out.get("estimates") or {}
    run.plan_json = {"task_graph": graph, "mode": out.get("mode"), "reference_targets": out.get("reference_targets"),
                     "estimates": est, "pending": True}
    if out.get("reference_targets"):
        run.brief_json = {**(run.brief_json or {}), "reference_targets": out["reference_targets"]}
    gaps = activation.gaps(graph)
    summary = (f"{len(graph)} tasks, {len({t['agent_id'] for t in graph if t['agent_id']})} agents, "
               f"~{est.get('wall_min', '?')} min" + (f", {len(gaps)} capability gap(s)" if gaps else ""))
    a = Approval(id=new_id("apr"), run_id=run.id, type="plan", requested_by="agt_meta_controller",
                 payload_json={"summary": summary, "plan": {"tasks": graph, "estimated_wall_min": est.get("wall_min"),
                                                            "mode": out.get("mode"), "gaps": gaps},
                               "plan_version": run.plan_version + 1, "initial": True},
                 expires_at=_iso_in(APPROVAL_TTL_S))
    db.add(a)
    db.flush()
    runs.set_status(db, run, "awaiting_approval", "agt_meta_controller")
    emit(db, run.id, "agt_meta_controller", "approval.requested", {"approval_id": a.id, "type": "plan", "summary": summary})
    services.notify(db, "approval_requested", a)


def materialize(db: Session, services, run: Run, graph: list[dict], reason: str = "initial plan approved") -> None:
    """Turn the approved graph into agent_tasks rows (status blocked until dependencies finish)."""
    keys = set()
    for t in graph:
        keys.add(t["task_id"])
        db.add(AgentTask(id=new_id("tsk"), run_id=run.id, task_type=t["task_type"], graph_key=t["task_id"],
                         agent_id=t.get("agent_id"), required_tags_json=t.get("required_tags", []),
                         depends_on_json=t.get("depends_on", []), input_json=t.get("input", {}), status="blocked"))
    db.flush()
    kinds = set((run.brief_json or {}).get("entry_types", []))
    if ("paper" in kinds or "repo" in kinds) and executor.baseline_branch(db, run) is None:
        executor.create_root_branch(db, run)
    run.plan_version += 1
    run.plan_json = {**(run.plan_json or {}), "task_graph": graph, "pending": False}
    db.add(PlanRevision(id=new_id("prv"), run_id=run.id, version=run.plan_version, trigger="intake", kind="initial",
                        diff_json={"add_tasks": sorted(keys)}, reason=reason))
    emit(db, run.id, "orchestrator", "plan.revised", {"version": run.plan_version, "trigger": "intake", "kind": "initial",
                                                      "reason": reason, "approval_id": None})
    from .evolution import open_gap
    for gap in activation.gaps(graph):
        open_gap(db, services, run, set(gap["required_tags"]), source="planning",
                 reason=f"task {gap['task_id']} needs {gap['required_tags']}", task_key=gap["task_id"])


# --- approvals -----------------------------------------------------------------------------------

def on_approval_decided(db: Session, services, a: Approval, status: str, edited: dict | None = None) -> None:
    run = db.get(Run, a.run_id) if a.run_id else None
    p = a.payload_json or {}
    if a.type == "plan" and run is not None:
        if p.get("initial"):
            if status in ("approved", "edited"):
                graph = (edited or {}).get("plan", {}).get("tasks") if status == "edited" else None
                graph = graph or (run.plan_json or {}).get("task_graph") or []
                if status == "edited" and (problem := activation.validate_graph(graph, db)):
                    raise_invalid(problem)
                materialize(db, services, run, graph, "plan edited and approved" if status == "edited" else "plan approved")
                runs.set_status(db, run, "running", "researcher")
            elif run.status == "awaiting_approval" and status == "expired":
                # No one answered: stop rather than re-plan in a loop and spend tokens unattended.
                runs.set_status(db, run, "cancelled", "system")
            elif run.status == "awaiting_approval":
                runs.set_status(db, run, "planning", "researcher")
                request_plan(db, run, comment=a.comment or "rejected without a comment")
        else:
            from .replan import apply_diff
            if status in ("approved", "edited"):
                diff = (edited or {}).get("diff") if status == "edited" else None
                apply_diff(db, services, run, diff or p.get("diff") or {}, trigger=p.get("trigger", "replan"),
                           kind="major", reason=p.get("reason", ""), approval_id=a.id)
    elif a.type == "human_input":
        task = db.get(AgentTask, p.get("task_id")) if p.get("task_id") else None
        answer = f"Researcher answer ({status}): {a.comment or ('yes' if status == 'approved' else 'no')}"
        if task is not None and task.status == "waiting_for_approval":
            resume_with(db, task, answer)
        elif run is not None and run.status not in runs.TERMINAL:
            from .replan import request_replan
            request_replan(db, run, {"type": "researcher_action", "question": p.get("question"), "answer": answer})
    elif a.type == "candidate_selection" and run is not None:
        _candidate_chosen(db, services, run, a, status, edited)
    elif a.type == "evolution":
        from .evolution import apply_proposal, reject_proposal
        if status in ("approved", "edited"):
            apply_proposal(db, services, a, (edited or {}).get("proposed_agent") if status == "edited" else None)
        else:
            reject_proposal(db, services, a)


def raise_invalid(problem: str):
    from .errors import ApiError
    raise ApiError(422, "validation_error", f"edited plan is invalid: {problem}")


def _candidate_chosen(db, services, run: Run, a: Approval, status: str, edited: dict | None) -> None:
    from .models import Input
    from .replan import apply_diff

    cands = (a.payload_json or {}).get("candidates") or []
    idx = int((edited or {}).get("chosen", 0)) if status in ("approved", "edited") else None
    if idx is None or not (0 <= idx < len(cands)):
        emit(db, run.id, "researcher", "candidates.none", {"approval_id": a.id})
        return
    chosen = cands[idx]
    inp = Input(id=new_id("inp"), project_id=run.project_id, kind="paper", ref=chosen["url"], source="url",
                meta_json={"untrusted": True, "title": chosen.get("title"), "chosen_from": a.id})
    db.add(inp)
    db.flush()
    brief = run.brief_json or {}
    order = {"paper_claim": 1, "repo_reported": 2, "published_baseline": 3, "internal_baseline": 4}
    targets = sorted([dict(t) for t in brief.get("reference_targets", [])] + [{"type": "paper_claim", "source": inp.id}],
                     key=lambda t: order.get(t["type"], 5))
    for i, t in enumerate(targets, 1):
        t["rank"] = i
    run.brief_json = {**brief, "reference_targets": targets}
    # The researcher already chose, so this is applied as a minor revision, not another approval.
    apply_diff(db, services, run, {"add_tasks": [{"task_id": "extract_spec_chosen", "task_type": "extract_spec",
                                                  "agent_id": None, "required_tags": ["paper:extract"], "depends_on": [],
                                                  "input": {"mode": "paper", "input_id": inp.id}}]},
               trigger="candidate_selection", kind="minor", reason=f"researcher chose: {chosen.get('title')}", approval_id=a.id)


# --- job results -----------------------------------------------------------------------------------

def on_job_finished(db: Session, services, job: Job) -> None:
    if services is None:
        return
    if services.settings.pipeline == "pipe_check":
        from . import fake_agent
        fake_agent.on_job_finished(db, job)
        return
    if job.status in ("failed", "timed_out"):
        services.notify(db, "job_failed", job)
    from . import uploads
    if uploads.on_job_finished(db, job):
        return
    if executor.on_job_finished(db, services, job):
        return
    if job.task_id is None:
        return
    task = db.get(AgentTask, job.task_id)
    pending = (task.state_json or {}).get("pending") if task else None
    if task and task.status == "waiting_for_job" and pending and pending.get("id") == job.id:
        resume_with(db, task, f"Result of {pending.get('tool')}:\n" + job_result_view(job))
        emit(db, task.run_id, "orchestrator", "agent.task", {"task_id": task.id, "agent_id": task.agent_id, "agent_name": None,
                                                             "status": "queued", "summary": f"job {job.id} {job.status}; resuming"})


def create_debug_task(db: Session, services, run: Run, job: Job, exp: Experiment, reason: str) -> AgentTask:
    from .ladder import best_agent
    from .librarian import error_class

    err = error_class((job.stderr_tail or "") + "\n" + (job.stdout_tail or "")) or reason
    lib_tags = _lib_tags((job.stderr_tail or "") + (job.stdout_tail or ""))
    required = {"debug:python"}
    specialist = best_agent(db, required | lib_tags) if lib_tags else None
    agent = specialist or best_agent(db, required)
    task = AgentTask(id=new_id("tsk"), run_id=run.id, task_type="debug", agent_id=agent.id if agent else None,
                     required_tags_json=sorted(required | (lib_tags if specialist else set())), status="queued",
                     input_json={"failed_job_id": job.id, "experiment_id": exp.id, "reason": reason, "error_class": err,
                                 "lib_tags": sorted(lib_tags), "command": (job.payload_json or {}).get("argv"),
                                 "history": f"debug cycle {exp.debug_cycles + 1} for experiment {exp.id}"})
    db.add(task)
    db.flush()
    emit(db, run.id, "orchestrator", "agent.task", {"task_id": task.id, "agent_id": task.agent_id, "agent_name": agent.name if agent else None,
                                                    "status": "queued", "summary": f"debug: {err[:120]}"})
    return task


def _lib_tags(text: str) -> set[str]:
    import json as _json
    from pathlib import Path

    vocab = _json.loads((Path(__file__).resolve().parent.parent / "agents" / "tags.json").read_text(encoding="utf-8"))["tags"]
    low = text.lower()
    return {t for t in vocab if t.startswith("lib:") and t[4:] in low}


# --- task completion ---------------------------------------------------------------------------------

def on_task_finished(db: Session, services, task: AgentTask) -> None:
    run = db.get(Run, task.run_id)
    tt, out = task.task_type, task.output_json or {}
    from . import replan, rewards
    from .evolution import after_task, check_runtime_gap, handle_draft

    if task.status == "done":
        if tt == "plan":
            _handle_plan(db, services, run, task)
        elif tt == "replan":
            replan.handle_output(db, services, run, task)
        elif tt == "evolution_draft":
            handle_draft(db, services, run, task)
        elif tt == "audit_repo" and out.get("recommended_mode"):
            run.mode = out["recommended_mode"]
        elif tt in ("design_exploratory", "design_baseline_suite", "design_branches"):
            for b in out.get("branches", []):
                br = executor.ensure_branch(db, run, b, proposed_by=task.agent_id)
                if tt in ("design_exploratory", "design_baseline_suite"):
                    executor.set_branch(db, br, "queued", actor=task.agent_id or "experiment_designer")
        elif tt in ("select_branches", "decide_branches"):
            _branch_decisions(db, run, out.get("branch_decisions") or [], final=(tt == "decide_branches"))
        elif tt == "write_report":
            _store_report(db, services, run, task)
        elif tt == "debug":
            _after_debug(db, services, run, task)
        # signals from working agents may trigger a re-plan (ARCHITECTURE 3.9)
        if task.agent_id not in (None, "agt_meta_controller") and task.signals_json and tt not in ("write_report",):
            replan.request_replan(db, run, {"type": "signals", "from_task": task.graph_key or task.id,
                                            "agent_id": task.agent_id, "signals": task.signals_json})
    else:
        if tt == "debug":
            _after_debug(db, services, run, task)
        elif tt == "plan" and run.status == "planning":
            runs.set_status(db, run, "failed", "orchestrator")
        elif task.graph_key and run.status == "running":
            replan.request_replan(db, run, {"type": "task_failed", "task": task.graph_key, "error": (task.error or "")[:500]})
    if task.agent_id:
        rewards.update_task(db, services, task)
        after_task(db, services, task)
    if tt == "debug":
        check_runtime_gap(db, services, run, task)
    _check_run_complete(db, services, run)


def _branch_decisions(db: Session, run: Run, decisions: list[dict], final: bool) -> None:
    seen = set()
    for d in decisions:
        br = db.get(Branch, d.get("branch_id"))
        if br is None or br.run_id != run.id:
            continue
        seen.add(br.id)
        if final:
            if br.status == "done":
                executor.set_branch(db, br, d["decision"], d["decision"], d.get("decision_reason"), "agt_meta_controller")
        elif br.status == "proposed":
            if d["decision"] == "expanded":
                br.decision_reason = d.get("decision_reason")
                executor.set_branch(db, br, "queued", actor="agt_meta_controller")
            else:
                executor.set_branch(db, br, "pruned", "pruned", d.get("decision_reason"), "agt_meta_controller")
    if not final:
        for br in db.scalars(select(Branch).where(Branch.run_id == run.id, Branch.status == "proposed")):
            if br.id not in seen:
                executor.set_branch(db, br, "pruned", "pruned", "not selected by the Meta-Controller", "agt_meta_controller")


def _after_debug(db: Session, services, run: Run, task: AgentTask) -> None:
    exp = db.get(Experiment, (task.input_json or {}).get("experiment_id"))
    out = task.output_json or {}
    if out.get("failure_origin_agent_id"):
        task.failure_origin_agent_id = out["failure_origin_agent_id"]
    if exp is None or exp.status != "debugging":
        return
    if task.status == "done" and out.get("fixed"):
        executor.retry_experiment(db, run, exp)
    else:
        executor.give_up(db, run, exp)
        if out.get("escalate") or task.status == "failed":
            from .replan import request_replan
            request_replan(db, run, {"type": "unresolved_failure", "error_class": (task.input_json or {}).get("error_class"),
                                     "experiment_id": exp.id})


def _store_report(db: Session, services, run: Run, task: AgentTask) -> None:
    from pathlib import Path

    from .models import Artifact
    out = task.output_json or {}
    d = Path(services.settings.artifacts_dir) / run.id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "report.md"
    text = out.get("report_md", "")
    path.write_text(text, encoding="utf-8")
    import hashlib
    art = Artifact(id=new_id("art"), run_id=run.id, kind="report", path=str(path),
                   sha256=hashlib.sha256(text.encode()).hexdigest(), size=len(text.encode()))
    db.add(art)
    db.flush()
    emit(db, run.id, "agt_reporter", "report.ready", {"artifact_id": art.id})


def _check_run_complete(db: Session, services, run: Run) -> None:
    if run.status != "running":
        return
    graph_tasks = list(db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.graph_key.is_not(None))))
    if not graph_tasks or any(t.status not in TERMINAL_TASK for t in graph_tasks):
        return
    busy = db.scalar(select(func.count()).select_from(AgentTask).where(
        AgentTask.run_id == run.id, AgentTask.graph_key.is_(None),
        AgentTask.status.in_(("queued", "running", "waiting_for_job", "waiting_for_approval"))))
    if busy:
        return
    report = next((t for t in graph_tasks if t.task_type == "write_report"), None)
    runs.set_status(db, run, "done" if report and report.status == "done" else "failed", "orchestrator")
    from .evolution import after_run
    from .rewards import finalize_run
    finalize_run(db, services, run)
    after_run(db, services, run)
    services.notify(db, "run_finished", run)


# --- usage and budget ------------------------------------------------------------------------------

def usage(db: Session, run: Run) -> dict:
    from .models import CouncilScore
    tokens = db.scalar(select(func.coalesce(func.sum(AgentTask.tokens_in + AgentTask.tokens_out), 0))
                       .where(AgentTask.run_id == run.id)) or 0
    council = db.scalar(select(func.coalesce(func.sum(CouncilScore.tokens_in + CouncilScore.tokens_out), 0))
                        .join(AgentTask, AgentTask.id == CouncilScore.task_id).where(AgentTask.run_id == run.id)) or 0
    started = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(run.ended_at.replace("Z", "+00:00")) if run.ended_at else datetime.now(timezone.utc)
    return {"tokens": int(tokens + council), "council_tokens": int(council),
            "wall_min": round((end - started).total_seconds() / 60, 2)}


def _budget_check(db: Session, run: Run) -> None:
    u = usage(db, run)
    b = run.budget_json or {}
    frac = max(u["tokens"] / max(b.get("max_tokens", 1), 1), u["wall_min"] / max(b.get("max_wall_min", 1), 1))
    run.usage_json = {**(run.usage_json or {}), **u}
    state = run.usage_json
    if frac >= BUDGET_TRIGGER and not state.get("budget_warned"):
        run.usage_json = {**state, "budget_warned": True}
        metric = "tokens" if u["tokens"] / max(b.get("max_tokens", 1), 1) >= BUDGET_TRIGGER else "wall_min"
        emit(db, run.id, "orchestrator", "budget.warning", {"metric": metric, "used": u[metric], "limit": b.get(f"max_{metric}")})
        from .replan import request_replan
        request_replan(db, run, {"type": "budget", "used_fraction": round(frac, 2)})
    if frac >= 1.0 and not state.get("budget_exhausted"):
        run.usage_json = {**run.usage_json, "budget_exhausted": True}
        for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.status == "blocked",
                                                    AgentTask.task_type.in_(("design_branches", "select_branches", "run_branches",
                                                                             "evaluate_final", "decide_branches")))):
            t.status, t.error = "skipped", "budget exhausted"


# --- scheduling -------------------------------------------------------------------------------------

def _unblock(db: Session, run: Run) -> None:
    tasks = list(db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.graph_key.is_not(None))))
    status = {t.graph_key: t.status for t in tasks}
    for t in tasks:
        if t.status != "blocked":
            continue
        if all(status.get(d) in TERMINAL_TASK for d in (t.depends_on_json or [])):
            if t.task_type in activation.SERVICE_TASKS:
                t.status = "queued"
            elif t.agent_id:
                t.status = "queued"
            # else: capability gap, waits for the ladder (evolution approval) to assign an agent


def _claim(db: Session, task_id: str) -> bool:
    n = db.execute(update(AgentTask).where(AgentTask.id == task_id, AgentTask.status == "queued")
                   .values(status="running")).rowcount
    return n == 1


def tick(services, inline: bool = False) -> int:
    """One scheduling pass. Returns how many tasks it started."""
    started: list[str] = []
    intakes: list[str] = []
    with services.sessionmaker() as db:
        for t in db.scalars(select(AgentTask).where(AgentTask.task_type == "intake", AgentTask.status == "queued")):
            if _claim(db, t.id):
                intakes.append(t.id)
        live = list(db.scalars(select(Run).where(Run.status.in_(("planning", "running", "awaiting_approval")))))
        in_flight = db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.status == "running",
                                                                                AgentTask.agent_id.is_not(None))) or 0
        for run in live:
            if run.status == "running":
                _unblock(db, run)
                _budget_check(db, run)
                for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.status == "queued",
                                                            AgentTask.task_type.in_(activation.SERVICE_TASKS))):
                    if _claim(db, t.id):
                        executor.start(db, run, t)
                        on_task_if_finished(db, services, t)
            cap = int((run.budget_json or {}).get("max_concurrent_agents", 2))
            run_flight = db.scalar(select(func.count()).select_from(AgentTask).where(
                AgentTask.run_id == run.id, AgentTask.status == "running", AgentTask.agent_id.is_not(None))) or 0
            q = select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.status == "queued",
                                        AgentTask.agent_id.is_not(None)).order_by(AgentTask.created_at)
            for t in db.scalars(q):
                if t.task_type == "evolution_draft":
                    continue            # handled below, independent of run status
                if run.status != "running" and t.task_type not in PLANNING_TYPES:
                    continue
                retry_at = (t.state_json or {}).get("retry_at")
                if retry_at and retry_at > time.time():
                    continue
                if run_flight >= cap or in_flight >= GLOBAL_AGENT_CAP:
                    break
                if _claim(db, t.id):
                    started.append(t.id)
                    run_flight += 1
                    in_flight += 1
        # Evolution drafts may outlive their run (triggers fire at run end); they run regardless of run status.
        for t in db.scalars(select(AgentTask).where(AgentTask.task_type == "evolution_draft", AgentTask.status == "queued")):
            if in_flight < GLOBAL_AGENT_CAP and _claim(db, t.id):
                started.append(t.id)
                in_flight += 1
        councils = []
        for t in db.scalars(select(AgentTask).where(AgentTask.status.in_(("done", "failed")), AgentTask.agent_id.is_not(None))
                            .order_by(AgentTask.ended_at)):
            st = t.state_json or {}
            if st.get("council") == "pending" and st.get("council_retry_at", 0) <= time.time() and len(councils) < 2:
                t.state_json = {**t.state_json, "council": "running"}
                councils.append(t.id)
        db.commit()
    from . import council_runner
    for tid in intakes:
        _dispatch(services, _intake, tid, inline)
    for tid in started:
        _dispatch(services, run_task, tid, inline)
    for tid in councils:
        _dispatch(services, council_runner.run, tid, inline)
    return len(started) + len(intakes) + len(councils)


def on_task_if_finished(db: Session, services, t: AgentTask) -> None:
    if t.status in ("done", "failed"):
        on_task_finished(db, services, t)


def _dispatch(services, fn, task_id: str, inline: bool) -> None:
    if inline:
        fn(services, task_id)
        return
    pool: ThreadPoolExecutor = services.extras.setdefault("pool", ThreadPoolExecutor(max_workers=GLOBAL_AGENT_CAP + 2))
    pool.submit(fn, services, task_id)


def recover_orphans(services) -> int:
    """Requeue agent tasks left `running` by a process that died (killed server, crash, restart).

    Only one orchestrator runs (D-046), so at startup nothing can still be executing them. The agent
    loop commits its transcript before every AI and tool call, so a requeued task resumes from its
    last saved step instead of starting over. Without this, such a task blocks its run forever,
    because the scheduler only starts `queued` tasks."""
    with services.sessionmaker() as db:
        ids = list(db.scalars(select(AgentTask.id).where(AgentTask.status == "running", AgentTask.agent_id.is_not(None))))
        if ids:
            db.execute(update(AgentTask).where(AgentTask.id.in_(ids)).values(status="queued"))
            for t in db.scalars(select(AgentTask).where(AgentTask.id.in_(ids))):
                t.state_json = {**(t.state_json or {}), "retry_at": None}
                emit(db, t.run_id, "orchestrator", "agent.task", {"task_id": t.id, "agent_id": t.agent_id, "status": "queued",
                                                                   "summary": "resumed after a server restart"})
            db.commit()
            log.warning("requeued %d agent task(s) left running by a previous process", len(ids))
        return len(ids)


async def run_forever(services, interval_s: float = 1.0) -> None:
    try:
        await asyncio.to_thread(recover_orphans, services)
    except Exception:  # noqa: BLE001 - never block scheduling on recovery
        log.exception("orphan recovery failed")
    while True:
        try:
            await asyncio.to_thread(tick, services)
        except Exception:  # noqa: BLE001 - keep scheduling
            log.exception("tick failed")
        await asyncio.sleep(interval_s)


# --- chat -------------------------------------------------------------------------------------------

def chat(db: Session, services, run: Run, message: str, target_agent_id: str | None) -> ChatMessage:
    m = ChatMessage(id=new_id("chat"), run_id=run.id, role="researcher", content=message, target_agent_id=target_agent_id)
    db.add(m)
    db.flush()
    emit(db, run.id, "researcher", "chat.message", {"id": m.id, "role": "researcher", "content": message})
    from .replan import request_replan
    if run.status in runs.TERMINAL:
        reply(db, run, "This run has ended; start a new run to act on new instructions.")
    else:
        request_replan(db, run, {"type": "researcher_chat", "chat_id": m.id}, message=message)
    return m


def reply(db: Session, run: Run, text: str) -> None:
    m = ChatMessage(id=new_id("chat"), run_id=run.id, role="meta_controller", content=text[:4000])
    db.add(m)
    db.flush()
    emit(db, run.id, "agt_meta_controller", "chat.message", {"id": m.id, "role": "meta_controller", "content": m.content})


def cancel_tasks(db: Session, run: Run) -> None:
    for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.status.not_in(TERMINAL_TASK))):
        t.status = "cancelled"
    for b in db.scalars(select(Branch).where(Branch.run_id == run.id, Branch.status.in_(("proposed", "queued", "running")))):
        executor.set_branch(db, b, "killed", actor="researcher")

