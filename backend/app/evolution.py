"""Evolution engine (AGENTS.md section 6, ARCHITECTURE 3.7 and 3.10, D-009, D-033).

Triggers are deterministic code; the Meta-Controller only drafts the change (prompt,
spec). Guardrails are enforced here, not trusted to the draft: tools only from the
registry, no spawning tools for spawned agents, tags from the frozen vocabulary, core
agents never changed, at most 15 active agents, one evolution action per agent per run.
Every action goes through an `evolution` approval, then a 2-task probation: if the new
version or agent scores below what it replaced, it is rolled back or retired.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ladder
from .events import emit
from .ids import new_id
from .librarian import error_class
from .models import Agent, AgentTask, AgentVersion, Approval, Run
from .rewards import recent_rewards, rolling_reward

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
TOOLS = set(json.loads((AGENTS_DIR / "tool_registry.json").read_text(encoding="utf-8"))["tools"])
VOCAB = set(json.loads((AGENTS_DIR / "tags.json").read_text(encoding="utf-8"))["tags"])
MC_ONLY_TOOLS = {"spawn_agent", "replan", "search_agents", "match_agents"}
CORE_ROLES = {"meta_controller", "evaluator", "council_judge"}
PROBATION_TASKS = 2
REFINE_BELOW, RETIRE_BELOW = 0.6, 0.35
TASK_ROLE = {"design_baseline_suite": ("experiment_designer", "experiment_designer.json")}


# --- helpers ------------------------------------------------------------------------------------

def _evolved(run: Run) -> set[str]:
    return set((run.usage_json or {}).get("evolved_agents", []))


def _mark_evolved(run: Run, agent_id: str) -> None:
    run.usage_json = {**(run.usage_json or {}), "evolved_agents": sorted(_evolved(run) | {agent_id})}


def _pending_for(db: Session, run_id: str | None, key: str) -> bool:
    for a in db.scalars(select(Approval).where(Approval.type == "evolution", Approval.status == "pending")):
        if (a.payload_json or {}).get("candidate", {}).get("key") == key:
            return True
    drafts = db.scalars(select(AgentTask).where(AgentTask.task_type == "evolution_draft",
                                                AgentTask.status.in_(("queued", "running"))))
    return any(((t.input_json or {}).get("candidate") or {}).get("key") == key for t in drafts)


def _agent_view(db: Session, a: Agent | None) -> dict | None:
    if a is None:
        return None
    v = db.get(AgentVersion, a.current_version_id)
    return {"agent_id": a.id, "name": a.name, "role": a.role, "kind": a.kind, "status": a.status, "model": v.model,
            "tools": v.tools_json, "capability_tags": v.capability_tags_json, "output_schema": v.output_schema,
            "prompt": v.system_prompt[:6000], "rolling_reward": rolling_reward(db, a.id)}


def _draft(db: Session, run: Run, candidate: dict) -> AgentTask:
    task = AgentTask(id=new_id("tsk"), run_id=run.id, task_type="evolution_draft", agent_id="agt_meta_controller",
                     status="queued", required_tags_json=["evolve"], input_json={"candidate": candidate})
    db.add(task)
    db.flush()
    return task


# --- capability gaps and the ladder ---------------------------------------------------------------

def open_gap(db: Session, services, run: Run, required: set[str], *, source: str, reason: str,
             task_key: str | None = None, task: AgentTask | None = None) -> dict:
    required = {t for t in required if t in VOCAB} or set(required)
    emit(db, run.id, "evolution_engine", "capability.gap", {"task_id": task_key, "required_tags": sorted(required), "source": source})
    res = ladder.walk(db, required)
    if res.step == "reuse":
        if task_key:
            _assign_gap_tasks(db, run, res.agent)
        return {"ladder_step": "reuse", "agent_id": res.agent.id}
    key = f"gap:{run.id}:{','.join(sorted(required))}"
    if _pending_for(db, run.id, key):
        return {"ladder_step": res.step, "status": "already proposed"}
    if res.step != "restore" and ladder.active_count(db) >= ladder.MAX_ACTIVE:
        emit(db, run.id, "evolution_engine", "evolution.blocked", {"reason": "15 active agents", "required_tags": sorted(required)})
        return {"ladder_step": res.step, "status": "blocked: 15 active agents"}
    role, out_schema = TASK_ROLE.get(_task_type(db, run, task_key), (None, None))
    candidate = {"key": key, "action": "restore" if res.step == "restore" else "spawn", "ladder_step": res.step,
                 "required_tags": sorted(required), "source": source, "reason": reason, "task_key": task_key,
                 "basis": _agent_view(db, res.agent), "role": role, "output_schema": out_schema, "note": res.note}
    if res.step == "restore":
        _create_approval(db, services, run, candidate, proposed={"name": res.agent.name}, evidence=[reason, res.note],
                         effect=f"{res.agent.name} covers {sorted(required)}")
        return {"ladder_step": "restore", "status": "approval requested"}
    _draft(db, run, candidate)
    return {"ladder_step": res.step, "status": "drafting proposal"}


def _task_type(db: Session, run: Run, key: str | None) -> str | None:
    if not key:
        return None
    t = db.scalar(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.graph_key == key))
    return t.task_type if t else None


def _assign_gap_tasks(db: Session, run: Run, agent: Agent) -> None:
    tags = ladder.tags_of(db, agent)
    for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.agent_id.is_(None),
                                                AgentTask.status == "blocked", AgentTask.graph_key.is_not(None))):
        from .activation import SERVICE_TASKS
        if t.task_type not in SERVICE_TASKS and set(t.required_tags_json or []) <= tags:
            t.agent_id = agent.id


def check_runtime_gap(db: Session, services, run: Run, debug_task: AgentTask) -> None:
    """Same error class escalated or failed twice and nobody's tags match it -> runtime gap."""
    out = debug_task.output_json or {}
    if out.get("fixed") and debug_task.status == "done":
        return
    cls = (debug_task.input_json or {}).get("error_class")
    libs = set((debug_task.input_json or {}).get("lib_tags") or [])
    if not cls or not libs:
        return
    same = [t for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.task_type == "debug"))
            if (t.input_json or {}).get("error_class") == cls and t.status in ("done", "failed")
            and not (t.status == "done" and (t.output_json or {}).get("fixed"))]
    if len(same) >= 2:
        open_gap(db, services, run, {"debug:python"} | libs, source="runtime",
                 reason=f"Debugger failed {len(same)}x on: {cls[:160]}")


