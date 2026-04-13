/**
 * GET /v1/analytics/map-layers and /v1/analytics/sos-queue
 * Requires DASHBOARD_ADMIN_KEY on the API and the same value in env:
 *
 *   k6 run -e DASHBOARD_ADMIN_KEY=your-key k6/analytics.js
 */
import exec from "k6/execution";
import http from "k6/http";
import { check, sleep } from "k6";
import { baseUrl } from "./lib.js";

const key = __ENV.DASHBOARD_ADMIN_KEY || "";

export function setup() {
  if (!key) {
    exec.test.abort("Set DASHBOARD_ADMIN_KEY (e.g. -e DASHBOARD_ADMIN_KEY=...)");
  }
}

export const options = {
  scenarios: {
    analytics: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 10 },
        { duration: "40s", target: 10 },
        { duration: "20s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const h = { "X-Dashboard-Admin-Key": key };
  const root = baseUrl();
  const r1 = http.get(`${root}/v1/analytics/map-layers`, { headers: h });
  check(r1, { "map-layers 200": (r) => r.status === 200 });
  const r2 = http.get(`${root}/v1/analytics/sos-queue`, { headers: h });
  check(r2, { "sos-queue 200": (r) => r.status === 200 });
  sleep(0.2);
}
