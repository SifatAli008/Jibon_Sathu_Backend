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
