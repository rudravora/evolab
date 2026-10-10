"""Executor service (AGENTS.md roster #6; WORKFLOW 3.5): turns branches into experiment jobs,
scales seeds and per-run time to the budget, records metrics, and hands failed experiments
to the Debugger. Plain code, no LLM.

Entry point template (from the Implementer's output, or a branch's spec for the dataset
path): a command string with placeholders {seed}, {budget_min}, {results_path} and
{spec_args} (the branch spec as `--key value` pairs). The worker reads the JSON at
`results_path` back as the job's metrics (B's runner); B's harness result schema
(`{"metrics": {...}, "param_count", "train_seconds"}`) is unwrapped here.
"""

from __future__ import annotations

import shlex

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import ApiError
from .events import emit
from .ids import new_id, now_iso
from .jobs import create_job
from .models import AgentTask, Branch, Experiment, Job, Run

MAX_DEBUG_CYCLES = 2
SPEC_SKIP = {"entrypoint", "workdir"}


def ensure_branch(db: Session, run: Run, b: dict, proposed_by: str | None = None) -> Branch:
    """Create a proposed branch unless one with the same hypothesis exists (Designer may call
    propose_branch and also list the branch in its finish output)."""
    hyp = (b.get("hypothesis") or "").strip()[:2000]
    existing = db.scalar(select(Branch).where(Branch.run_id == run.id, Branch.hypothesis == hyp))
    if existing:
        return existing
    root = baseline_branch(db, run)
    kind = b.get("kind", "whatif")
    # The first branch of a run (root) is the baseline every other branch is compared with.
    br = Branch(id=new_id("br"), run_id=run.id, parent_branch_id=root.id if root else None,
                hypothesis=hyp, kind=kind, spec_json={**(b.get("spec") or {}), "_est_cost": b.get("est_cost"),
                                                     "_expected_effect": b.get("expected_effect")},
                status="proposed", priority_score=None)
    db.add(br)
    db.flush()
    emit(db, run.id, proposed_by or "experiment_designer", "branch.update",
         {"branch_id": br.id, "status": br.status, "decision": None, "decision_reason": None, "priority_score": None})
    return br


def baseline_branch(db: Session, run: Run) -> Branch | None:
    return db.scalar(select(Branch).where(Branch.run_id == run.id, Branch.parent_branch_id.is_(None))
                     .order_by(Branch.created_at).limit(1))


def create_root_branch(db: Session, run: Run, hypothesis: str = "Baseline reproduction") -> Branch:
    br = Branch(id=new_id("br"), run_id=run.id, hypothesis=hypothesis, kind="baseline", spec_json={}, status="queued")
    db.add(br)
    db.flush()
    emit(db, run.id, "executor", "branch.update", {"branch_id": br.id, "status": "queued", "decision": None,
                                                   "decision_reason": None, "priority_score": None})
    return br


def set_branch(db: Session, br: Branch, status: str, decision: str | None = None, reason: str | None = None,
               actor: str = "executor") -> None:
    br.status = status
    if decision:
        br.decision, br.decision_reason = decision, reason
    emit(db, br.run_id, actor, "branch.update", {"branch_id": br.id, "status": status, "decision": br.decision,
                                                 "decision_reason": br.decision_reason, "priority_score": br.priority_score})


def seeds_for(budget: dict) -> int:
    wall = budget.get("max_wall_min", 90)
    return 3 if wall >= 60 else 2 if wall >= 30 else 1


def _entrypoint(db: Session, run: Run, br: Branch) -> tuple[str | None, str]:
    spec = br.spec_json or {}
    if spec.get("entrypoint"):
        return spec["entrypoint"], spec.get("workdir") or "."
    impl = db.scalar(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.task_type == "implement",
                                             AgentTask.status == "done").order_by(AgentTask.ended_at.desc()).limit(1))
    if impl and impl.output_json and impl.output_json.get("entrypoints"):
        return impl.output_json["entrypoints"][0], impl.output_json.get("workdir") or "."
    return None, "."


