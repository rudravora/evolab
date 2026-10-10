"""Database engine and sessions. SQLite in dev, Postgres in deploy (same models).

Sync SQLAlchemy (D-045): routes are plain `def` and run in FastAPI's threadpool;
the orchestrator will call the DB through `asyncio.to_thread`.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return engine


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        with self.sessionmaker() as s:
            yield s
