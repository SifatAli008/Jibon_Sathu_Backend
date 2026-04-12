from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportKind(StrEnum):
    road = "road"
    sos = "sos"
    supply = "supply"


class ReportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: ReportKind
    segment_key: str | None = None
    status: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    """When set (or with `is_tombstone`), the server stores a CRDT tombstone row (Issue #5)."""

    is_tombstone: bool | None = None
    """Explicit tombstone flag without `deleted_at` (optional)."""


class SyncPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: UUID
    batch_id: UUID
    gateway_name: str | None = None
    reports: list[ReportItem] = Field(default_factory=list)


class SyncPushResponse(BaseModel):
    idempotent_replay: bool = False
    record_count: int
    applied_count: int
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    sync_log_status: str = "applied"


class SyncPullReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    segment_key: str | None = None
    status: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    source_gateway_id: UUID | None = None
    server_sequence_id: int
    is_tombstone: bool


class LatestModelVersionMeta(BaseModel):
    name: str
    version: str
    sha256: str
    size_bytes: int


class SyncPullResponse(BaseModel):
    items: list[SyncPullReportItem]
    max_sequence_id: int
    has_more: bool
    latest_model_version: LatestModelVersionMeta | None = None


class SyncConflictLogItem(BaseModel):
    id: int
    gateway_id: UUID
    batch_id: UUID
    received_at: datetime
    record_count: int
    applied_count: int
    status: str
    server_sequence_id: int
    merge_audit: dict[str, Any] | None = None


class SyncConflictsResponse(BaseModel):
    items: list[SyncConflictLogItem]
    has_more: bool = False
