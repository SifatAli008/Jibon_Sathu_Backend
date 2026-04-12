import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.sync import ReportItem, SyncPushRequest


def test_report_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        ReportItem.model_validate(
            {
                "id": str(uuid.uuid4()),
                "kind": "weather",
                "created_at": "2026-04-12T10:00:00Z",
                "updated_at": "2026-04-12T10:00:00Z",
            }
        )


def test_sync_push_requires_gateway_and_batch() -> None:
    with pytest.raises(ValidationError):
        SyncPushRequest.model_validate({"reports": []})


def test_sync_push_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SyncPushRequest.model_validate(
            {
                "gateway_id": str(uuid.uuid4()),
                "batch_id": str(uuid.uuid4()),
                "unknown": True,
            }
        )


def test_report_accepts_valid_payload() -> None:
    rid = uuid.uuid4()
    item = ReportItem.model_validate(
        {
            "id": str(rid),
            "kind": "road",
            "segment_key": "BD-DHK-12-450",
            "status": "damaged",
            "payload": {"lat": 23.7, "lon": 90.4},
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    assert item.id == rid
    assert item.kind.value == "road"
