"""Agent registry routes (API.md section 6). Read-only in M0."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..models import Agent, AgentVersion
from ..rewards import rolling_reward
from ..security import current_user

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(current_user)])


class VersionSummary(BaseModel):
    id: str
    version: int
    model: str
    tools: list[str]
    capability_tags: list[str]
    reason: str | None
    parent_version_id: str | None
    created_at: str


class VersionDetail(VersionSummary):
    system_prompt: str
    output_schema: str | None
    max_steps: int


class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    kind: str
    status: str
    origin: str
    evolvable: bool
    council_evaluated: bool
    parent_ids: list[str]
    current_version: VersionSummary | None
    rolling_reward: float | None   # filled once rewards exist (M4)


def _summary(v: AgentVersion) -> VersionSummary:
    return VersionSummary(id=v.id, version=v.version, model=v.model, tools=v.tools_json,
                          capability_tags=v.capability_tags_json, reason=v.reason,
                          parent_version_id=v.parent_version_id, created_at=v.created_at)


def _agent_out(a: Agent, db: Session) -> AgentOut:
    v = db.get(AgentVersion, a.current_version_id) if a.current_version_id else None
    return AgentOut(id=a.id, name=a.name, role=a.role, kind=a.kind, status=a.status, origin=a.origin,
                    evolvable=a.evolvable, council_evaluated=a.council_evaluated,
                    parent_ids=a.parent_ids_json or [], current_version=_summary(v) if v else None,
                    rolling_reward=rolling_reward(db, a.id))


def _get_agent(agent_id: str, db: Session) -> Agent:
    a = db.get(Agent, agent_id)
    if a is None:
        raise ApiError(404, "not_found", "Agent not found")
    return a


@router.get("", response_model=list[AgentOut])
def list_agents(kind: str | None = Query(default=None, pattern="^(core|seed|spawned|template)$"),
                db: Session = Depends(get_db)) -> list[AgentOut]:
    q = select(Agent).order_by(Agent.created_at, Agent.id)
    if kind:
        q = q.where(Agent.kind == kind)
    return [_agent_out(a, db) for a in db.scalars(q)]


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentOut:
    return _agent_out(_get_agent(agent_id, db), db)


@router.get("/{agent_id}/versions", response_model=list[VersionSummary])
def list_versions(agent_id: str, db: Session = Depends(get_db)) -> list[VersionSummary]:
    _get_agent(agent_id, db)
    q = select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version)
    return [_summary(v) for v in db.scalars(q)]


@router.get("/{agent_id}/versions/{version}", response_model=VersionDetail)
def get_version(agent_id: str, version: int, db: Session = Depends(get_db)) -> VersionDetail:
    v = db.scalar(select(AgentVersion).where(AgentVersion.agent_id == agent_id, AgentVersion.version == version))
    if v is None:
        raise ApiError(404, "not_found", "Agent version not found")
    return VersionDetail(**_summary(v).model_dump(), system_prompt=v.system_prompt,
                         output_schema=v.output_schema, max_steps=v.max_steps)
