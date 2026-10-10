"""Seed registry, output schemas and examples stay consistent (AGENTS.md sections 1-5a)."""

import json

import pytest
from jsonschema import Draft202012Validator

from agents.registry import (
    REPO_ROOT,
    council_judges,
    load_model_tiers,
    load_output_schema,
    load_seed_agents,
    load_tool_registry,
)

AGENTS = load_seed_agents()
TOOLS = load_tool_registry()
TIERS = load_model_tiers()
EXAMPLES_DIR = REPO_ROOT / "shared" / "examples" / "agents"
CORE_ROLES = {"meta_controller", "evaluator", "council_judge"}


def test_roster_is_nine_agents_plus_three_judges():
    roles = [a["agent"]["role"] for a in AGENTS]
    assert len(AGENTS) == 12
    assert roles.count("council_judge") == 3
    assert len(set(roles) - {"council_judge"}) == 9


def test_ids_unique():
    ids = [a["agent"]["id"] for a in AGENTS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("record", AGENTS, ids=lambda r: r["agent"]["id"])
def test_record_is_well_formed(record):
    agent, version = record["agent"], record["version"]
    assert agent["kind"] in {"core", "seed"}
    assert agent["status"] == "active" and agent["origin"] == "seed"
    assert version["model"] in TIERS
    assert "finish" in version["tools"]
    assert version["capability_tags"]
    assert version["system_prompt"].strip()
    for tool in version["tools"]:
        assert tool in TOOLS, f"{tool} not in tool registry"
        allowed = TOOLS[tool].get("restricted_to")
        assert allowed is None or agent["role"] in allowed, f"{tool} not allowed for {agent['role']}"


@pytest.mark.parametrize("record", AGENTS, ids=lambda r: r["agent"]["id"])
def test_core_agents_are_not_evolvable(record):
    if record["agent"]["role"] in CORE_ROLES:
        assert record["agent"]["kind"] == "core"
        assert record["evolvable"] is False


def test_council_has_one_judge_per_tier():
    judges = council_judges(AGENTS)
    assert sorted(j["version"]["model"] for j in judges) == sorted(TIERS)
    for j in judges:
        assert j["council_evaluated"] is False  # judges are not judged
        assert j["counts_toward_active_cap"] is False
        assert j["version"]["tools"] == ["finish"]


def test_every_non_judge_is_council_evaluated():
    for a in AGENTS:
        if a["agent"]["role"] != "council_judge":
            assert a["council_evaluated"] is True


def test_active_cap_leaves_room_to_spawn():
    capped = [a for a in AGENTS if a["counts_toward_active_cap"]]
    assert len(capped) < 15


@pytest.mark.parametrize("record", AGENTS, ids=lambda r: r["agent"]["id"])
def test_schema_is_valid_and_example_validates(record):
    schema = load_output_schema(record["version"]["output_schema"])
    Draft202012Validator.check_schema(schema)
    example_path = EXAMPLES_DIR / f"{record['agent']['role']}.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(example))
    assert not errors, [e.message for e in errors]


def test_non_judge_schemas_require_signals():
    for a in AGENTS:
        if a["agent"]["role"] == "council_judge":
            continue
        schema = load_output_schema(a["version"]["output_schema"])
        assert "signals" in schema["required"]
        assert "suggested_next" in schema["properties"]
