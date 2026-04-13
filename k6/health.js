/**
 * Baseline load: GET /health (includes DB ping).
 *
 * Usage:
 *   k6 run k6/health.js
 *   k6 run -e BASE_URL=http://127.0.0.1:8000 k6/health.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { baseUrl } from "./lib.js";

export const options = {
  scenarios: {
    health: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 20 },
        { duration: "1m", target: 50 },
        { duration: "30s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

export default function () {
  const url = `${baseUrl()}/health`;
  const res = http.get(url);
  check(res, {
    "status 200": (r) => r.status === 200,
    "db ok": (r) => {
      try {
        const j = r.json();
        return j && j.status === "ok" && j.db === "ok";
      } catch (_) {
        return false;
      }
    },
  });
  sleep(0.1);
}
