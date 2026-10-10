"""Seed the agent registry into the DB from backend/agents/seed/*.json (idempotent).

Run from backend/:  python -m app.seed
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `agents` importable

from agents.registry import load_seed_agents  # noqa: E402

from .models import Agent, AgentVersion  # noqa: E402


def seed_agents(session: Session) -> int:
    """Insert seed agents and their version 1 if missing. Returns rows inserted."""
    inserted = 0
    for record in load_seed_agents():
        a, v = record["agent"], record["version"]
        if session.get(Agent, a["id"]) is None:
            session.add(Agent(
                id=a["id"], name=a["name"], role=a["role"], kind=a["kind"], status=a["status"],
                origin=a["origin"], parent_ids_json=[], evolvable=record["evolvable"],
                council_evaluated=record["council_evaluated"],
                counts_toward_active_cap=record["counts_toward_active_cap"],
            ))
            inserted += 1
        version_id = f"agv_{a['id'].removeprefix('agt_')}_v{v['version']}"
        exists = session.scalar(select(AgentVersion.id).where(AgentVersion.id == version_id))
        if exists is None:
            session.add(AgentVersion(
                id=version_id, agent_id=a["id"], version=v["version"], system_prompt=v["system_prompt"],
                tools_json=v["tools"], capability_tags_json=v["capability_tags"], model=v["model"],
                output_schema=v["output_schema"], max_steps=record["max_steps"], reason=v["reason"],
                parent_version_id=v["parent_version_id"],
            ))
            inserted += 1
        session.flush()
        agent = session.get(Agent, a["id"])
        if agent.current_version_id is None:
            agent.current_version_id = version_id
    session.commit()
    return inserted


if __name__ == "__main__":
    from .config import get_settings
    from .db import Database

    db = Database(get_settings().database_url)
    with db.sessionmaker() as s:
        print(f"seeded {seed_agents(s)} rows")
