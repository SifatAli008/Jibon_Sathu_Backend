/**
 * Shared helpers for k6 scripts (ES5-compatible for k6).
 */

export function uuidv4() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function baseUrl() {
  return (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

/** ISO8601 UTC with Z suffix (matches API examples). */
export function isoNowZ() {
  const d = new Date();
  const pad = (n) => (n < 10 ? "0" : "") + n;
  return (
    d.getUTCFullYear() +
    "-" +
    pad(d.getUTCMonth() + 1) +
    "-" +
    pad(d.getUTCDate()) +
    "T" +
    pad(d.getUTCHours()) +
    ":" +
    pad(d.getUTCMinutes()) +
    ":" +
    pad(d.getUTCSeconds()) +
    "Z"
  );
}
