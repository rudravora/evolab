"""FastAPI app factory. Run from backend/:  uvicorn app.main:app --port 8000"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, errors, sweeper
from .config import Settings, get_settings
from .db import Database
from .routes import agents, approvals, auth, health, projects, stream, workers
from .security import SecurityHeaders

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(sweeper.run_forever(app.state.db.sessionmaker)) if settings.run_sweeper else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    dev_docs = not settings.https  # interactive docs only in local dev
    app = FastAPI(
        title="EvoLab API",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json" if dev_docs else None,
        docs_url="/docs" if dev_docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.dependency_overrides[get_settings] = lambda: settings

    errors.install(app)
    app.add_middleware(SecurityHeaders, hsts=settings.https)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )

    for router in (health.router, auth.router, agents.router, projects.router, stream.router, approvals.router,
                   workers.dashboard, workers.worker_api):
        app.include_router(router, prefix=API_PREFIX)
    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app lazily so importing this module
    # (tests, the OpenAPI exporter) does not require a configured .env.
    if name == "app":
        return create_app()
    raise AttributeError(name)
