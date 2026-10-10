"""Service container shared by routes, the orchestrator and tools. Tests build it with fakes
(LLM transport, web, Supermemory) so nothing reaches the network."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .librarian import Librarian
from .llm import LLMClient
from .n8n import Notifier
from .supermemory import Supermemory
from .tracing import NoopTracer, make_tracer
from .web import Web


@dataclass
class Services:
    settings: Settings
    sessionmaker: sessionmaker
    llm: LLMClient
    tracer: NoopTracer
    web: Web
    librarian: Librarian
    notifier: Notifier
    extras: dict = field(default_factory=dict)

    def notify(self, db: Session, event: str, obj) -> None:
        self.notifier.send(db, event, obj)


def build_services(settings: Settings, sm: sessionmaker, *, transport=None, web=None, supermemory=None) -> Services:
    tracer = make_tracer(settings)
    sup = supermemory if supermemory is not None else Supermemory(settings.supermemory_api_key, settings.supermemory_base_url)
    return Services(settings=settings, sessionmaker=sm, llm=LLMClient(settings, transport=transport, tracer=tracer),
                    tracer=tracer, web=web or Web(), librarian=Librarian(sup), notifier=Notifier(settings))
