from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://jibon:jibon@127.0.0.1:5433/jibon_sathu"
    """Async SQLAlchemy URL (asyncpg driver)."""

    max_future_skew_seconds: int = 300
    """Reject `updated_at` / `created_at` more than this many seconds after server UTC."""

    max_sync_batch_items: int = Field(default=500, validation_alias="MAX_SYNC_BATCH_ITEMS")
    """Strict upper bound on `reports` length per `POST /sync/push` (Issues #2, #8)."""

    require_gateway_auth: bool = Field(default=False, validation_alias="REQUIRE_GATEWAY_AUTH")
    """When true, sync + model download routes require `X-Gateway-Id` + `Authorization: Bearer <secret>`."""

    sync_rate_limit: str = Field(default="120/minute", validation_alias="SYNC_RATE_LIMIT")
    """slowapi limit for `/sync/*` routes, keyed by `X-Gateway-Id` (Issue #8)."""

    sync_admin_key: str | None = Field(default=None, validation_alias="SYNC_ADMIN_KEY")
    """If set, `GET /sync/conflicts` requires `X-Sync-Admin-Key` (Issue #8)."""

    reports_dev_key: str | None = None
    """If set, `GET /reports` is enabled when `X-Dev-Reports-Key` matches (Issue #4 handoff)."""

    model_artifacts_base_dir: str = "artifacts/models"
    """Root directory for stored `.onnx` files (relative to cwd or absolute)."""

    models_download_key: str | None = None
    """If set, `GET /models/.../latest/file` requires matching `X-Model-Download-Key`."""

    models_admin_key: str | None = None
    """If set, `POST /models/.../publish` requires matching `X-Models-Admin-Key`."""

    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")
    """Redis URL for Celery (Issue #11). If unset, triage tasks are not enqueued (API still merges)."""

    celery_result_backend: str | None = Field(default=None, validation_alias="CELERY_RESULT_BACKEND")
    """Optional Celery result backend; defaults to broker."""

    celery_task_always_eager: bool = Field(default=False, validation_alias="CELERY_TASK_ALWAYS_EAGER")
    """Run triage inline (tests) instead of Redis."""

    dashboard_admin_key: str | None = Field(default=None, validation_alias="DASHBOARD_ADMIN_KEY")
    """If set, `/v1/analytics/*` requires `X-Dashboard-Admin-Key` (Issue #13)."""

    grpc_port: int = Field(default=50051, validation_alias="GRPC_PORT")
    """gRPC listen port (Issue #12). Set 0 to disable in-process server."""

    grpc_min_client_version: str = Field(default="1.0.0", validation_alias="GRPC_MIN_CLIENT_VERSION")
    """Reject gRPC calls when `x-client-version` metadata is below this semver."""

    analytics_cache_ttl_seconds: int = Field(default=30, validation_alias="ANALYTICS_CACHE_TTL_SECONDS")

    @property
    def sync_database_url(self) -> str:
        """Sync driver URL for Celery workers (`psycopg2`)."""
        u = self.database_url
        if "+asyncpg" in u:
            return u.replace("+asyncpg", "+psycopg2", 1)
        return u


@lru_cache
def get_settings() -> Settings:
    return Settings()
