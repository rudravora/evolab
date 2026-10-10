"""Capability matching and the resolution ladder (ARCHITECTURE 3.10, AGENTS.md 6a, D-033).

An agent matches a task when its current version's tags cover all required tags; ties
go to the higher rolling reward. Ladder, cheapest first: 1 reuse an active agent;
2 restore an inactive/retired one with rolling reward >= 0.5; 3 instantiate a dormant
template; 4 specialise a broad agent; 5 fresh spawn.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Agent, AgentVersion

SPECIFIC_PREFIXES = ("lib:", "bench:", "domain:")
MAX_ACTIVE = 15


def tags_of(db: Session, agent: Agent) -> set[str]:
    v = db.get(AgentVersion, agent.current_version_id) if agent.current_version_id else None
    return set(v.capability_tags_json) if v else set()


def covering_agents(db: Session, required: set[str], *, include_inactive: bool = False) -> list[Agent]:
    q = select(Agent).where(Agent.role != "council_judge")
    if not include_inactive:
        q = q.where(Agent.status == "active")
    return [a for a in db.scalars(q) if required <= tags_of(db, a)]


def best_agent(db: Session, required: set[str], only_ids: set[str] | None = None) -> Agent | None:
    from .rewards import rolling_reward

    cands = [a for a in covering_agents(db, required) if only_ids is None or a.id in only_ids or a.kind == "spawned"]
    if not cands:
        return None
    return max(cands, key=lambda a: (rolling_reward(db, a.id) or 0.5, a.kind == "spawned"))


def active_count(db: Session) -> int:
    return sum(1 for a in db.scalars(select(Agent).where(Agent.status == "active")) if a.counts_toward_active_cap)


@dataclass
class LadderResult:
    step: str                       # reuse | restore | instantiate_template | specialise | fresh_spawn
    agent: Agent | None = None      # agent reused/restored, template, or parent to specialise
    note: str = ""


def walk(db: Session, required: set[str]) -> LadderResult:
    from .rewards import rolling_reward

    active = covering_agents(db, required)
    if active:
        return LadderResult("reuse", best_agent(db, required), "an active agent covers the tags")
    for a in db.scalars(select(Agent).where(Agent.status.in_(("inactive", "retired")))):
        if required <= tags_of(db, a) and (rolling_reward(db, a.id) or 0) >= 0.5:
            return LadderResult("restore", a, f"{a.name} covers the tags and had rolling reward >= 0.5")
    for a in db.scalars(select(Agent).where(Agent.kind == "template", Agent.status == "dormant")):
        if required <= tags_of(db, a):
            return LadderResult("instantiate_template", a, f"dormant template {a.name} covers the tags")
    general = {t for t in required if not t.startswith(SPECIFIC_PREFIXES)}
    if general and len(general) < len(required):
        broad = [a for a in covering_agents(db, general) if a.kind in ("seed", "spawned") and a.evolvable]
        if broad:
            parent = max(broad, key=lambda a: rolling_reward(db, a.id) or 0.5)
            return LadderResult("specialise", parent,
                                f"{parent.name} covers {sorted(general)} broadly; specialise for {sorted(required - general)}")
    return LadderResult("fresh_spawn", None, "no active, retired or template agent covers the tags")
