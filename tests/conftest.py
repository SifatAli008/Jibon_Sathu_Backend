from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.config import get_settings


def _postgres_reachable() -> bool:
    try:
        url = get_settings().database_url.replace("+asyncpg", "+psycopg2")
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


_POSTGRES_OK = _postgres_reachable()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: needs running Postgres (see docker-compose.yml)")
    config.addinivalue_line("markers", "load: slow / large-data tests (optional; see RUN_ANALYTICS_LOAD_TEST)")


@pytest.fixture(autouse=True)
def _disable_grpc_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #12: avoid binding port 50051 during pytest unless a test overrides GRPC_PORT."""
    monkeypatch.setenv("GRPC_PORT", "0")
    from app.config import get_settings

    get_settings.cache_clear()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _POSTGRES_OK:
        return
    skip = pytest.mark.skip(reason="Postgres not reachable at DATABASE_URL; start `docker compose up -d`")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