def _argv(template: str, seed: int, budget_min: float, results_path: str, spec: dict) -> list[str]:
    spec_args = " ".join(f"--{k} {shlex.quote(str(v))}" for k, v in spec.items()
                         if k not in SPEC_SKIP and not k.startswith("_"))
    text = template.replace("{seed}", str(seed)).replace("{budget_min}", f"{budget_min:g}") \
        .replace("{results_path}", results_path).replace("{spec_args}", spec_args)
    return shlex.split(text)


def _job_for(db: Session, run: Run, task: AgentTask, exp: Experiment, br: Branch) -> Job:
    template, workdir = _entrypoint(db, run, br)
    if not template:
        raise ApiError(409, "invalid_state", "no entry point: the Implementer produced none and the branch has no spec.entrypoint")
    budget_min = exp.config_json["budget_min"]
    results_path = f"results/{exp.id}.json"
    argv = _argv(template, exp.seed or 0, budget_min, results_path, br.spec_json or {})
    jtype = "python_script" if argv and argv[0] in ("python", "python3") and len(argv) > 1 and argv[1].endswith(".py") else "shell"
    timeout = int(min(600, max(120, budget_min * 60 * 2)))
    job = create_job(db, run, jtype, {"argv": argv, "cwd": workdir, "env": {"OMP_NUM_THREADS": "2"},
                                      "results_path": results_path}, task_id=task.id, timeout_s=timeout, actor="executor")
    exp.job_id, exp.status = job.id, "running"
    exp.config_json = {**exp.config_json, "argv": argv, "cwd": workdir}
    return job


def start(db: Session, run: Run, task: AgentTask) -> None:
    """Executor service task: pick branches by scope, create experiments and jobs, then wait."""
    scope = (task.input_json or {}).get("scope", "baseline")
    if scope == "baseline":
        branches = [b for b in [baseline_branch(db, run)] if b]
    elif scope in ("baseline_suite", "exploratory"):
        kind = "baseline" if scope == "baseline_suite" else "exploratory"
        branches = list(db.scalars(select(Branch).where(Branch.run_id == run.id, Branch.kind == kind,
                                                        Branch.status.in_(("proposed", "queued")))))
    else:  # selected
        branches = list(db.scalars(select(Branch).where(Branch.run_id == run.id, Branch.status == "queued",
                                                        Branch.parent_branch_id.is_not(None))))
    # combined runs: the baseline suite runs alongside the root baseline
    if scope == "baseline":
        branches += list(db.scalars(select(Branch).where(Branch.run_id == run.id, Branch.kind == "baseline",
                                                         Branch.parent_branch_id.is_not(None),
                                                         Branch.status.in_(("proposed", "queued")))))
    n_seeds = seeds_for(run.budget_json or {})
    total = max(1, len(branches) * n_seeds)
    budget_min = round(max(0.5, min(10.0, (run.budget_json or {}).get("max_wall_min", 90) * 0.4 / total)), 2)
    task.state_json = {"branches": [b.id for b in branches]}
    if not branches:
        finish(db, run, task, "no branches to run")
        return
    try:
        for b in branches:
            set_branch(db, b, "running")
            for seed in range(n_seeds):
                exp = Experiment(id=new_id("exp"), branch_id=b.id, seed=seed, status="queued",
                                 config_json={"seed": seed, "budget_min": budget_min, "spec": b.spec_json})
                db.add(exp)
                db.flush()
                _job_for(db, run, task, exp, b)
    except ApiError as exc:
        task.status, task.error, task.ended_at = "failed", exc.message, now_iso()
        emit(db, run.id, "executor", "agent.task", {"task_id": task.id, "agent_id": None, "agent_name": "Executor",
                                                    "status": "failed", "summary": exc.message})
        return
    task.status = "waiting_for_job"
    emit(db, run.id, "executor", "agent.task", {"task_id": task.id, "agent_id": None, "agent_name": "Executor",
                                                "status": task.status, "summary": f"{len(branches)} branch(es) x {n_seeds} seed(s)"})


