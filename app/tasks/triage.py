"""Celery task body: triage report batch (Issue #11)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import update

from app.db_sync import sync_session_scope
from app.models import Report
from app.services.triage_logic import compute_priority_score


def run_triage_batch(report_ids: list[str]) -> None:
    """Load each report, compute score, mark triage completed."""
    with sync_session_scope() as session:
        for sid in report_ids:
            try:
                rid = UUID(sid)
            except ValueError:
                continue
            row = session.get(Report, rid)
            if row is None:
                continue
            score = compute_priority_score(row.kind, row.status, dict(row.payload or {}))
            session.execute(
                update(Report)
                .where(Report.id == rid)
                .values(priority_score=score, triage_status="completed")
            )
