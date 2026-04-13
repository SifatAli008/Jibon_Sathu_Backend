/**
 * Load test: POST /v1/sync/push with empty report batches.
 * Each iteration uses a NEW gateway_id + batch_id so:
 * - Idempotency does not short-circuit merges
 * - Rate limit (default 120/min per X-Gateway-Id) is spread across many virtual gateways
 *
 * If you must use a SINGLE gateway, lower VUs or raise SYNC_RATE_LIMIT in API .env for the test.
 *
 * With REQUIRE_GATEWAY_AUTH=true, set GATEWAY_SECRET and provision that gateway — this script
 * is intended for REQUIRE_GATEWAY_AUTH=false (typical local dev).
 *
 * Usage:
 *   k6 run k6/sync-push.js
 *   k6 run -e BASE_URL=http://127.0.0.1:8000 k6/sync-push.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { baseUrl, uuidv4 } from "./lib.js";

export const options = {
  scenarios: {
    sync_push: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<2000"],
  },
};

export default function () {
  const gid = uuidv4();
  const bid = uuidv4();
  const url = `${baseUrl()}/v1/sync/push`;
  const body = JSON.stringify({
    gateway_id: gid,
    batch_id: bid,
    gateway_name: "k6-load",
    reports: [],
  });
  const headers = {
    "Content-Type": "application/json",
    "X-Gateway-Id": gid,
    "X-Sync-Batch-Id": bid,
  };
  const secret = __ENV.GATEWAY_SECRET || "";
  if (secret) {
    headers.Authorization = "Bearer " + secret;
  }

  const res = http.post(url, body, { headers });
  check(res, {
    "status 200": (r) => r.status === 200,
    "applied": (r) => {
      try {
        const j = r.json();
        return j && j.record_count === 0 && j.applied_count === 0;
      } catch (_) {
        return false;
      }
    },
  });
  sleep(0.05);
}
