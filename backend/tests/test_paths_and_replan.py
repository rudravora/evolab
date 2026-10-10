"""M3-M4: all four entry paths plan, the question path's candidate pick, re-planning on signals
and chat (minor vs major diffs), the budget trigger, and the council with a failing judge."""

import pytest

from conftest import API
from test_evolution import tasks_of
from test_paper_path import start

PATHS = {
    "paper": [{"kind": "paper", "source": "url", "ref": "https://arxiv.org/abs/2404.19756"}],
    "repo": [{"kind": "repo", "source": "url", "ref": "https://github.com/KindXiaoming/pykan"}],
    "dataset": [{"kind": "dataset", "source": "url", "ref": "https://example.org/housing.csv"}],
    "question": [{"kind": "question", "source": "text", "ref": "Do KANs beat MLPs on tabular data?"}],
    "combined": [{"kind": "paper", "source": "url", "ref": "https://arxiv.org/abs/2404.19756"},
                 {"kind": "repo", "source": "url", "ref": "https://github.com/KindXiaoming/pykan"},
                 {"kind": "dataset", "source": "url", "ref": "https://example.org/housing.csv"},
                 {"kind": "question", "source": "text", "ref": "Do KANs beat parameter-matched MLPs on real tabular data?"}],
}


@pytest.mark.parametrize("path", sorted(PATHS))
def test_every_entry_path_produces_an_approvable_plan(ac, driver, path):
    run_id = start(ac, goal="Study this?", inputs=PATHS[path])["run_id"]
    driver.step()
    driver.step()
    plans = [a for a in driver.approvals(run_id) if a["type"] == "plan"]
    assert len(plans) == 1, path
    graph = plans[0]["payload"]["plan"]["tasks"]
    types = {t["task_type"] for t in graph}
    assert {"run_baseline", "evaluate", "write_report"} <= types
    expected = {"paper": {"extract_spec", "implement"}, "repo": {"audit_repo", "implement"},
                "dataset": {"search_baselines", "design_baseline_suite"},
                "question": {"find_candidates", "design_exploratory", "implement"},
                "combined": {"extract_spec", "audit_repo", "design_baseline_suite", "implement"}}[path]
    assert expected <= types, (path, types)
    if path == "combined":
        brief = ac.get(f"{API}/runs/{run_id}/brief").json()
        facts = {f["fact"] for f in brief["facts"]}
        assert {"repo_links_paper", "dataset_not_in_paper", "question_about_paper"} <= facts
        design = next(t for t in graph if t["task_type"] == "design_branches")
        assert design["input"]["transfer"] is True
        assert plans[0]["payload"]["plan"]["gaps"] == [{"task_id": "design_baseline_suite",
                                                        "required_tags": ["bench:tabular-protocol"]}]
    if path == "question":
        assert "find_candidates" in types and "extract_spec" not in types


def test_question_path_candidate_pick_adds_the_paper(ac, driver):
    run_id = start(ac, goal="Do KANs beat MLPs?", inputs=PATHS["question"])["run_id"]
    driver.run(run_id, until=lambda: any(a["type"] == "candidate_selection" for a in driver.approvals(run_id)))
    pick = next(a for a in driver.approvals(run_id) if a["type"] == "candidate_selection")
    assert len(pick["payload"]["candidates"]) == 3
    events = [e["type"] for e in ac.get(f"{API}/runs/{run_id}/events", params={"limit": 1000}).json()]
    assert "candidates.ready" in events
    driver.decide(pick, "edit", edited_payload={"chosen": 1})
    assert driver.run(run_id) == "done"
    chosen = [t for t in tasks_of(ac, run_id) if t["graph_key"] == "extract_spec_chosen"]
    assert chosen and chosen[0]["status"] == "done"
    targets = ac.get(f"{API}/runs/{run_id}/brief").json()["reference_targets"]
    assert targets[0]["type"] == "paper_claim"
    revisions = ac.get(f"{API}/runs/{run_id}/plan/revisions").json()
    assert any(r["trigger"] == "candidate_selection" and r["kind"] == "minor" for r in revisions)
    tree = ac.get(f"{API}/runs/{run_id}/tree").json()
    assert any(r["kind"] == "exploratory" for r in tree["roots"])     # the exploratory branch ran alongside


def test_signals_trigger_a_minor_replan_that_applies_at_once(ac, driver, llm):
    llm.env_signals = [{"signal": "data_issue", "evidence": "column id is monotonic with the target"}]
    llm.replan_diff = {"add_tasks": [{"task_id": "fix_leak", "task_type": "setup_env", "agent_id": None,
                                      "required_tags": ["env:setup"], "depends_on": ["setup_env"],
                                      "input": {"fix": "drop the id column"}}]}
    run_id = start(ac)["run_id"]
    assert driver.run(run_id) == "done"
    revisions = ac.get(f"{API}/runs/{run_id}/plan/revisions").json()
    minor = [r for r in revisions if r["kind"] == "minor"]
    assert minor and minor[0]["trigger"] == "signals" and minor[0]["diff"]["add_tasks"] == ["fix_leak"]
    fix = next(t for t in tasks_of(ac, run_id) if t["graph_key"] == "fix_leak")
    assert fix["agent_id"] == "agt_env_data_engineer" and fix["status"] == "done"
    replan = next(t for t in tasks_of(ac, run_id, "replan"))
    assert ac.get(f"{API}/tasks/{replan['id']}").json()["input"]["trigger"]["type"] == "signals"


