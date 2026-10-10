import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
# Make `agents` and `app` importable when pytest runs from the repo root.
sys.path.insert(0, str(BACKEND))

OWNER_PASSWORD = "correct horse battery staple"
API = "/api/v1"


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def make_settings(tmp_path, **over):
    from app.config import Settings
    from app.security import hash_password

    base = dict(_env_file=None, app_secret="t" * 40, database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
                owner_password_hash=hash_password(OWNER_PASSWORD), allowed_origins="http://localhost:5173",
                public_base_url="http://localhost:8000", run_sweeper=False, run_orchestrator=False,
                pipeline="pipe_check", artifacts_dir=str(tmp_path / "artifacts"), langsmith_tracing=False)
    base.update(over)
    return Settings(**base)


def build_app(settings, transport=None, web=None, supermemory=None):
    from app.main import create_app
    from app.routes import auth, workers
    from app.security import LoginLimiter, RateLimiter
    from app.seed import seed_agents
    from app.services import build_services

    migrate(settings.database_url)
    services = build_services(settings, None, transport=transport, web=web, supermemory=supermemory)
    application = create_app(settings, services)          # create_app attaches the DB sessionmaker
    with application.state.db.sessionmaker() as s:
        seed_agents(s)
    auth.limiter = LoginLimiter()          # fresh rate-limit state per test
    workers.log_limiter = RateLimiter(10_000, 1.0)
    return application


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def app(settings):
    return build_app(settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(client):
    r = client.post(f"{API}/auth/login", json={"password": OWNER_PASSWORD})
    assert r.status_code == 200
    return client


# --- agent pipeline (M2-M5) -------------------------------------------------------------------

@pytest.fixture
def llm():
    from fakes import ScriptedLLM
    return ScriptedLLM()


@pytest.fixture
def sm():
    from fakes import FakeSupermemory
    return FakeSupermemory()


@pytest.fixture
def agent_settings(tmp_path):
    return make_settings(tmp_path, pipeline="agents", llm_base_url="http://llm.test", llm_api_key="k",
                         llm_model_strong="gpt-5.6-luna", llm_model_code="deepseek-v4-pro", llm_model_fast="gpt-5-mini")


@pytest.fixture
def agent_app(agent_settings, llm, sm):
    from fakes import FakeWeb
    return build_app(agent_settings, transport=llm, web=FakeWeb(), supermemory=sm)


@pytest.fixture
def ac(agent_app):
    """Signed-in client for the agent pipeline."""
    from fastapi.testclient import TestClient

    with TestClient(agent_app) as c:
        assert c.post(f"{API}/auth/login", json={"password": OWNER_PASSWORD}).status_code == 200
        yield c


class Driver:
    """Runs scheduler passes inline, lets the simulated worker drain jobs, and answers approvals."""

    def __init__(self, app, client, worker):
        self.app, self.c, self.w = app, client, worker
        self.decided: list[dict] = []

    def services(self):
        return self.app.state.services

    def approvals(self, run_id, status="pending"):
        return self.c.get(f"{API}/approvals", params={"run_id": run_id, "status": status}).json()

    def decide(self, approval, decision="approve", **extra):
        r = self.c.post(f"{API}/approvals/{approval['id']}/decide", json={"decision": decision, **extra})
        assert r.status_code == 200, r.text
        self.decided.append(approval)
        return r.json()

    def step(self) -> int:
        from app import orchestrator
        n = orchestrator.tick(self.services(), inline=True)
        n += self.w.drain()
        return n

    def run(self, run_id, approve=("plan", "evolution"), max_steps=200, until=None):
        idle = 0
        for _ in range(max_steps):
            moved = self.step()
            for a in self.approvals(run_id):
                if a["type"] in approve:
                    self.decide(a)
                    moved += 1
            status = self.c.get(f"{API}/runs/{run_id}").json()["status"]
            if until and until():
                return status
            if status in ("done", "failed", "cancelled") and not moved:
                idle += 1
                if idle >= 2:
                    return status
            elif not moved:
                idle += 1
                if idle >= 6:
                    return status
            else:
                idle = 0
        return self.c.get(f"{API}/runs/{run_id}").json()["status"]


@pytest.fixture
def driver(agent_app, ac):
    from fakes import SimWorker
    return Driver(agent_app, ac, SimWorker(ac))
