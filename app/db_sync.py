"""Synchronous SQLAlchemy engine for Celery workers (Issue #11)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_sync_engine = None
_sync_factory: sessionmaker[Session] | None = None


def get_sync_engine():
    global _sync_engine, _sync_factory
    if _sync_engine is None:
        settings = get_settings()
        url = settings.sync_database_url
        _sync_engine = create_engine(url, pool_pre_ping=True)
        _sync_factory = sessionmaker(bind=_sync_engine, expire_on_commit=False)
    return _sync_engine


def get_sync_session_factory() -> sessionmaker[Session]:
    get_sync_engine()
    assert _sync_factory is not None
    return _sync_factory


@contextmanager
def sync_session_scope() -> Iterator[Session]:
    factory = get_sync_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
