#!/usr/bin/env python3
"""
Zone B → Zone A integration spike (Issue #4).

Pushes overlapping road reports, probes model metadata, downloads ONNX, verifies SHA256 + onnxruntime.

Environment (optional; CLI overrides):
  GATEWAY_SIM_BASE_URL     default http://127.0.0.1:8000
  GATEWAY_SIM_GATEWAY_ID   UUID for X-Gateway-Id / body.gateway_id
  GATEWAY_SIM_MODEL_NAME   default road_decay_model
  GATEWAY_SIM_DOWNLOAD_KEY -> X-Model-Download-Key when server requires it
  GATEWAY_SIM_REPORTS_KEY  -> X-Dev-Reports-Key for optional GET /reports after push

Exit codes: 0 ok | 1 HTTP/API failure | 2 SHA256 mismatch | 3 ONNX load failure
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx


def _iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_reports(now: datetime) -> list[dict[str, Any]]:
    """Ten reports with intentional segment overlaps (merge rehearsal)."""
    t0 = now
    t_later = now + timedelta(hours=2)
    t_mid = now + timedelta(hours=1)
    t_earlier = now - timedelta(minutes=30)

    seg_a = "SPIKE-OVERLAP-A"
    seg_b = "SPIKE-OVERLAP-B"

    ids = [uuid.uuid4() for _ in range(10)]

    return [
        {
            "id": str(ids[0]),
            "kind": "road",
            "segment_key": seg_a,
            "status": "first_observation",
            "payload": {"seq": 0},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
        {
            "id": str(ids[1]),
            "kind": "road",
            "segment_key": seg_a,
            "status": "second_should_win",
            "payload": {"seq": 1},
            "created_at": _iso_z(t_later),
            "updated_at": _iso_z(t_later),
        },
        {
            "id": str(ids[2]),
            "kind": "road",
            "segment_key": seg_b,
            "status": "later_on_B",
            "payload": {"seq": 2},
            "created_at": _iso_z(t_mid),
            "updated_at": _iso_z(t_mid),
        },
        {
            "id": str(ids[3]),
            "kind": "road",
            "segment_key": seg_b,
            "status": "earlier_loses",
            "payload": {"seq": 3},
            "created_at": _iso_z(t_earlier),
            "updated_at": _iso_z(t_earlier),
        },
        {
            "id": str(ids[4]),
            "kind": "road",
            "segment_key": "SPIKE-SINGLE-1",
            "status": "solo",
            "payload": {},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
        {
            "id": str(ids[5]),
            "kind": "supply",
            "segment_key": "SPIKE-SUPPLY-1",
            "status": "stock_ok",
            "payload": {"qty": 3},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
        {
            "id": str(ids[6]),
            "kind": "road",
            "segment_key": None,
            "status": "no_segment_key",
            "payload": {},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
        {
            "id": str(ids[7]),
            "kind": "road",
            "segment_key": "SPIKE-SINGLE-2",
            "status": "z",
            "payload": {},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
        {
            "id": str(ids[8]),
            "kind": "sos",
            "status": "open",
            "payload": {"note": "spike-sos"},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
        {
            "id": str(ids[9]),
            "kind": "road",
            "segment_key": "SPIKE-SINGLE-3",
            "status": "tail",
            "payload": {},
            "created_at": _iso_z(t0),
            "updated_at": _iso_z(t0),
        },
    ]


def _sleep_ms(ms: int, log: logging.Logger, batch_id: str, label: str) -> None:
    if ms <= 0:
        return
    log.info("batch_id=%s sleep_ms=%s (%s)", batch_id, ms, label)
    time.sleep(ms / 1000.0)


def _verify_onnx(path: Path, log: logging.Logger) -> None:
    try:
        import numpy as np
        import onnxruntime as ort
    except ImportError as e:
        log.error("onnxruntime (and numpy) required for model verify step: %s", e)
        raise SystemExit(3) from e

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    x = np.random.randn(1, 4).astype(np.float32)
    out = sess.run(None, {name: x})
    log.info("onnxruntime smoke ok output_len=%s", len(out))


def main() -> None:
    p = argparse.ArgumentParser(description="Issue #4 gateway-shaped integration spike")
    p.add_argument(
        "--base-url",
        default=os.environ.get("GATEWAY_SIM_BASE_URL", "http://127.0.0.1:8000"),
        help="Zone A API base URL",
    )
    p.add_argument(
        "--gateway-id",
        default=os.environ.get("GATEWAY_SIM_GATEWAY_ID"),
        help="Gateway UUID (default: random each run)",
    )
    p.add_argument(
        "--model-name",
        default=os.environ.get("GATEWAY_SIM_MODEL_NAME", "road_decay_model"),
        help="Model artifact name for GET /v1/models/{name}/...",
    )
    p.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout seconds")
    p.add_argument(
        "--no-verify-tls",
        action="store_true",
        help="Disable TLS certificate verification (dev only)",
    )
    p.add_argument(
        "--download-key",
        default=os.environ.get("GATEWAY_SIM_DOWNLOAD_KEY"),
        help="X-Model-Download-Key if server requires it",
    )
    p.add_argument(
        "--reports-dev-key",
        default=os.environ.get("GATEWAY_SIM_REPORTS_KEY"),
        help="If set, GET /reports after push and print SPIKE-* rows",
    )
    p.add_argument("--sleep-ms", type=int, default=0, help="Sleep between major steps (milliseconds)")
    p.add_argument(
        "--sleep-before-push-ms",
        type=int,
        default=0,
        help="Sleep before POST /v1/sync/push (simulate slow client / latency)",
    )
    p.add_argument(
        "--repeat-idempotent-push",
        action="store_true",
        help="POST the same batch again; expect idempotent_replay true",
    )
    args = p.parse_args()

    gateway_id = args.gateway_id or str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    log = logging.getLogger("gateway_sim")
    log.info("batch_id=%s gateway_id=%s base_url=%s", batch_id, gateway_id, args.base_url)

    reports = _build_reports(now)
    body: dict[str, Any] = {
        "gateway_id": gateway_id,
        "batch_id": batch_id,
        "gateway_name": "gateway-sim",
        "reports": reports,
    }

    verify = not args.no_verify_tls
    headers_push = {
        "X-Gateway-Id": gateway_id,
        "X-Sync-Batch-Id": batch_id,
    }

    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=args.timeout, verify=verify) as client:
        _sleep_ms(args.sleep_before_push_ms, log, batch_id, "before_push")

        log.info("batch_id=%s POST /v1/sync/push reports=%s", batch_id, len(reports))
        r = client.post("/v1/sync/push", json=body, headers=headers_push)
        if r.status_code != 200:
            log.error("batch_id=%s push failed status=%s body=%s", batch_id, r.status_code, r.text[:2000])
            raise SystemExit(1)
        push_out = r.json()
        log.info(
            "batch_id=%s push ok idempotent_replay=%s record_count=%s applied_count=%s status=%s",
            batch_id,
            push_out.get("idempotent_replay"),
            push_out.get("record_count"),
            push_out.get("applied_count"),
            push_out.get("sync_log_status"),
        )

        if args.repeat_idempotent_push:
            log.info("batch_id=%s repeating identical POST (idempotency check)", batch_id)
            r2 = client.post("/v1/sync/push", json=body, headers=headers_push)
            if r2.status_code != 200:
                log.error("batch_id=%s repeat push failed: %s", batch_id, r2.text[:500])
                raise SystemExit(1)
            rep = r2.json()
            if not rep.get("idempotent_replay"):
                log.error("batch_id=%s expected idempotent_replay on second POST, got %s", batch_id, rep)
                raise SystemExit(1)
            log.info("batch_id=%s idempotent replay confirmed", batch_id)

        _sleep_ms(args.sleep_ms, log, batch_id, "after_push")

        if args.reports_dev_key:
            log.info("batch_id=%s GET /reports (dev)", batch_id)
            rr = client.get("/reports", headers={"X-Dev-Reports-Key": args.reports_dev_key})
            if rr.status_code != 200:
                log.warning("batch_id=%s reports dev GET failed status=%s", batch_id, rr.status_code)
            else:
                rows = rr.json()
                spike = [x for x in rows if "SPIKE-" in (x.get("segment_key") or "")]
                log.info("batch_id=%s spike-related report rows=%s", batch_id, len(spike))
                for row in spike[:12]:
                    log.info(
                        "batch_id=%s segment=%s status=%s id=%s updated_at=%s",
                        batch_id,
                        row.get("segment_key"),
                        row.get("status"),
                        row.get("id"),
                        row.get("updated_at"),
                    )

        _sleep_ms(args.sleep_ms, log, batch_id, "before_model_meta")

        meta_path = f"/v1/models/{args.model_name}/latest"
        log.info("batch_id=%s GET %s", batch_id, meta_path)
        mr = client.get(meta_path)
        if mr.status_code != 200:
            log.error("batch_id=%s model metadata failed status=%s body=%s", batch_id, mr.status_code, mr.text)
            raise SystemExit(1)
        meta = mr.json()
        sha = meta["sha256"]
        log.info(
            "batch_id=%s model name=%s version=%s sha256=%s size_bytes=%s",
            batch_id,
            meta.get("name"),
            meta.get("version"),
            sha,
            meta.get("size_bytes"),
        )

        _sleep_ms(args.sleep_ms, log, batch_id, "before_model_download")

        dl_headers: dict[str, str] = {}
        if args.download_key:
            dl_headers["X-Model-Download-Key"] = args.download_key

        file_path = f"/v1/models/{args.model_name}/latest/file"
        log.info("batch_id=%s GET %s -> temp file", batch_id, file_path)
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tf:
            out_path = Path(tf.name)
        try:
            with client.stream("GET", file_path, headers=dl_headers) as fr:
                if fr.status_code != 200:
                    log.error(
                        "batch_id=%s download failed status=%s",
                        batch_id,
                        fr.status_code,
                    )
                    raise SystemExit(1)
                h = hashlib.sha256()
                with out_path.open("wb") as f:
                    for chunk in fr.iter_bytes():
                        h.update(chunk)
                        f.write(chunk)
            digest = h.hexdigest()
            if digest.lower() != str(sha).lower():
                log.error("batch_id=%s sha256 mismatch local=%s remote=%s", batch_id, digest, sha)
                raise SystemExit(2)
            log.info("batch_id=%s downloaded bytes sha256 matches metadata", batch_id)

            _verify_onnx(out_path, log)
        finally:
            out_path.unlink(missing_ok=True)

    log.info("batch_id=%s spike completed successfully", batch_id)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        logging.getLogger("gateway_sim").exception("fatal: %s", e)
        sys.exit(1)
