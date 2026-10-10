"""M2-M4 end to end on the paper path (paper + its codebase): intake, Brief, activation, plan
approval, agent loop with suspend/resume, Executor, Evaluator, branches, report, rewards,
council, memory and the event stream. The LLM, web and Supermemory are fakes; the worker
runs over the real HTTP API."""

API = "/api/v1"


def start(ac, **body):
    body = body or {"goal": "Do KANs beat MLPs?", "inputs": [
        {"kind": "paper", "source": "url", "ref": "https://arxiv.org/abs/2404.19756"},
        {"kind": "repo", "source": "url", "ref": "https://github.com/KindXiaoming/pykan"}]}
    r = ac.post(f"{API}/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_paper_path_end_to_end(ac, driver, llm, sm):
    created = start(ac)
    run_id = created["run_id"]
    assert created["status"] == "planning"

    # Intake runs in the background; the Brief is ready after one pass.
    driver.step()
    brief = ac.get(f"{API}/runs/{run_id}/brief").json()
    assert brief["ready"] and set(brief["entry_types"]) == {"paper", "repo"}
    facts = {f["fact"] for f in brief["facts"]}
    assert "repo_links_paper" in facts and brief["domain"] == "cpu-ml"
    assert [t["type"] for t in brief["reference_targets"]] == ["paper_claim", "repo_reported"]
    act = {a["agent_id"]: a for a in brief["activation"]}
    assert len(act) == 9 and all(a["reason"] for a in act.values())
    assert act["agt_repo_auditor"]["active"] and "consistency" in act["agt_repo_auditor"]["reason"]

    # The Meta-Controller drafts a plan that waits for approval.
    driver.step()
    assert ac.get(f"{API}/runs/{run_id}").json()["status"] == "awaiting_approval"
    plan_approvals = driver.approvals(run_id)
    assert len(plan_approvals) == 1 and plan_approvals[0]["type"] == "plan"
    assert ac.get(f"{API}/runs/{run_id}/plan").json()["pending_approval"] is True

    status = driver.run(run_id)
    assert status == "done", [(t["task_type"], t["status"], t["error"]) for t in ac.get(f"{API}/runs/{run_id}/tasks").json()]

    tasks = ac.get(f"{API}/runs/{run_id}/tasks").json()
    by_type = {t["task_type"]: t for t in tasks}
    for tt in ("plan", "extract_spec", "audit_repo", "setup_env", "implement", "run_baseline", "evaluate", "design_branches",
               "select_branches", "run_branches", "evaluate_final", "decide_branches", "write_report"):
        assert by_type[tt]["status"] == "done", (tt, by_type[tt])

    # Executor: baseline x 3 seeds, then the selected branch; one branch pruned with a reason.
    tree = ac.get(f"{API}/runs/{run_id}/tree").json()
    root = tree["root"]
    assert root["hypothesis"] == "Baseline reproduction" and root["seeds"] == [0, 1, 2]
    statuses = sorted((c["status"], bool(c["decision_reason"])) for c in root["children"])
    assert statuses == [("expanded", True), ("pruned", True)]
    expanded = next(c for c in root["children"] if c["status"] == "expanded")
    assert "test_rmse" in expanded["metrics"] and "test_rmse" in expanded["delta_vs_baseline"]

    # Report built from the ledger; every ledger entry cited.
    report = ac.get(f"{API}/runs/{run_id}/report").json()
    ledger = ac.get(f"{API}/runs/{run_id}/ledger").json()
    assert report["markdown"].startswith("# Report") and len(ledger) == 2
    assert {w["ledger_entry_id"] for w in report["why_differs"]} == {e["id"] for e in ledger}

    # Rewards and the council: every agent task scored by three judges, O blended.
    judged = [t for t in tasks if t["agent_id"] and t["status"] == "done"]
    assert judged
    for t in judged:
        council = ac.get(f"{API}/tasks/{t['id']}/council").json()
        assert council["status"] == "done" and len(council["judges"]) == 3, t["task_type"]
        assert {j["tier"] for j in council["judges"]} == {"strong", "code", "fast"}
        r = ac.get(f"{API}/tasks/{t['id']}").json()["reward"]
        assert r["council_q"] == 0.8
        assert abs(r["outcome"] - (0.5 * r["outcome_det"] + 0.5 * 0.8)) < 1e-6
        assert 0 <= r["reward"] <= 1
    agents = {a["id"]: a for a in ac.get(f"{API}/agents").json()}
    assert agents["agt_paper_analyst"]["rolling_reward"] is not None

    # Judges ran on three different models, never the same tier twice for one task.
    judge_models = [c["model"] for c in llm.calls if "Performance Council" in c["messages"][0]["content"]]
    assert set(judge_models) == {"gpt-5.6-luna", "deepseek-v4-pro", "gpt-5-mini"}

    # Every request respected the gateway contract.
    for body in llm.calls:
        assert body["stream"] is False and "tools" not in body
        param = "max_tokens" if body["model"] == "deepseek-v4-pro" else "max_completion_tokens"
        assert param in body

    # Events tell the whole story.
    types = {e["type"] for e in ac.get(f"{API}/runs/{run_id}/events", params={"limit": 1000}).json()}
    for t in ("intake.brief", "agent.activation", "approval.requested", "plan.revised", "agent.task", "agent.message",
              "job.status", "experiment.metrics", "branch.update", "ledger.entry", "agent.score", "council.score",
              "report.ready", "run.status"):
        assert t in types, t

    # Transcript (the "why") is stored for each agent task.
    msgs = ac.get(f"{API}/tasks/{by_type['implement']['id']}/messages").json()
    tools = [m["tool_name"] for m in msgs if m["role"] == "tool"]
    # a worker tool appears twice: when the task suspends and when the job result resumes it
    assert tools == ["write_file", "write_file", "log_ledger", "finish"]
    assert msgs[2]["tool_result"] == {"suspended": "job", "id": msgs[2]["tool_result"]["id"]}

    # The untrusted-content rule is appended to every agent's system prompt by code.
    assert all("UNTRUSTED CONTENT RULE" in b["messages"][0]["content"] for b in llm.calls
               if "Performance Council" not in b["messages"][0]["content"])


def test_feedback_changes_reward(ac, driver):
    run_id = start(ac)["run_id"]
    driver.run(run_id)
    task = next(t for t in ac.get(f"{API}/runs/{run_id}/tasks").json() if t["task_type"] == "write_report")
    before = task["reward"]["reward"]
    up = ac.post(f"{API}/tasks/{task['id']}/feedback", json={"value": "up"}).json()
    down = ac.post(f"{API}/tasks/{task['id']}/feedback", json={"value": "down"}).json()
    assert up["reward"] > before > down["reward"] and up["feedback"] == "up"


def test_plan_rejection_replans_with_comment(ac, driver, llm):
    run_id = start(ac)["run_id"]
    driver.step()
    driver.step()
    plan = driver.approvals(run_id)[0]
    driver.decide(plan, "reject", comment="Use 2 seeds only")
    assert ac.get(f"{API}/runs/{run_id}").json()["status"] == "planning"
    driver.step()
    assert ac.get(f"{API}/runs/{run_id}").json()["status"] == "awaiting_approval"
    plan_calls = [b for b in llm.calls if b["messages"][1]["content"].startswith("# Task: plan")]
    assert "Use 2 seeds only" in plan_calls[-1]["messages"][1]["content"]


def test_plan_edit_uses_the_edited_graph(ac, driver):
    run_id = start(ac)["run_id"]
    driver.step()
    driver.step()
    plan = driver.approvals(run_id)[0]
    graph = [t for t in plan["payload"]["plan"]["tasks"] if t["task_type"] not in ("design_branches", "select_branches",
                                                                                   "run_branches", "evaluate_final", "decide_branches")]
    for t in graph:
        if t["task_type"] == "write_report":
            t["depends_on"] = ["evaluate"]
    driver.decide(plan, "edit", edited_payload={"plan": {"tasks": graph}})
    assert driver.run(run_id) == "done"
    types = {t["task_type"] for t in ac.get(f"{API}/runs/{run_id}/tasks").json()}
    assert "design_branches" not in types and "write_report" in types


def test_cancel_stops_agents_and_branches(ac, driver):
    run_id = start(ac)["run_id"]
    driver.run(run_id, until=lambda: ac.get(f"{API}/runs/{run_id}/tree").json()["roots"])
    assert ac.post(f"{API}/runs/{run_id}/cancel").json()["status"] == "cancelled"
    tasks = ac.get(f"{API}/runs/{run_id}/tasks").json()
    assert all(t["status"] in ("done", "failed", "cancelled", "skipped") for t in tasks)
