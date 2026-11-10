"""The one typed settings module read by the API and the worker (TRD 8.4, R-06)."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Validated at start; the process refuses to start without the required values."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore", frozen=True)

    public_base_url: str = Field(alias="PUBLIC_BASE_URL")
    database_url: str = Field(alias="DATABASE_URL")
    migration_database_url: str | None = Field(default=None, alias="MIGRATION_DATABASE_URL")
    storage_bucket: str = Field(alias="STORAGE_BUCKET")
    session_key: str = Field(alias="SESSION_KEY", min_length=16, repr=False)
    api_port: int = Field(default=8103, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    read_only: bool = Field(default=False, alias="READ_ONLY")
    worker_poll_seconds: float = Field(default=1.0, alias="WORKER_POLL_SECONDS")
    worker_heartbeat_path: str = Field(default=".run/worker.heartbeat", alias="WORKER_HEARTBEAT_PATH")
    max_pdf_bytes: int = Field(default=26_214_400, alias="MAX_PDF_BYTES")
    max_photo_bytes: int = Field(default=15_728_640, alias="MAX_PHOTO_BYTES")
    job_lock_seconds: int = Field(default=120, alias="JOB_LOCK_SECONDS")

    @field_validator("public_base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("PUBLIC_BASE_URL must be an absolute http(s) URL")
        return value.rstrip("/")

    @field_validator("storage_bucket")
    @classmethod
    def _bucket(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("STORAGE_BUCKET is required")
        return value

    def fingerprint(self) -> str:
        """Short hash of non-secret settings, logged at start by both processes (R-06)."""
        public = self.model_dump(exclude={"session_key", "database_url", "migration_database_url"})
        text = "|".join(f"{k}={public[k]}" for k in sorted(public))
        return hashlib.sha256(text.encode()).hexdigest()[:12]

    def storage_root(self) -> Path:
        return Path(self.storage_bucket)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