def test_major_replan_needs_approval(ac, driver, llm):
    llm.env_signals = [{"signal": "new_target", "evidence": "README reports numbers"}]
    llm.replan_diff = {"targets_added": [{"type": "repo_reported", "source": "readme"}], "activate": ["agt_repo_auditor"]}
    run_id = start(ac)["run_id"]
    driver.run(run_id, approve=(), until=lambda: bool(driver.approvals(run_id)))
    driver.decide(driver.approvals(run_id)[0])                     # the initial plan
    driver.run(run_id, approve=(), until=lambda: any(a["type"] == "plan" for a in driver.approvals(run_id)))
    major = next(a for a in driver.approvals(run_id) if a["type"] == "plan")
    assert major["payload"]["initial"] is False
    assert major["payload"]["trigger"] == "signals" and major["payload"]["diff"]["activate"] == ["agt_repo_auditor"]
    driver.decide(major)
    revisions = ac.get(f"{API}/runs/{run_id}/plan/revisions").json()
    assert any(r["kind"] == "major" and r["approval_id"] == major["id"] for r in revisions)


def test_chat_reaches_the_meta_controller_and_gets_a_reply(ac, driver):
    run_id = start(ac)["run_id"]
    driver.run(run_id, until=lambda: ac.get(f"{API}/runs/{run_id}").json()["status"] == "running")
    r = ac.post(f"{API}/runs/{run_id}/chat", json={"message": "try noisy data"})
    assert r.status_code == 202
    driver.step()
    chat = ac.get(f"{API}/runs/{run_id}/chat").json()
    assert [m["role"] for m in chat] == ["researcher", "meta_controller"]
    assert chat[1]["content"] == "Handled the trigger."


def test_chat_is_rate_limited_per_run(ac, driver):
    run_id = start(ac)["run_id"]
    codes = [ac.post(f"{API}/runs/{run_id}/chat", json={"message": f"m{i}"}).status_code for i in range(21)]
    assert codes[:20] == [202] * 20 and codes[20] == 429


def test_budget_warning_triggers_replan(agent_app, ac, driver):
    run_id = start(ac, goal="KAN?", inputs=PATHS["paper"], budget={"max_wall_min": 90, "max_tokens": 1000})["run_id"]
    driver.run(run_id, max_steps=30)
    events = ac.get(f"{API}/runs/{run_id}/events", params={"limit": 1000}).json()
    warn = [e for e in events if e["type"] == "budget.warning"]
    assert warn and warn[0]["payload"]["metric"] == "tokens"
    assert any((ac.get(f"{API}/tasks/{t['id']}").json()["input"]["trigger"] or {}).get("type") == "budget"
               for t in tasks_of(ac, run_id, "replan"))


def test_council_with_one_failing_judge_uses_the_mean_of_two(ac, driver, llm):
    llm.judge_fail_tiers = {"fast"}
    run_id = start(ac)["run_id"]
    assert driver.run(run_id) == "done"
    t = next(t for t in tasks_of(ac, run_id, "extract_spec"))
    council = ac.get(f"{API}/tasks/{t['id']}/council").json()
    assert len(council["judges"]) == 2 and council["q"] == 0.8
    assert {j["tier"] for j in council["judges"]} == {"strong", "code"}


def test_council_off_uses_deterministic_outcome(agent_settings, llm, sm, tmp_path):
    from fastapi.testclient import TestClient

    from conftest import OWNER_PASSWORD, Driver, build_app
    from fakes import FakeWeb, SimWorker
    agent_settings.feature_council = False
    app = build_app(agent_settings, transport=llm, web=FakeWeb(), supermemory=sm)
    with TestClient(app) as c:
        c.post(f"{API}/auth/login", json={"password": OWNER_PASSWORD})
        d = Driver(app, c, SimWorker(c))
        run_id = start(c)["run_id"]
        assert d.run(run_id) == "done"
        t = next(t for t in tasks_of(c, run_id, "extract_spec"))
        assert t["reward"]["council_q"] is None and t["reward"]["outcome"] == t["reward"]["outcome_det"]
    assert not any("Performance Council" in b["messages"][0]["content"] for b in llm.calls)



def test_rate_limited_judges_are_retried_later_not_dropped(agent_app, ac, driver, llm, monkeypatch):
    import app.llm as llm_mod
    from app.models import AgentTask
    monkeypatch.setattr(llm_mod, "RETRY_DELAYS_S", (0, 0, 0))
    run_id = start(ac)["run_id"]
    driver.step()                                  # intake

    def gate(body, headers, timeout):              # the code-tier judge is rate limited
        if body["model"] == "deepseek-v4-pro" and "Performance Council" in body["messages"][0]["content"]:
            return 429, {"error": "rate limited"}
        return llm(body, headers, timeout)
    driver.services().llm.transport = gate
    driver.step()                                  # plan, then council for the plan task
    driver.step()
    plan = next(t for t in tasks_of(ac, run_id, "plan"))
    council = ac.get(f"{API}/tasks/{plan['id']}/council").json()
    assert council["status"] == "pending" and {j["tier"] for j in council["judges"]} == {"strong", "fast"}

    driver.services().llm.transport = llm          # limits lifted; make the retry due now
    with agent_app.state.db.sessionmaker() as db:
        t = db.get(AgentTask, plan["id"])
        t.state_json = {**t.state_json, "council_retry_at": 0}
        db.commit()
    driver.step()
    council = ac.get(f"{API}/tasks/{plan['id']}/council").json()
    assert council["status"] == "done" and len(council["judges"]) == 3 and council["q"] == 0.8
