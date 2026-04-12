"""
Issue #2 merge orchestration + Issue #5 server_sequence_id / tombstones + Issue #8 audit payload.

Invariants:
- Whole batch commits or rolls back (SyncLog written only after all items succeed).
- SOS rows are never UPDATEd or DELETEd on push (append-only / first-write wins on id).
- `applied_count` counts DB rows inserted or updated, not raw report count.
- Each successful insert/update assigns a fresh `server_sequence_id` from `server_sequence_global`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Gateway, Report, SyncLog
from app.schemas.sync import ReportItem, ReportKind, SyncPushRequest
from app.services.merge_policy import (
    MutableMergeAction,
    SosMergeAction,
    decide_road_like_merge,
    decide_sos_merge,
    incoming_is_tombstone,
)
from app.services.server_sequence import next_server_sequence

# Tests may set this to raise after N successful touches (insert/update) to assert rollback.
_simulated_fault_after_touches: int | None = None


def set_merge_fault_after_touches(n: int | None) -> None:
    global _simulated_fault_after_touches
    _simulated_fault_after_touches = n


class BatchValidationError(ValueError):
    """Strict batch failure (HTTP 422): no partial apply, no success SyncLog."""


class BatchPayloadTooLargeError(BatchValidationError):
    """HTTP 413: batch exceeds configured maximum item count (Issue #8)."""


class SimulatedMergeFault(RuntimeError):
    """Test-only fault injection (maps to HTTP 500 in the sync route)."""


@dataclass(frozen=True)
class MergeResult:
    idempotent_replay: bool
    record_count: int
    applied_count: int
    sync_log_status: str
    """Report PKs touched by merge (insert/update) for async M6 triage (Issue #11)."""
    triage_report_ids: tuple[UUID, ...] = ()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _validate_timestamps(item: ReportItem, now: datetime, max_future: timedelta) -> str | None:
    limit = now + max_future
    if item.created_at > limit or item.updated_at > limit:
        return "created_at/updated_at too far in the future relative to server clock"
    return None


def validate_batch_strict(reports: list[ReportItem], now: datetime, max_future: timedelta) -> None:
    """Issue #2 strict mode: one bad timestamp fails the entire batch (no DB writes)."""
    for r in reports:
        err = _validate_timestamps(r, now, max_future)
        if err:
            raise BatchValidationError(f"{err} (report id={r.id})")


def _snap_mutable(r: Report) -> dict[str, Any]:
    return {
        "id": r.id,
        "updated_at": r.updated_at,
        "source_gateway_id": r.source_gateway_id,
        "is_tombstone": r.is_tombstone,
        "server_sequence_id": r.server_sequence_id,
    }


async def _fetch_canonical_mutable(
    session: AsyncSession, kind: str, segment_key: str
) -> Report | None:
    """Pick the current winning row for (kind, segment_key) — prefer latest server_sequence_id."""
    stmt = (
        select(Report)
        .where(Report.kind == kind, Report.segment_key == segment_key)
        .order_by(
            Report.server_sequence_id.desc(),
            Report.updated_at.desc(),
            cast(Report.source_gateway_id, String).desc().nulls_last(),
            cast(Report.id, String).desc(),
        )
        .limit(1)
    )
    return await session.scalar(stmt)


def _append_merge_audit(
    audit: list[dict[str, Any]],
    *,
    incoming: ReportItem,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> None:
    row: dict[str, Any] = {
        "report_id": str(incoming.id),
        "kind": incoming.kind.value,
        "segment_key": incoming.segment_key,
        "reason": reason,
    }
    if extra:
        row.update(extra)
    audit.append(row)


async def _apply_one_report(
    session: AsyncSession,
    incoming: ReportItem,
    gateway_id: UUID,
    audit: list[dict[str, Any]],
) -> tuple[int, UUID | None]:
    """Returns (rows touched 0|1, affected report PK for triage enqueue)."""
    kind = incoming.kind.value

    if incoming.kind == ReportKind.sos:
        row = await session.get(Report, incoming.id)
        if row is not None and row.kind != "sos":
            raise BatchValidationError(
                f"report id={incoming.id} exists with kind={row.kind}; cannot store SOS on same id"
            )
        existing = _snap_mutable(row) if row is not None and row.kind == "sos" else None
        action = decide_sos_merge(existing_row=existing)
        if action == SosMergeAction.noop:
            _append_merge_audit(audit, incoming=incoming, reason="noop_sos_immutable")
            return (0, None)
        seq = await next_server_sequence(session)
        session.add(
            Report(
                id=incoming.id,
                kind="sos",
                segment_key=incoming.segment_key,
                status=incoming.status,
                payload=dict(incoming.payload),
                created_at=incoming.created_at,
                updated_at=incoming.updated_at,
                source_gateway_id=gateway_id,
                deleted_at=None,
                server_sequence_id=seq,
                is_tombstone=False,
                triage_status="pending",
            )
        )
        return (1, incoming.id)

    if incoming.segment_key:
        row = await _fetch_canonical_mutable(session, kind, incoming.segment_key)
    else:
        row = await session.get(Report, incoming.id)
        if row is not None and row.kind != kind:
            raise BatchValidationError(
                f"report id={incoming.id} exists with kind={row.kind}; incoming kind={kind}"
            )

    snap = _snap_mutable(row) if row is not None else None
    decision = decide_road_like_merge(
        incoming=incoming,
        incoming_gateway_id=gateway_id,
        canonical_existing=snap,
    )

    if decision.action == MutableMergeAction.noop:
        if snap and snap.get("is_tombstone") and not incoming_is_tombstone(incoming):
            _append_merge_audit(
                audit,
                incoming=incoming,
                reason="noop_tombstone_blocks_resurrection",
                extra={"canonical_sequence_id": snap.get("server_sequence_id")},
            )
        else:
            _append_merge_audit(audit, incoming=incoming, reason="noop_lww_loser")
        return (0, None)

    if decision.action == MutableMergeAction.insert:
        seq = await next_server_sequence(session)
        session.add(
            Report(
                id=decision.row_id,
                kind=decision.kind,
                segment_key=decision.segment_key,
                status=decision.status,
                payload=decision.payload,
                created_at=decision.created_at,
                updated_at=decision.updated_at,
                source_gateway_id=gateway_id,
                deleted_at=decision.deleted_at,
                server_sequence_id=seq,
                is_tombstone=decision.is_tombstone,
                triage_status="pending",
            )
        )
        return (1, decision.row_id)

    seq = await next_server_sequence(session)
    await session.execute(
        update(Report)
        .where(Report.id == decision.row_id)
        .values(
            kind=decision.kind,
            segment_key=decision.segment_key,
            status=decision.status,
            payload=decision.payload,
            created_at=decision.created_at,
            updated_at=decision.updated_at,
            source_gateway_id=gateway_id,
            deleted_at=decision.deleted_at,
            server_sequence_id=seq,
            is_tombstone=decision.is_tombstone,
            triage_status="pending",
            priority_score=None,
        )
    )
    return (1, decision.row_id)


class MergeService:
    """Merge entrypoint (Issue #2 + #5 + #8)."""

    @staticmethod
    async def apply_batch(
        session: AsyncSession,
        body: SyncPushRequest,
        header_gateway_id: UUID,
        header_batch_id: UUID,
    ) -> MergeResult:
        if body.gateway_id != header_gateway_id:
            raise ValueError("gateway_id must match X-Gateway-Id header")
        if body.batch_id != header_batch_id:
            raise ValueError("batch_id must match X-Sync-Batch-Id header")

        settings = get_settings()
        max_items = settings.max_sync_batch_items
        if len(body.reports) > max_items:
            raise BatchPayloadTooLargeError(f"batch exceeds max_sync_batch_items ({max_items})")

        now = _utcnow()
        max_future = timedelta(seconds=settings.max_future_skew_seconds)
        validate_batch_strict(body.reports, now, max_future)

        existing = await session.scalar(
            select(SyncLog).where(
                SyncLog.gateway_id == body.gateway_id,
                SyncLog.batch_id == body.batch_id,
            )
        )
        if existing is not None:
            return MergeResult(
                idempotent_replay=True,
                record_count=existing.record_count,
                applied_count=existing.applied_count,
                sync_log_status=existing.status,
                triage_report_ids=(),
            )

        gateway_name = body.gateway_name or f"gateway-{str(body.gateway_id)[:8]}"
        if settings.require_gateway_auth:
            await session.execute(
                update(Gateway)
                .where(Gateway.id == body.gateway_id)
                .values(last_seen_at=now, name=gateway_name)
            )
        else:
            await session.execute(
                pg_insert(Gateway)
                .values(
                    id=body.gateway_id,
                    name=gateway_name,
                    last_seen_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[Gateway.id],
                    set_={"last_seen_at": now, "name": gateway_name},
                )
            )

        audit: list[dict[str, Any]] = []
        touches = 0
        triage_ids: list[UUID] = []
        for item in body.reports:
            n, rid = await _apply_one_report(session, item, body.gateway_id, audit)
            touches += n
            if rid is not None:
                triage_ids.append(rid)
            await session.flush()
            if _simulated_fault_after_touches is not None and touches >= _simulated_fault_after_touches:
                raise SimulatedMergeFault("simulated merge fault for tests")

        record_count = len(body.reports)
        batch_seq = await next_server_sequence(session)
        session.add(
            SyncLog(
                gateway_id=body.gateway_id,
                batch_id=body.batch_id,
                record_count=record_count,
                applied_count=touches,
                status="applied",
                error_detail=None,
                server_sequence_id=batch_seq,
                merge_audit={"events": audit} if audit else None,
            )
        )

        return MergeResult(
            idempotent_replay=False,
            record_count=record_count,
            applied_count=touches,
            sync_log_status="applied",
            triage_report_ids=tuple(triage_ids),
        )
