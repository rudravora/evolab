"""M3-M4: Debugger and verified memory, memory reuse in a second run, the resolution ladder
(specialise on a runtime gap, fresh spawn on a planning gap), evolution approvals, probation
and refine triggers."""

from conftest import API
from test_paper_path import start

PYKAN_ERR = "AttributeError: 'KAN' object has no attribute 'train' (pykan 0.2.8)"


def tasks_of(ac, run_id, tt=None):
    ts = ac.get(f"{API}/runs/{run_id}/tasks").json()
    return [t for t in ts if tt is None or t["task_type"] == tt]


def test_debugger_fixes_and_writes_verified_memory_then_reused(ac, driver, sm):
    driver.w.fail_experiments, driver.w.fail_text = 1, PYKAN_ERR
    run_id = start(ac)["run_id"]
    assert driver.run(run_id) == "done"
    debug = tasks_of(ac, run_id, "debug")
    assert len(debug) == 1 and debug[0]["status"] == "done"
    detail = ac.get(f"{API}/tasks/{debug[0]['id']}").json()
    assert detail["output"]["fixed"] is True and detail["failure_origin_agent_id"] == "agt_implementer"

    # the lesson is verified (written after the re-run passed), labelled learned, mirrored to Supermemory
    mem = ac.get(f"{API}/memory", params={"kind": "error_fix"}).json()["entries"]
    assert len(mem) == 1 and mem[0]["source"] == "learned" and mem[0]["mirrored"]
    assert sm.docs and sm.docs[0]["metadata"]["kind"] == "error_fix"

    # the blamed agent loses outcome score
    impl = tasks_of(ac, run_id, "implement")[0]
    assert impl["reward"]["outcome_det"] <= 0.8 + 1e-9

    # second run: the same failure retrieves the learned fix
    driver.w.fail_experiments = 1
    run2 = start(ac)["run_id"]
    assert driver.run(run2) == "done"
    hits = [e for e in ac.get(f"{API}/runs/{run2}/events", params={"limit": 1000}).json() if e["type"] == "memory.hit"]
    assert any(h["payload"]["entry_id"] == mem[0]["id"] and h["payload"]["source"] == "learned" for h in hits)
    # deduped by signature: the second verified write increments the counter
    again = ac.get(f"{API}/memory/{mem[0]['id']}").json()
    assert again["success_count"] >= 2


def test_runtime_gap_specialises_the_debugger(ac, driver, llm):
    llm.debug_fixes = False
    driver.w.fail_experiments, driver.w.fail_text = 3, PYKAN_ERR
    run_id = start(ac)["run_id"]
    driver.run(run_id, approve=("plan",))
    evo = [a for a in driver.approvals(run_id) if a["type"] == "evolution"]
    assert len(evo) == 1, driver.approvals(run_id)
    p = evo[0]["payload"]
    assert p["ladder_step"] == "specialise" and p["gap"]["required_tags"] == ["debug:python", "lib:pykan"]
    assert p["proposed_agent"]["name"] == "KAN API Specialist"
    assert set(p["proposed_agent"]["capability_tags"]) >= {"debug:python", "debug:deps", "lib:pykan"}
    assert "spawn_agent" not in p["proposed_agent"]["tools"] and "finish" in p["proposed_agent"]["tools"]
    assert p["lineage"] == "specialised from agt_debugger" and p["probation_tasks"] == 2

    driver.decide(evo[0])
    graph = ac.get(f"{API}/runs/{run_id}/agent-graph").json()
    spec = next(n for n in graph["nodes"] if n["name"] == "KAN API Specialist")
    assert spec["kind"] == "spawned" and spec["origin"] == "specialised:agt_debugger"
    assert {"from": "agt_debugger", "to": spec["id"], "kind": "specialised-from"} in graph["edges"]
    events = ac.get(f"{API}/runs/{run_id}/events", params={"limit": 1000}).json()
    evo_ev = [e for e in events if e["type"] == "agent.evolution"]
    assert evo_ev and evo_ev[-1]["payload"]["action"] == "spawn" and evo_ev[-1]["payload"]["ladder_step"] == "specialise"
    assert any(e["type"] == "capability.gap" and e["payload"]["source"] == "runtime" for e in events)

    # the next pykan failure is routed to the specialist, which then sits in probation
    llm.debug_fixes = True
    driver.w.fail_experiments = 1
    run2 = start(ac)["run_id"]
    assert driver.run(run2) == "done"
    debug2 = tasks_of(ac, run2, "debug")
    assert debug2 and debug2[0]["agent_id"] == spec["id"]
    versions = ac.get(f"{API}/agents/{spec['id']}").json()
    assert versions["status"] == "active"


