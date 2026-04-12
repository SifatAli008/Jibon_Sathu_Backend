"""Celery application (Issue #11)."""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

# Eager mode (tests / local inline triage) must not require Redis; Celery still opens the
# result backend during apply_async unless broker/backend are in-memory.
if settings.celery_task_always_eager:
    _broker = "memory://"
    _backend = "cache+memory://"
else:
    _broker = settings.celery_broker_url or "redis://127.0.0.1:6379/0"
    _backend = settings.celery_result_backend or settings.celery_broker_url or _broker

celery_app = Celery(
    "jibon_sathu",
    broker=_broker,
    backend=_backend,
)
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.conf.task_eager_propagates = True


@celery_app.task(name="triage_reports_task")
def triage_reports_task(report_ids: list[str]) -> None:
    from app.tasks.triage import run_triage_batch

    run_triage_batch(report_ids)
