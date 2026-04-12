"""Enqueue async triage after sync transaction commits (Issue #11)."""

from __future__ import annotations

from uuid import UUID

from app.config import get_settings


def maybe_enqueue_triage(report_ids: tuple[UUID, ...]) -> None:
    if not report_ids:
        return
    settings = get_settings()
    if not settings.celery_broker_url and not settings.celery_task_always_eager:
        return
    ids_str = [str(x) for x in report_ids]
    # Import inside the function so tests can `importlib.reload(app.worker)` after env changes
    # without stale Celery app / task handles on the sync route.
    from app.worker import triage_reports_task

    triage_reports_task.delay(ids_str)
