"""Settings from environment variables (names documented in .env.example).

Values are read from the process environment, then from the repo-root `.env`.
Secrets never have defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # core
    database_url: str = "sqlite:///./evolab.db"
    app_secret: str = Field(min_length=32)
    owner_password_hash: str = ""
    allowed_origins: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:8000"
    session_ttl_s: int = 12 * 3600
    artifacts_dir: str = "./artifacts"

    # background work
    run_sweeper: bool = True          # worker offline, requeue, approval expiry
    run_orchestrator: bool = True     # scheduler that drives agent tasks
    pipeline: Literal["agents", "pipe_check"] = "agents"   # pipe_check = the M1 fake agent

    # LLM gateway (D-041)
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_strong: str = ""
    llm_model_code: str = ""
    llm_model_fast: str = ""
    llm_timeout_s: float = 180.0

    # memory, tracing, council (D-038, D-039, D-040)
    supermemory_api_key: str = ""
    supermemory_base_url: str = "https://api.supermemory.ai"
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "evolab"
    feature_council: bool = True

    # n8n (FR-26, FR-27)
    n8n_webhook_url: str = ""
    n8n_signing_secret: str = ""

    @field_validator("owner_password_hash")
    @classmethod
    def _hash_format(cls, v: str) -> str:
        if v and not v.startswith("scrypt$"):
            raise ValueError("OWNER_PASSWORD_HASH must come from backend/scripts/hash_password.py")
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def https(self) -> bool:
        return self.public_base_url.startswith("https://")

    @property
    def llm_models(self) -> dict[str, str]:
        return {"strong": self.llm_model_strong, "code": self.llm_model_code, "fast": self.llm_model_fast}


@lru_cache
def get_settings() -> Settings:
    return Settings()