def _unwrap(metrics: dict) -> tuple[dict, dict]:
    """B's harness writes {"metrics": {...}, "param_count", "train_seconds", "status"}; a bare dict also works."""
    if isinstance(metrics.get("metrics"), dict):
        flat = {k: v for k, v in metrics["metrics"].items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if isinstance(metrics.get("param_count"), int):
            flat["param_count"] = metrics["param_count"]
        return flat, metrics
    return {k: v for k, v in metrics.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}, metrics


def on_job_finished(db: Session, services, job: Job) -> bool:
    """Returns True if the job belonged to an experiment."""
    exp = db.scalar(select(Experiment).where(Experiment.job_id == job.id))
    if exp is None:
        return False
    run = db.get(Run, job.run_id)
    flat, raw = _unwrap(job.metrics_json or {})
    harness_failed = raw.get("status") == "failed"
    if job.status == "done" and flat and not harness_failed:
        exp.status, exp.metrics_json = "done", flat
        exp.cost_s = raw.get("train_seconds") or None
        emit(db, run.id, "executor", "experiment.metrics", {"experiment_id": exp.id, "branch_id": exp.branch_id, "metrics": flat})
    elif job.status == "cancelled":
        exp.status = "cancelled"
    else:
        reason = "no results file" if job.status == "done" else job.status
        if exp.debug_cycles < MAX_DEBUG_CYCLES and run.status == "running":
            exp.status = "debugging"
            from .orchestrator import create_debug_task
            create_debug_task(db, services, run, job, exp, reason)
            return True
        exp.status = "failed"
    check_done(db, run, exp)
    return True


def retry_experiment(db: Session, run: Run, exp: Experiment) -> None:
    br = db.get(Branch, exp.branch_id)
    task = db.scalar(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.task_type.in_(("run_baseline", "run_branches")),
                                             AgentTask.status == "waiting_for_job").order_by(AgentTask.created_at.desc()).limit(1))
    exp.debug_cycles += 1
    if task is None:
        exp.status = "failed"
        return
    try:
        _job_for(db, run, task, exp, br)
    except ApiError:
        exp.status = "failed"
        check_done(db, run, exp)


def give_up(db: Session, run: Run, exp: Experiment) -> None:
    exp.status = "failed"
    check_done(db, run, exp)


def check_done(db: Session, run: Run, exp: Experiment) -> None:
    br = db.get(Branch, exp.branch_id)
    exps = list(db.scalars(select(Experiment).where(Experiment.branch_id == br.id)))
    if all(e.status in ("done", "failed", "cancelled") for e in exps):
        all_cancelled = all(e.status == "cancelled" for e in exps)
        set_branch(db, br, "killed" if all_cancelled else "done")
    for task in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.status == "waiting_for_job",
                                                   AgentTask.task_type.in_(("run_baseline", "run_branches")))):
        ids = (task.state_json or {}).get("branches", [])
        pending = db.scalars(select(Experiment.id).where(Experiment.branch_id.in_(ids),
                                                         Experiment.status.not_in(("done", "failed", "cancelled")))).first()
        if pending is None:
            done = db.scalars(select(Experiment.id).where(Experiment.branch_id.in_(ids), Experiment.status == "done")).first()
            finish(db, run, task, "experiments finished" if done else "every experiment failed", failed=done is None)


def finish(db: Session, run: Run, task: AgentTask, summary: str, failed: bool = False) -> None:
    task.status, task.ended_at = ("failed" if failed else "done"), now_iso()
    task.output_json = {"summary": summary}
    if failed:
        task.error = summary
    emit(db, run.id, "executor", "agent.task", {"task_id": task.id, "agent_id": None, "agent_name": "Executor",
                                                "status": task.status, "summary": summary})