# --- drafts -> approvals ---------------------------------------------------------------------------

def _sanitize(proposed: dict, candidate: dict, basis: dict | None) -> dict:
    tools = [t for t in (proposed.get("tools") or (basis or {}).get("tools") or []) if t in TOOLS and t not in MC_ONLY_TOOLS]
    if "finish" not in tools:
        tools.append("finish")
    tags = sorted({t for t in (proposed.get("capability_tags") or []) if t in VOCAB} | set(candidate.get("required_tags", [])) |
                  ({t for t in (basis or {}).get("capability_tags", [])} if candidate.get("ladder_step") == "specialise" else set()))
    model = proposed.get("model") if proposed.get("model") in ("strong", "code", "fast") else (basis or {}).get("model", "strong")
    return {"name": (proposed.get("name") or "Spawned agent")[:80], "prompt": (proposed.get("prompt") or "")[:12000],
            "tools": tools, "capability_tags": tags, "model": model}


def handle_draft(db: Session, services, run: Run, task: AgentTask) -> None:
    candidate = (task.input_json or {}).get("candidate") or {}
    evo = (task.output_json or {}).get("evolution") or {}
    basis = candidate.get("basis")
    if candidate.get("action") == "retire":
        _create_approval(db, services, run, candidate, {"name": (basis or {}).get("name")},
                         evo.get("evidence") or [candidate.get("reason", "")], evo.get("expected_effect", "soft retire"))
        return
    proposed = _sanitize(evo.get("proposed_agent") or {}, candidate, basis)
    if not proposed["prompt"].strip():
        emit(db, run.id, "evolution_engine", "evolution.dropped", {"reason": "draft had no prompt", "key": candidate.get("key")})
        return
    extra = {}
    if candidate.get("action") == "refine" and basis:
        extra["prompt_diff"] = "".join(difflib.unified_diff(basis["prompt"].splitlines(True), proposed["prompt"].splitlines(True),
                                                            "current", "proposed"))[:12000]
    _create_approval(db, services, run, {**candidate, **extra}, proposed, evo.get("evidence") or [candidate.get("reason", "")],
                     evo.get("expected_effect") or "")


