"""
Pure merge rules for Issue #2 + Issue #5 tombstones (deterministic, testable without DB).

Invariants:
- SOS insert path never performs UPDATE or DELETE on push; duplicate id is a no-op (first write wins).
- Road/supply segment merge never lowers `updated_at` on the surviving row (loser is discarded, no write).
- Tie on `updated_at`: lexicographic (gateway_id, report id) — larger tuple wins so runs are stable.

Issue #5 (CRDT tombstones):
- Wall-clock `updated_at` alone is unsafe under device clock skew; Zone A still uses LWW for *competing live*
  rows, but **an established tombstone blocks non-tombstone “resurrection” pushes** regardless of
  client timestamps (prevents zombie records from stale Zone B batches).
- Tombstone rows (`is_tombstone=true`) only lose to another tombstone update that wins by normal LWW
  (e.g. a newer tombstone), not to stale live payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.schemas.sync import ReportItem


class MutableMergeAction(StrEnum):
    insert = "insert"
    update = "update"
    noop = "noop"


@dataclass(frozen=True)
class RoadLikeMergeDecision:
    """Road and supply share this policy."""

    action: MutableMergeAction
    """Row PK to INSERT (incoming id) or UPDATE (canonical survivor id)."""
    row_id: UUID
    status: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    kind: str
    segment_key: str | None
    is_tombstone: bool


def incoming_is_tombstone(item: ReportItem) -> bool:
    """A delete/tombstone is indicated by `deleted_at` and/or explicit `is_tombstone`."""
    if item.is_tombstone is True:
        return True
    return item.deleted_at is not None


def tombstone_deleted_at(item: ReportItem) -> datetime | None:
    """Prefer client `deleted_at`; fall back to `updated_at` for explicit tombstone-only payloads."""
    if item.deleted_at is not None:
        return item.deleted_at
    if item.is_tombstone is True:
        return item.updated_at
    return None


def _winner_tuple(updated_at: datetime, gateway_id: UUID | None, report_id: UUID) -> tuple[datetime, str, str]:
    return (updated_at, str(gateway_id or ""), str(report_id))


def incoming_beats_existing_row(
    incoming: ReportItem,
    incoming_gateway_id: UUID,
    existing_updated_at: datetime,
    existing_gateway_id: UUID | None,
    existing_id: UUID,
) -> bool:
    """Latest `updated_at` wins; on tie, lexicographic (gateway_id, id) — larger wins."""
    ti = _winner_tuple(incoming.updated_at, incoming_gateway_id, incoming.id)
    te = _winner_tuple(existing_updated_at, existing_gateway_id, existing_id)
    return ti > te


def decide_road_like_merge(
    *,
    incoming: ReportItem,
    incoming_gateway_id: UUID,
    canonical_existing: dict[str, Any] | None,
) -> RoadLikeMergeDecision:
    """
    `canonical_existing` is the chosen DB row for this natural key (segment or id), or None.

    Dict keys when present: id, updated_at, source_gateway_id, is_tombstone, (unused others ok).
    """
    kind = incoming.kind.value
    inc_tomb = incoming_is_tombstone(incoming)
    del_at = tombstone_deleted_at(incoming)

    if canonical_existing is None:
        return RoadLikeMergeDecision(
            action=MutableMergeAction.insert,
            row_id=incoming.id,
            status=incoming.status,
            payload=dict(incoming.payload),
            created_at=incoming.created_at,
            updated_at=incoming.updated_at,
            deleted_at=del_at if inc_tomb else incoming.deleted_at,
            kind=kind,
            segment_key=incoming.segment_key,
            is_tombstone=inc_tomb,
        )

    ex_id = canonical_existing["id"]
    ex_ut = canonical_existing["updated_at"]
    ex_gw = canonical_existing.get("source_gateway_id")
    ex_tomb = bool(canonical_existing.get("is_tombstone"))

    # Stale live updates must never resurrect a row that Zone A has already tombstoned.
    if ex_tomb and not inc_tomb:
        return RoadLikeMergeDecision(
            action=MutableMergeAction.noop,
            row_id=ex_id,
            status=incoming.status,
            payload=dict(incoming.payload),
            created_at=incoming.created_at,
            updated_at=incoming.updated_at,
            deleted_at=incoming.deleted_at,
            kind=kind,
            segment_key=incoming.segment_key,
            is_tombstone=inc_tomb,
        )

    if incoming_beats_existing_row(incoming, incoming_gateway_id, ex_ut, ex_gw, ex_id):
        return RoadLikeMergeDecision(
            action=MutableMergeAction.update,
            row_id=ex_id,
            status=incoming.status,
            payload=dict(incoming.payload),
            created_at=incoming.created_at,
            updated_at=incoming.updated_at,
            deleted_at=del_at if inc_tomb else incoming.deleted_at,
            kind=kind,
            segment_key=incoming.segment_key,
            is_tombstone=inc_tomb,
        )

    return RoadLikeMergeDecision(
        action=MutableMergeAction.noop,
        row_id=ex_id,
        status=incoming.status,
        payload=dict(incoming.payload),
        created_at=incoming.created_at,
        updated_at=incoming.updated_at,
        deleted_at=incoming.deleted_at,
        kind=kind,
        segment_key=incoming.segment_key,
        is_tombstone=inc_tomb,
    )


class SosMergeAction(StrEnum):
    insert = "insert"
    noop = "noop"


def decide_sos_merge(*, existing_row: dict[str, Any] | None) -> SosMergeAction:
    """Duplicate SOS id on push is ignored (immutable first write)."""
    if existing_row is not None:
        return SosMergeAction.noop
    return SosMergeAction.insert
