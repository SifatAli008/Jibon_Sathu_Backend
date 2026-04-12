from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_json() -> None:
    r = client.get("/health")
    assert r.status_code in (200, 503)
    data = r.json()
    assert "status" in data and "db" in data


@pytest.mark.integration
def test_push_minimal_batch() -> None:
    gid = uuid.uuid4()
    bid = uuid.uuid4()
    rid = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid),
        "gateway_name": "test-gateway",
        "reports": [
            {
                "id": str(rid),
                "kind": "road",
                "segment_key": "BD-DHK-12-450",
                "status": "damaged",
                "payload": {"notes": "crack"},
                "created_at": now,
                "updated_at": now,
            }
        ],
    }
    r = client.post(
        "/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["record_count"] == 1
    assert out["applied_count"] == 1
    assert out["idempotent_replay"] is False

    r2 = client.post(
        "/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
    )
    assert r2.status_code == 200
    out2 = r2.json()
    assert out2["idempotent_replay"] is True


def test_push_header_body_mismatch() -> None:
    gid = uuid.uuid4()
    other = uuid.uuid4()
    bid = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid),
        "reports": [],
    }
    r = client.post(
        "/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(other), "X-Sync-Batch-Id": str(bid)},
    )
    assert r.status_code == 400


@pytest.mark.integration
def test_push_partial_clock_skew() -> None:
    from datetime import timedelta

    gid = uuid.uuid4()
    bid = uuid.uuid4()
    rid_ok = uuid.uuid4()
    rid_bad = uuid.uuid4()
    now = datetime.now(UTC)
    far = (now + timedelta(days=400)).isoformat().replace("+00:00", "Z")
    ok_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid),
        "reports": [
            {
                "id": str(rid_ok),
                "kind": "sos",
                "status": "open",
                "payload": {},
                "created_at": ok_iso,
                "updated_at": ok_iso,
            },
            {
                "id": str(rid_bad),
                "kind": "road",
                "status": "ok",
                "payload": {},
                "created_at": far,
                "updated_at": far,
            },
        ],
    }
    r = client.post(
        "/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["applied_count"] == 1
    assert out["sync_log_status"] == "partial"
    assert len(out["rejected"]) == 1
