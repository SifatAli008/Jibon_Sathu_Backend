"""Deterministic priority scoring for M6 triage (Issue #11). Pure functions for unit tests."""

from __future__ import annotations

from typing import Any


def compute_priority_score(kind: str, status: str, payload: dict[str, Any]) -> float:
    """
    Higher = more urgent. Range roughly 0–100 for dashboard sorting.

    Rules are intentionally simple; product can replace with ML or policy tables later.
    """
    score = 15.0
    k = (kind or "").lower()
    st = (status or "").lower()

    if k == "sos":
        score = 100.0
    elif k == "road" and ("blocked" in st or "damaged" in st or "flood" in st):
        score = 75.0
    elif k == "supply" and ("critical" in st or "shortage" in st):
        score = 70.0

    if payload.get("priority") == "high":
        score = min(100.0, score + 20.0)
    if payload.get("casualties") or payload.get("injured"):
        score = min(100.0, score + 15.0)

    return float(min(100.0, max(0.0, score)))
