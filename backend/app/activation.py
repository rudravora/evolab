"""Activation rules and plan fragments (AGENTS.md 4a and 4b, ARCHITECTURE 3.0b, D-031).

Deterministic: Brief facts -> which agents are active (with a reason for every agent,
including inactive ones) -> a draft task graph joined from per-entry-type fragments.
The Meta-Controller then adapts the draft and must write a reason for every change.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .ladder import best_agent

WORKING_AGENTS = ["agt_paper_analyst", "agt_repo_auditor", "agt_env_data_engineer", "agt_implementer",
                  "agt_experiment_designer", "agt_meta_controller", "agt_evaluator", "agt_reporter", "agt_debugger"]

# task_type -> (default role, required tags). Service tasks have no role.
TASK_TYPES: dict[str, tuple[str | None, list[str]]] = {
    "extract_spec": ("paper_analyst", ["paper:extract"]),
    "find_candidates": ("paper_analyst", ["paper:search"]),
    "search_baselines": ("paper_analyst", ["baseline:search"]),
    "audit_repo": ("repo_auditor", ["repo:audit", "repo:smoke-test"]),
    "setup_env": ("env_data_engineer", ["env:setup"]),
    "implement": ("implementer", ["code:patch"]),
    "design_exploratory": ("experiment_designer", ["design:exploratory"]),
    # Only the protocol tag: no seed agent has it and nothing covers it broadly, so the ladder ends at a
    # fresh spawn (D-035). Output uses the Experiment Designer schema (baseline-kind branches).
    "design_baseline_suite": ("experiment_designer", ["bench:tabular-protocol"]),
    "run_baseline": (None, []),
    "evaluate": ("evaluator", ["eval:stats", "eval:verdict"]),
    "design_branches": ("experiment_designer", ["design:whatif"]),
    "select_branches": ("meta_controller", ["plan"]),
    "run_branches": (None, []),
    "evaluate_final": ("evaluator", ["eval:stats", "eval:verdict"]),
    "decide_branches": ("meta_controller", ["replan"]),
    "write_report": ("reporter", ["report:write"]),
    "debug": ("debugger", ["debug:python"]),
}
SERVICE_TASKS = {"run_baseline", "run_branches"}


def _facts(brief: dict) -> set[str]:
    return {f["fact"] for f in brief.get("facts", [])}


def activation(brief: dict) -> list[dict]:
    kinds = set(brief.get("entry_types", []))
    facts = _facts(brief)
    paper, repo, data, question = ("paper" in kinds), ("repo" in kinds), ("dataset" in kinds), ("question" in kinds)
    rows: list[tuple[str, bool, str]] = []

    if paper:
        rows.append(("agt_paper_analyst", True, "paper supplied" + ("; candidate search not required: paper supplied" if question else "")))
    elif question:
        rows.append(("agt_paper_analyst", True, "question, no paper: find 3-5 candidate papers"))
    elif data:
        rows.append(("agt_paper_analyst", True, "dataset path: search published baselines"))
    else:
        rows.append(("agt_paper_analyst", False, "not required yet: activated if the README links a paper"))

    if repo:
        reason = "paper + its own codebase: consistency check and mode" if "repo_links_paper" in facts else "codebase supplied"
        rows.append(("agt_repo_auditor", True, reason))
    else:
        rows.append(("agt_repo_auditor", False, "not required: no codebase supplied"))

    if data:
        rows.append(("agt_env_data_engineer", True, "dataset supplied: profile and leakage check"))
    else:
        rows.append(("agt_env_data_engineer", True, "environment setup for the experiments"))

    if repo and data:
        rows.append(("agt_implementer", True, "codebase + dataset: adapt the code to the new data"))
    elif paper or repo:
        rows.append(("agt_implementer", True, "patch or implement the method so it runs on CPU"))
    elif question:
        rows.append(("agt_implementer", True, "exploratory branch: write the experiment scripts"))
    else:
        rows.append(("agt_implementer", False, "not required: baseline scripts are run directly"))

    designer = []
    if question and not paper:
        designer.append("question, no paper: open the exploratory branch")
    if paper and data and "dataset_not_in_paper" in facts:
        designer.append("paper + different dataset: transfer what-if")
    if question and (paper or repo):
        designer.append("question frames the what-if branches")
    if data and not paper:
        designer.append("dataset path: baseline suite")
    rows.append(("agt_experiment_designer", True, "; ".join(designer) or "what-if branches"))

    rows += [("agt_meta_controller", True, "every run"), ("agt_evaluator", True, "every run"),
             ("agt_reporter", True, "every run"), ("agt_debugger", True, "on demand: woken by failed jobs")]
    return [{"agent_id": a, "active": on, "reason": r} for a, on, r in rows]


def _task(key: str, ttype: str, deps: list[str], **inp) -> dict:
    return {"task_id": key, "task_type": ttype, "agent_id": None, "required_tags": list(TASK_TYPES[ttype][1]),
            "depends_on": deps, "input": inp}


def draft_graph(brief: dict) -> list[dict]:
    """Join per-entry-type fragments (AGENTS.md 4b) into one graph."""
    kinds = set(brief.get("entry_types", []))
    facts = _facts(brief)
    paper, repo, data, question = ("paper" in kinds), ("repo" in kinds), ("dataset" in kinds), ("question" in kinds)
    question_only = question and not paper and not repo
    g: list[dict] = []
    head: list[str] = []

    if paper:
        g.append(_task("extract_spec", "extract_spec", [], mode="paper"))
        head = ["extract_spec"]
    if question_only:
        g.append(_task("find_candidates", "find_candidates", [], mode="question"))
        g.append(_task("design_exploratory", "design_exploratory", [], kind="exploratory"))
        head = ["design_exploratory"]
    if repo:
        g.append(_task("audit_repo", "audit_repo", list(head), paper_linked="repo_links_paper" in facts))
        head = ["audit_repo"]

    g.append(_task("setup_env", "setup_env", list(head), profile_dataset=data))
    if data:
        g[-1]["required_tags"] += ["data:profile:tabular", "data:leakage-check"]
    env = ["setup_env"]

    run_deps: list[str] = []
    if data:
        if not paper and not repo:
            g.append(_task("search_baselines", "search_baselines", env, mode="baselines"))
            g.append(_task("design_baseline_suite", "design_baseline_suite", ["search_baselines"], kind="baseline"))
        else:
            g.append(_task("design_baseline_suite", "design_baseline_suite", env, kind="baseline"))
        run_deps.append("design_baseline_suite")
    if paper or repo or question_only:
        impl = _task("implement", "implement", env, mode="A")
        if repo and data:
            impl["required_tags"] = ["code:adapt-data"]
        g.append(impl)
        run_deps.append("implement")

    g.append(_task("run_baseline", "run_baseline", run_deps,
                   scope="exploratory" if question_only else ("baseline_suite" if not (paper or repo) else "baseline")))
    g.append(_task("evaluate", "evaluate", ["run_baseline"]))
    transfer = paper and data and "dataset_not_in_paper" in facts
    g.append(_task("design_branches", "design_branches", ["evaluate"], transfer=transfer, question_frames=question))
    g.append(_task("select_branches", "select_branches", ["design_branches"]))
    g.append(_task("run_branches", "run_branches", ["select_branches"], scope="selected"))
    g.append(_task("evaluate_final", "evaluate_final", ["run_branches"]))
    g.append(_task("decide_branches", "decide_branches", ["evaluate_final"]))
    g.append(_task("write_report", "write_report", ["decide_branches"]))
    return g


def assign(db: Session, graph: list[dict], active_ids: set[str]) -> list[dict]:
    """Reuse step of the ladder: give each task the best active agent covering its tags, or leave a gap."""
    for t in graph:
        if t["task_type"] in SERVICE_TASKS:
            t["agent_id"] = None
            continue
        if t.get("agent_id") and t["agent_id"] in active_ids:
            continue
        agent = best_agent(db, set(t["required_tags"]), only_ids=active_ids)
        t["agent_id"] = agent.id if agent else None
    return graph


def gaps(graph: list[dict]) -> list[dict]:
    return [{"task_id": t["task_id"], "required_tags": t["required_tags"]} for t in graph
            if t["task_type"] not in SERVICE_TASKS and not t.get("agent_id")]


def validate_graph(graph: list[dict], db: Session) -> str | None:
    from .models import Agent

    keys = [t.get("task_id") for t in graph]
    if len(keys) != len(set(keys)) or not all(keys):
        return "task ids must be unique and non-empty"
    for t in graph:
        if t.get("task_type") not in TASK_TYPES:
            return f"unknown task_type {t.get('task_type')!r}"
        for d in t.get("depends_on", []):
            if d not in keys:
                return f"{t['task_id']} depends on unknown task {d}"
        if t.get("agent_id") and db.get(Agent, t["agent_id"]) is None:
            return f"{t['task_id']}: unknown agent {t['agent_id']}"
    # cycle check
    deps = {t["task_id"]: set(t.get("depends_on", [])) for t in graph}
    done: set[str] = set()
    while deps:
        ready = [k for k, v in deps.items() if v <= done]
        if not ready:
            return f"dependency cycle among {sorted(deps)}"
        for k in ready:
            done.add(k)
            deps.pop(k)
    return None
