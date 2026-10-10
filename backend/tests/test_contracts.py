"""M0 contract checks: migrations match models, events are append-only, OpenAPI file is current,
tag vocabulary covers every agent, activation examples reference real agents."""

import json
import subprocess
import sys

import pytest
from conftest import BACKEND, migrate

REPO = BACKEND.parent
TAGS = set(json.loads((BACKEND / "agents" / "tags.json").read_text(encoding="utf-8"))["tags"])


def test_migrations_match_models(tmp_path):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    migrate(url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    command.check(cfg)  # raises if models drifted from migrations


def test_events_are_append_only(app):
    from app.models import AppendOnlyError, Event

    with app.state.db.sessionmaker() as s:
        e = Event(run_id=None, actor="test", type="run.status", payload_json={"status": "planning"})
        s.add(e)
        s.commit()
        e.type = "changed"
        with pytest.raises(AppendOnlyError):
            s.commit()
        s.rollback()
        s.delete(s.get(Event, e.id))
        with pytest.raises(AppendOnlyError):
            s.commit()


def test_openapi_file_is_current():
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "export_openapi.py"), "--check"],
                       capture_output=True, text=True, cwd=BACKEND)
    assert r.returncode == 0, r.stdout + r.stderr


def test_seed_tags_are_in_vocabulary():
    from agents.registry import load_seed_agents

    for a in load_seed_agents():
        assert set(a["version"]["capability_tags"]) <= TAGS, a["agent"]["id"]


@pytest.mark.parametrize("name", ["paper", "repo", "dataset", "question", "combined"])
def test_activation_examples(name):
    from agents.registry import load_seed_agents

    ex = json.loads((REPO / "shared" / "examples" / "activation" / f"{name}.json").read_text(encoding="utf-8"))
    working = {a["agent"]["id"] for a in load_seed_agents() if a["agent"]["role"] != "council_judge"}
    listed = [row["agent_id"] for row in ex["activation"]]
    assert sorted(listed) == sorted(working)  # every working agent appears once, with a reason
    assert all(row["reason"] for row in ex["activation"])
    assert set(ex["entry_types"]) <= {"paper", "question", "repo", "dataset"}
    for gap in ex["capability_gaps"]:
        assert set(gap["required_tags"]) <= TAGS
