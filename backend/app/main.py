"""FastAPI app factory. Run from backend/:  uvicorn app.main:app --port 8000"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, errors, jobs, orchestrator, sweeper, uploads
from .config import Settings, get_settings
from .db import Database
from .limits import Limits
from .routes import agents, approvals, auth, experiments, health, hooks, memory, projects, stream, tasks, workers
from .security import RateLimiter, SecurityHeaders
from .services import Services, build_services

API_PREFIX = "/api/v1"
log = logging.getLogger("evolab")


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db = Database(settings.database_url)
    services = services or build_services(settings, db.sessionmaker)
    services.sessionmaker = db.sessionmaker

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks_ = []
        if settings.run_sweeper:
            tasks_.append(asyncio.create_task(sweeper.run_forever(db.sessionmaker, services)))
        if settings.run_orchestrator:
            tasks_.append(asyncio.create_task(orchestrator.run_forever(services)))
        try:
            with db.sessionmaker() as s:
                n = services.librarian.load_seeded(s)
                if n:
                    log.info("loaded %d seeded memory entries", n)
        except Exception:  # noqa: BLE001 - a missing table on first start must not stop the app
            log.warning("seeded memory not loaded", exc_info=True)
        yield
        for t in tasks_:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        pool = services.extras.get("pool")
        if pool:
            pool.shutdown(wait=False, cancel_futures=True)

    dev_docs = not settings.https  # interactive docs only in local dev
    app = FastAPI(title="EvoLab API", version=__version__,
                  openapi_url=f"{API_PREFIX}/openapi.json" if dev_docs else None,
                  docs_url="/docs" if dev_docs else None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.services = services
    app.state.chat_limiter = RateLimiter(20, 60.0, "Too many chat messages for this run")     # API.md 12
    app.state.hook_limiter = RateLimiter(30, 60.0, "Too many hook requests")
    app.dependency_overrides[get_settings] = lambda: settings

    # A finished job goes back to whoever created it (agent loop, Executor, relay, or the M1 pipe check).
    jobs.on_finished = lambda s, job: orchestrator.on_job_finished(s, services, job)
    uploads.trust_backend_host(settings)

    errors.install(app)
    app.add_middleware(Limits)
    app.add_middleware(SecurityHeaders, hsts=settings.https)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"])

    for router in (health.router, auth.router, agents.router, projects.router, stream.router, approvals.router,
                   workers.dashboard, workers.worker_api, tasks.router, experiments.router, memory.router, hooks.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app lazily so importing this module
    # (tests, the OpenAPI exporter) does not require a configured .env.
    if name == "app":
        return create_app()
    raise AttributeError(name)
