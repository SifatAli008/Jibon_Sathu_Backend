#!/usr/bin/env python3
"""
Push synthetic reports so the React dashboard can show map layers, SOS queue, field devices,
sync history, and recent activity.

Uses POST /v1/sync/push. With --gateways > 1, sends multiple batches (different gateway_id /
batch_id) so GET /reports groups rows by source_gateway_id and GET /v1/sync/conflicts lists
multiple batches.

Usage (API must be running, DB migrated):

  python scripts/seed_dashboard_demo.py
  python scripts/seed_dashboard_demo.py --gateways 3 --base-url http://127.0.0.1:8000

Environment:
  SEED_BASE_URL       API base URL (default http://127.0.0.1:8000)
  GATEWAY_SECRET      Plain secret when REQUIRE_GATEWAY_AUTH=true (sent as Bearer)

API .env (restart uvicorn after changes):
  DASHBOARD_ADMIN_KEY       → X-Dashboard-Admin-Key (analytics)
  REPORTS_DEV_KEY           → VITE_DEV_REPORTS_KEY (GET /reports)
  SYNC_ADMIN_KEY            → VITE_SYNC_ADMIN_KEY (GET /v1/sync/conflicts)

For SOS priority scores without Redis, set CELERY_TASK_ALWAYS_EAGER=true so triage runs inline.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

_DEMO_GATEWAY_NAMES = (
    "Demo field phone - north",
    "Demo gateway - sector B",
    "Demo relief tablet - central",
)


def _iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _demo_reports(now: datetime) -> list[dict[str, Any]]:
    """
    Road/supply around Dhaka with lat/lon (required for /v1/analytics/map-layers).
    SOS rows for /v1/analytics/sos-queue (varied status/payload for triage scoring).
    """
    base_lat, base_lon = 23.8103, 90.4125
    reports: list[dict[str, Any]] = []

    for i in range(18):
        lat = base_lat + (i % 6) * 0.012 - 0.03
        lon = base_lon + (i // 6) * 0.015 - 0.02
        rid = uuid.uuid4()
        status = "damaged" if i % 4 == 0 else "flood_affected" if i % 4 == 1 else "ok"
        reports.append(
            {
                "id": str(rid),
                "kind": "road",
                "segment_key": f"DASH-DEMO-ROAD-{i:03d}",
                "status": status,
                "payload": {
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "label": f"Demo road segment {i}",
                },
                "created_at": _iso_z(now - timedelta(minutes=i)),
                "updated_at": _iso_z(now - timedelta(minutes=i)),
            }
        )

    supply_pts = [
        (23.785, 90.392, "medical", "critical_shortage"),
        (23.825, 90.435, "water", "stock_ok"),
        (23.798, 90.418, "food", "shortage"),
        (23.812, 90.405, "shelter", "ok"),
        (23.830, 90.428, "fuel", "critical"),
    ]
    for i, (lat, lon, label, status) in enumerate(supply_pts):
        rid = uuid.uuid4()
        reports.append(
            {
                "id": str(rid),
                "kind": "supply",
                "segment_key": f"DASH-DEMO-SUPPLY-{i}",
                "status": status,
                "payload": {
                    "lat": lat,
                    "lon": lon,
                    "type": label,
                    "qty_estimate": 10 + i * 3,
                },
                "created_at": _iso_z(now - timedelta(hours=1, minutes=i)),
                "updated_at": _iso_z(now - timedelta(hours=1, minutes=i)),
            }
        )

    sos_specs = [
        ("open", {"note": "Trapped family", "priority": "high", "lat": 23.82, "lon": 90.43}),
        ("open", {"casualties": True, "note": "Medical emergency"}),
        ("acknowledged", {"note": "Evacuation requested"}),
        ("open", {"injured": 2, "note": "Collapsed structure"}),
        ("open", {"note": "Water rising - need boat", "priority": "high"}),
    ]
    for i, (status, payload) in enumerate(sos_specs):
        rid = uuid.uuid4()
        reports.append(
            {
                "id": str(rid),
                "kind": "sos",
                "segment_key": None,
                "status": status,
                "payload": payload,
                "created_at": _iso_z(now - timedelta(minutes=30 + i * 5)),
                "updated_at": _iso_z(now - timedelta(minutes=30 + i * 5)),
            }
        )

    return reports


def _chunk_reports(items: list[dict[str, Any]], n: int) -> list[list[dict[str, Any]]]:
    if n <= 1:
        return [items]
    if not items:
        return []
    chunk_size = (len(items) + n - 1) // n
    out: list[list[dict[str, Any]]] = []
    for i in range(0, len(items), chunk_size):
        part = items[i : i + chunk_size]
        if part:
            out.append(part)
    return out


def _gateway_name(index: int) -> str:
    if 0 <= index < len(_DEMO_GATEWAY_NAMES):
        return _DEMO_GATEWAY_NAMES[index]
    return f"Demo gateway - unit {index + 1}"


def main() -> int:
    p = argparse.ArgumentParser(description="Seed dashboard demo data via POST /v1/sync/push")
    p.add_argument("--base-url", default=os.environ.get("SEED_BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument(
        "--gateways",
        type=int,
        default=3,
        help="Number of distinct gateway devices (separate sync batches; default 3)",
    )
    p.add_argument(
        "--gateway-id",
        default=os.environ.get("SEED_GATEWAY_ID"),
        help="When --gateways 1: optional fixed UUID. Ignored when --gateways > 1.",
    )
    p.add_argument(
        "--secret",
        default=os.environ.get("GATEWAY_SECRET"),
        help="Bearer token when REQUIRE_GATEWAY_AUTH=true",
    )
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args()

    if args.gateways < 1:
        print("--gateways must be >= 1", file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    all_reports = _demo_reports(now)
    chunks = _chunk_reports(all_reports, args.gateways)

    headers_base: dict[str, str] = {}
    if args.secret:
        headers_base["Authorization"] = f"Bearer {args.secret}"

    base = args.base_url.rstrip("/")
    total_applied = 0
    gateway_rows: list[tuple[str, str, int]] = []

    try:
        with httpx.Client(base_url=base, timeout=args.timeout) as client:
            for i, chunk in enumerate(chunks):
                if args.gateways == 1 and args.gateway_id:
                    gateway_id = args.gateway_id
                else:
                    gateway_id = str(uuid.uuid4())
                batch_id = str(uuid.uuid4())
                body: dict[str, Any] = {
                    "gateway_id": gateway_id,
                    "batch_id": batch_id,
                    "gateway_name": _gateway_name(i),
                    "reports": chunk,
                }
                headers = {
                    **headers_base,
                    "X-Gateway-Id": gateway_id,
                    "X-Sync-Batch-Id": batch_id,
                }
                r = client.post("/v1/sync/push", json=body, headers=headers)
                if r.status_code != 200:
                    print(f"Push failed HTTP {r.status_code}: {r.text[:2000]}", file=sys.stderr)
                    return 1
                out = r.json()
                applied = int(out.get("applied_count") or 0)
                total_applied += applied
                gateway_rows.append((gateway_id, batch_id, len(chunk)))
    except httpx.ConnectError as e:
        print(f"Cannot connect to {base}: {e}", file=sys.stderr)
        print("Start the API (e.g. uvicorn app.main:app --reload) and retry.", file=sys.stderr)
        return 1

    print("Seeded demo data via POST /v1/sync/push")
    print(f"  batches (sync history rows): {len(gateway_rows)}")
    print(f"  total reports applied: {total_applied} (of {len(all_reports)} sent)")
    for gateway_id, batch_id, nrep in gateway_rows:
        print(f"  gateway_id={gateway_id} batch_id={batch_id} reports_in_batch={nrep}")
    print()
    print("API .env -> React .env.local (use the same values):")
    print("  DASHBOARD_ADMIN_KEY     -> VITE_DASHBOARD_ADMIN_KEY (if your UI reads it)")
    print("  REPORTS_DEV_KEY         -> VITE_DEV_REPORTS_KEY")
    print("  SYNC_ADMIN_KEY          -> VITE_SYNC_ADMIN_KEY")
    print()
    print("Analytics headers: X-Dashboard-Admin-Key")
    print(f"  GET {base}/v1/analytics/map-layers")
    print(f"  GET {base}/v1/analytics/sos-queue")
    print("Dev / admin:")
    print(f"  GET {base}/reports  (header X-Dev-Reports-Key)")
    print(f"  GET {base}/v1/sync/conflicts  (header X-Sync-Admin-Key)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