def _create_approval(db, services, run: Run, candidate: dict, proposed: dict, evidence: list, effect: str) -> Approval:
    lineage = {"specialise": f"specialised from {(candidate.get('basis') or {}).get('agent_id')}",
               "instantiate_template": f"template:{(candidate.get('basis') or {}).get('name')}",
               "restore": "restored", "fresh_spawn": "fresh"}.get(candidate.get("ladder_step"), candidate.get("action"))
    payload = {"summary": f"{candidate.get('action')}: {proposed.get('name')} ({candidate.get('ladder_step') or 'trigger'})"[:300],
               "action": candidate.get("action"), "ladder_step": candidate.get("ladder_step"),
               "gap": {"required_tags": candidate.get("required_tags")} if candidate.get("required_tags") else None,
               "proposed_agent": proposed, "lineage": lineage, "evidence": [str(e)[:500] for e in evidence][:8],
               "expected_effect": str(effect)[:500], "probation_tasks": PROBATION_TASKS, "candidate": candidate}
    if candidate.get("prompt_diff"):
        payload["prompt_diff"] = candidate["prompt_diff"]
    a = Approval(id=new_id("apr"), run_id=run.id, type="evolution", requested_by="agt_meta_controller", payload_json=payload)
    db.add(a)
    db.flush()
    emit(db, run.id, "agt_meta_controller", "approval.requested", {"approval_id": a.id, "type": "evolution", "summary": payload["summary"]})
    services.notify(db, "approval_requested", a)
    return a


# --- applying decisions --------------------------------------------------------------------------------

def _evo_event(db, run_id, action, agent: Agent, version: int | None, reason: str, ladder_step=None) -> None:
    emit(db, run_id, "evolution_engine", "agent.evolution", {"action": action, "ladder_step": ladder_step, "origin": agent.origin,
                                                             "agent_id": agent.id, "version": version, "reason": reason[:300]})


def apply_proposal(db: Session, services, a: Approval, edited_agent: dict | None) -> None:
    p = a.payload_json or {}
    c = p.get("candidate") or {}
    run = db.get(Run, a.run_id) if a.run_id else None
    proposed = _sanitize(edited_agent, c, c.get("basis")) if edited_agent else p.get("proposed_agent") or {}
    basis = db.get(Agent, (c.get("basis") or {}).get("agent_id")) if c.get("basis") else None
    action, step = c.get("action"), c.get("ladder_step")

    if action == "refine" and basis is not None:
        old = db.get(AgentVersion, basis.current_version_id)
        v = AgentVersion(id=new_id("agv"), agent_id=basis.id, version=old.version + 1, system_prompt=proposed["prompt"],
                         tools_json=old.tools_json, capability_tags_json=old.capability_tags_json, model=old.model,
                         output_schema=old.output_schema, max_steps=old.max_steps, reason=c.get("reason", "refined")[:500],
                         parent_version_id=old.id,
                         probation_json={"kind": "refine", "baseline": rolling_reward(db, basis.id) or 0.5, "rewards": {}})
        db.add(v)
        db.flush()
        basis.current_version_id = v.id
        _evo_event(db, a.run_id, "refine", basis, v.version, c.get("reason", ""))
        target = basis
    elif action == "restore" and basis is not None:
        basis.status = "active"
        v = db.get(AgentVersion, basis.current_version_id)
        v.probation_json = {"kind": "restore", "baseline": 0.5, "rewards": {}}
        _evo_event(db, a.run_id, "restore", basis, v.version, c.get("reason", ""), "restore")
        target = basis
        if run:
            _assign_gap_tasks(db, run, basis)
    elif action == "retire" and basis is not None:
        basis.status = "retired"
        _evo_event(db, a.run_id, "retire", basis, None, c.get("reason", ""))
        target = basis
    elif action == "merge":
        target = _spawn(db, proposed, c, origin="fresh", parents=[x for x in c.get("merge_ids", [])])
        for aid in c.get("merge_ids", []):
            other = db.get(Agent, aid)
            if other is not None:
                other.status = "retired"
        _evo_event(db, a.run_id, "merge", target, 1, c.get("reason", ""))
    else:  # spawn: instantiate_template | specialise | fresh_spawn
        origin = {"instantiate_template": f"template:{(c.get('basis') or {}).get('name')}",
                  "specialise": f"specialised:{(c.get('basis') or {}).get('agent_id')}"}.get(step, "fresh")
        target = _spawn(db, proposed, c, origin=origin, parents=[basis.id] if basis else [])
        _evo_event(db, a.run_id, "spawn", target, 1, c.get("reason", ""), step)
        if run:
            _assign_gap_tasks(db, run, target)
    if run is not None and target is not None:
        _mark_evolved(run, target.id)


