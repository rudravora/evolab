"""Settings from environment variables (names documented in .env.example).

Values are read from the process environment, then from the repo-root `.env`.
Secrets never have defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///./evolab.db"
    app_secret: str = Field(min_length=32)
    owner_password_hash: str = ""
    allowed_origins: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:8000"
    session_ttl_s: int = 12 * 3600
    run_sweeper: bool = True   # background housekeeping (worker offline, requeue, approval expiry)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
