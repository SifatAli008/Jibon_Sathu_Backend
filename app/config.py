from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://jibon:jibon@127.0.0.1:5433/jibon_sathu"
    """Async SQLAlchemy URL (asyncpg driver)."""

    max_future_skew_seconds: int = 300
    """Reject `updated_at` / `created_at` more than this many seconds after server UTC."""

    max_sync_batch_items: int = 10_000
    """Strict upper bound on `reports` length per `POST /sync/push` (Issue #2)."""

    reports_dev_key: str | None = None
    """If set, `GET /reports` is enabled when `X-Dev-Reports-Key` matches (Issue #4 handoff)."""

    model_artifacts_base_dir: str = "artifacts/models"
    """Root directory for stored `.onnx` files (relative to cwd or absolute)."""

    models_download_key: str | None = None
    """If set, `GET /models/.../latest/file` requires matching `X-Model-Download-Key`."""

    models_admin_key: str | None = None
    """If set, `POST /models/.../publish` requires matching `X-Models-Admin-Key`."""


@lru_cache
def get_settings() -> Settings:
    return Settings()