def _spawn(db: Session, proposed: dict, c: dict, origin: str, parents: list[str]) -> Agent:
    basis = c.get("basis") or {}
    role = c.get("role") or basis.get("role") or "spawned"
    agent = Agent(id=new_id("agt"), name=proposed.get("name", "Spawned agent"), role=role, kind="spawned", status="active",
                  origin=origin, parent_ids_json=parents, evolvable=True, council_evaluated=True, counts_toward_active_cap=True)
    db.add(agent)
    db.flush()
    baseline = rolling_reward(db, parents[0]) if parents else None
    v = AgentVersion(id=new_id("agv"), agent_id=agent.id, version=1, system_prompt=proposed["prompt"],
                     tools_json=proposed["tools"], capability_tags_json=proposed["capability_tags"], model=proposed["model"],
                     output_schema=c.get("output_schema") or basis.get("output_schema"), max_steps=12,
                     reason=f"{c.get('ladder_step')}: {c.get('reason', '')}"[:500], parent_version_id=None,
                     probation_json={"kind": "spawn", "baseline": baseline if baseline is not None else 0.5,
                                     "parent": parents[0] if parents else None, "rewards": {}})
    db.add(v)
    db.flush()
    agent.current_version_id = v.id
    return agent


def reject_proposal(db: Session, services, a: Approval) -> None:
    c = (a.payload_json or {}).get("candidate") or {}
    run = db.get(Run, a.run_id) if a.run_id else None
    if run is None or not c.get("task_key"):
        return
    t = db.scalar(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.graph_key == c["task_key"]))
    if t is not None and t.agent_id is None and t.status == "blocked":
        t.status, t.error = "skipped", "capability gap not resolved (evolution rejected)"
        from .replan import request_replan
        request_replan(db, run, {"type": "capability_gap", "task": c["task_key"], "required_tags": c.get("required_tags"),
                                 "status": "rejected"})


# --- triggers and probation --------------------------------------------------------------------------

def after_task(db: Session, services, task: AgentTask) -> None:
    agent = db.get(Agent, task.agent_id) if task.agent_id else None
    if agent is None or agent.role in CORE_ROLES or task.reward is None:
        return
    _probation(db, task, agent)
    _triggers(db, services, task, agent)


def _probation(db: Session, task: AgentTask, agent: Agent) -> None:
    v = db.get(AgentVersion, task.agent_version_id) if task.agent_version_id else None
    if v is None or not v.probation_json or v.probation_json.get("result"):
        return
    pj = dict(v.probation_json)
    rewards = dict(pj.get("rewards") or {})
    rewards[task.id] = task.reward
    pj["rewards"] = rewards
    if len(rewards) >= PROBATION_TASKS:
        mean = sum(rewards.values()) / len(rewards)
        passed = mean >= pj.get("baseline", 0.5)
        pj["result"], pj["mean"] = ("passed" if passed else "failed"), round(mean, 4)
        if not passed:
            if pj["kind"] == "refine" and v.parent_version_id:
                agent.current_version_id = v.parent_version_id
                _evo_event(db, task.run_id, "rollback", agent, v.version, f"probation mean {mean:.2f} < {pj['baseline']:.2f}")
            else:
                agent.status = "retired"
                _evo_event(db, task.run_id, "retire", agent, v.version, f"probation mean {mean:.2f} < {pj['baseline']:.2f}")
        else:
            emit(db, task.run_id, "evolution_engine", "agent.probation",
                 {"agent_id": agent.id, "version": v.version, "result": "passed", "mean": pj["mean"], "baseline": pj["baseline"]})
    v.probation_json = pj


