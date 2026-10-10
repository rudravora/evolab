import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
# Make `agents` and `app` importable when pytest runs from the repo root.
sys.path.insert(0, str(BACKEND))

OWNER_PASSWORD = "correct horse battery staple"


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def settings(tmp_path):
    from app.config import Settings
    from app.security import hash_password

    return Settings(
        _env_file=None,
        app_secret="t" * 40,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        owner_password_hash=hash_password(OWNER_PASSWORD),
        allowed_origins="http://localhost:5173",
        public_base_url="http://localhost:8000",
        run_sweeper=False,
    )


@pytest.fixture
def app(settings):
    from app.main import create_app
    from app.routes import auth
    from app.security import LoginLimiter
    from app.seed import seed_agents

    migrate(settings.database_url)
    application = create_app(settings)
    with application.state.db.sessionmaker() as s:
        seed_agents(s)
    auth.limiter = LoginLimiter()  # fresh rate-limit state per test
    from app.routes import workers
    from app.security import RateLimiter
    workers.log_limiter = RateLimiter(10_000, 1.0)
    return application


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(client):
    r = client.post("/api/v1/auth/login", json={"password": OWNER_PASSWORD})
    assert r.status_code == 200
    return client