def test_planning_gap_fresh_spawn_on_dataset_path(ac, driver):
    run_id = start(ac, goal="Baselines for this table?", inputs=[
        {"kind": "dataset", "source": "url", "ref": "https://example.org/housing.csv"}])["run_id"]
    driver.run(run_id, approve=("plan",), until=lambda: any(a["type"] == "evolution" for a in driver.approvals(run_id)))
    evo = next(a for a in driver.approvals(run_id) if a["type"] == "evolution")
    assert evo["payload"]["ladder_step"] == "fresh_spawn"
    assert evo["payload"]["gap"]["required_tags"] == ["bench:tabular-protocol"]
    assert evo["payload"]["lineage"] == "fresh"
    gap_task = next(t for t in tasks_of(ac, run_id) if t["task_type"] == "design_baseline_suite")
    assert gap_task["agent_id"] is None and gap_task["status"] == "blocked"

    driver.decide(evo)
    assert driver.run(run_id) == "done"
    gap_task = next(t for t in tasks_of(ac, run_id) if t["task_type"] == "design_baseline_suite")
    agent = ac.get(f"{API}/agents/{gap_task['agent_id']}").json()
    assert agent["name"] == "Tabular Benchmark Protocol" and agent["origin"] == "fresh" and agent["role"] == "experiment_designer"
    assert gap_task["status"] == "done"
    tree = ac.get(f"{API}/runs/{run_id}/tree").json()
    assert any(r["kind"] == "baseline" for r in tree["roots"])


def test_rejected_evolution_skips_the_gap_task_and_replans(ac, driver):
    run_id = start(ac, goal="Baselines?", inputs=[{"kind": "dataset", "source": "url", "ref": "https://example.org/d.csv"}])["run_id"]
    driver.run(run_id, approve=("plan",), until=lambda: any(a["type"] == "evolution" for a in driver.approvals(run_id)))
    evo = next(a for a in driver.approvals(run_id) if a["type"] == "evolution")
    driver.decide(evo, "reject", comment="not now")
    gap_task = next(t for t in tasks_of(ac, run_id) if t["task_type"] == "design_baseline_suite")
    assert gap_task["status"] == "skipped"
    assert any(t["task_type"] == "replan" for t in tasks_of(ac, run_id))


def test_refine_trigger_and_probation_rollback(agent_app, ac, driver, llm):
    """Low rewards with a repeated failure pattern -> refine proposal with a prompt diff ->
    approved -> new version on probation -> worse again -> rolled back to the parent version."""
    from app import evolution
    from app.models import Agent, AgentTask, AgentVersion

    llm.judge_overall = 0.0
    run_id = start(ac)["run_id"]
    assert driver.run(run_id) == "done"
    sm_ = agent_app.state.db.sessionmaker
    with sm_() as db:
        agent = db.get(Agent, "agt_reporter")
        # three poor reporter tasks with the same council failure pattern
        for t in db.query(AgentTask).filter(AgentTask.agent_id == "agt_reporter").all():
            t.reward = 0.2
            t.state_json = {**(t.state_json or {}), "council_pattern": "ignored ledger entries"}
        for i in range(2):
            db.add(AgentTask(id=f"tsk_fake{i}", run_id=run_id, task_type="write_report", agent_id="agt_reporter",
                             status="done", reward=0.2, ended_at=f"2026-10-10T10:0{i}:00.000Z",
                             state_json={"council_pattern": "ignored ledger entries"}))
        db.commit()
        t = db.get(AgentTask, "tsk_fake1")
        evolution._triggers(db, agent_app.state.services, t, agent)
        db.commit()
    driver.step()
    evo = [a for a in driver.approvals(run_id) if a["type"] == "evolution"]
    assert len(evo) == 1 and evo[0]["payload"]["action"] == "refine"
    assert evo[0]["payload"]["prompt_diff"].startswith("--- current")
    driver.decide(evo[0])
    with sm_() as db:
        agent = db.get(Agent, "agt_reporter")
        v2 = db.get(AgentVersion, agent.current_version_id)
        assert v2.version == 2 and v2.probation_json["kind"] == "refine"
        for i in range(2):
            t = AgentTask(id=f"tsk_prob{i}", run_id=run_id, task_type="write_report", agent_id="agt_reporter",
                          agent_version_id=v2.id, status="done", reward=0.1, ended_at=f"2026-10-10T11:0{i}:00.000Z")
            db.add(t)
            db.flush()
            evolution._probation(db, t, agent)
        db.commit()
        agent = db.get(Agent, "agt_reporter")
        assert db.get(AgentVersion, agent.current_version_id).version == 1       # rolled back
        assert db.get(AgentVersion, v2.id).probation_json["result"] == "failed"


def test_core_agents_never_evolve(agent_app, ac, driver):
    from app import evolution
    from app.models import Agent, AgentTask

    run_id = start(ac)["run_id"]
    driver.run(run_id)
    with agent_app.state.db.sessionmaker() as db:
        t = db.query(AgentTask).filter(AgentTask.agent_id == "agt_evaluator").first()
        for x in db.query(AgentTask).filter(AgentTask.agent_id == "agt_evaluator").all():
            x.reward = 0.0
        evolution.after_task(db, agent_app.state.services, t)
        db.commit()
        assert db.get(Agent, "agt_evaluator").status == "active"
    assert not [a for a in driver.approvals(run_id) if a["type"] == "evolution"]