def _patterns(db: Session, agent: Agent) -> Counter:
    c: Counter = Counter()
    tasks = list(db.scalars(select(AgentTask).where(AgentTask.agent_id == agent.id, AgentTask.reward.is_not(None))
                            .order_by(AgentTask.ended_at.desc()).limit(5)))
    for t in tasks:
        if (t.state_json or {}).get("council_pattern"):
            c[t.state_json["council_pattern"]] += 1
        if t.error:
            c[error_class(t.error) or t.error[:80]] += 1
        blamed = db.scalars(select(AgentTask.id).where(AgentTask.run_id == t.run_id, AgentTask.task_type == "debug",
                                                       AgentTask.failure_origin_agent_id == agent.id)).first()
        if blamed:
            c["caused a failure the Debugger traced back"] += 1
    return c


def _triggers(db: Session, services, task: AgentTask, agent: Agent) -> None:
    run = db.get(Run, task.run_id)
    if not agent.evolvable or agent.status != "active" or agent.id in _evolved(run):
        return
    v = db.get(AgentVersion, agent.current_version_id)
    if v.probation_json and not v.probation_json.get("result"):
        return
    rewards = recent_rewards(db, agent.id)
    if len(rewards) < 3:
        return
    mean = sum(rewards) / len(rewards)
    if len(rewards) >= 5 and mean < RETIRE_BELOW:
        key = f"retire:{agent.id}"
        if not _pending_for(db, run.id, key):
            _create_approval(db, services, run, {"key": key, "action": "retire", "basis": _agent_view(db, agent),
                                                 "reason": f"rolling reward {mean:.2f} < {RETIRE_BELOW} over {len(rewards)} tasks"},
                             {"name": agent.name}, [f"last {len(rewards)} rewards: {[round(r, 2) for r in rewards]}"],
                             "soft retire (restorable)")
        return
    pattern, count = (_patterns(db, agent).most_common(1) or [(None, 0)])[0]
    if mean < REFINE_BELOW and count >= 2:
        key = f"refine:{agent.id}"
        if not _pending_for(db, run.id, key):
            _draft(db, run, {"key": key, "action": "refine", "ladder_step": None, "basis": _agent_view(db, agent),
                             "reason": f"rolling reward {mean:.2f} < {REFINE_BELOW}; repeated failure: {pattern}",
                             "pattern": pattern, "rewards": rewards})


def after_run(db: Session, services, run: Run) -> None:
    """Merge check across recent runs (rarely fires with the seed set: needs >=80% co-invocation,
    nearly identical tools and similar scores)."""
    recent_runs = list(db.scalars(select(Run.id).where(Run.status == "done").order_by(Run.ended_at.desc()).limit(5)))
    if len(recent_runs) < 3:
        return
    used: dict[str, set[str]] = {}
    for t in db.scalars(select(AgentTask).where(AgentTask.run_id.in_(recent_runs), AgentTask.agent_id.is_not(None))):
        used.setdefault(t.agent_id, set()).add(t.run_id)
    agents = [db.get(Agent, aid) for aid in used]
    agents = [a for a in agents if a and a.evolvable and a.status == "active" and a.role not in CORE_ROLES]
    for i, x in enumerate(agents):
        for y in agents[i + 1:]:
            both = used[x.id] & used[y.id]
            either = used[x.id] | used[y.id]
            tx = set(db.get(AgentVersion, x.current_version_id).tools_json)
            ty = set(db.get(AgentVersion, y.current_version_id).tools_json)
            jacc = len(tx & ty) / max(len(tx | ty), 1)
            rx, ry = rolling_reward(db, x.id) or 0, rolling_reward(db, y.id) or 0
            key = f"merge:{min(x.id, y.id)}:{max(x.id, y.id)}"
            if len(both) / len(either) >= 0.8 and jacc >= 0.8 and abs(rx - ry) <= 0.1 and not _pending_for(db, run.id, key):
                _draft(db, run, {"key": key, "action": "merge", "ladder_step": None, "basis": _agent_view(db, x),
                                 "other": _agent_view(db, y), "merge_ids": [x.id, y.id],
                                 "reason": f"co-invoked in {len(both)}/{len(either)} runs, tool overlap {jacc:.2f}"})
