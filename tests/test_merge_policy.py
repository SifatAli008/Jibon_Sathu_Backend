import uuid
from datetime import UTC, datetime

from app.schemas.sync import ReportItem, ReportKind
from app.services.merge_policy import (
    MutableMergeAction,
    SosMergeAction,
    decide_road_like_merge,
    decide_sos_merge,
    incoming_beats_existing_row,
)


def _road_item(*, rid: uuid.UUID, gw_ts: datetime, seg: str = "S1", status: str = "ok") -> ReportItem:
    return ReportItem(
        id=rid,
        kind=ReportKind.road,
        segment_key=seg,
        status=status,
        payload={},
        created_at=gw_ts,
        updated_at=gw_ts,
    )


def test_incoming_wins_on_newer_updated_at() -> None:
    t_old = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    t_new = datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC)
    g = uuid.uuid4()
    ex_id = uuid.uuid4()
    inc = _road_item(rid=uuid.uuid4(), gw_ts=t_new, status="blocked")
    assert incoming_beats_existing_row(inc, g, t_old, g, ex_id) is True


def test_tie_break_lexicographic_gateway_then_id() -> None:
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    gw_low = uuid.UUID("00000000-0000-4000-8000-000000000001")
    gw_high = uuid.UUID("ffffffff-ffff-4fff-ffff-ffffffffffff")
    id_low = uuid.UUID("00000000-0000-4000-8000-000000000002")
    id_high = uuid.UUID("ffffffff-ffff-4fff-ffff-ffffffffffff")

    inc = _road_item(rid=id_low, gw_ts=t)
    assert incoming_beats_existing_row(inc, gw_high, t, gw_low, id_high) is True
    assert incoming_beats_existing_row(inc, gw_low, t, gw_high, id_high) is False


def test_decide_road_segment_merge_update_canonical_id() -> None:
    t_old = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    t_new = datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC)
    canonical_id = uuid.uuid4()
    incoming_id = uuid.uuid4()
    g = uuid.uuid4()
    inc = _road_item(rid=incoming_id, gw_ts=t_new, status="winner")
    snap = {"id": canonical_id, "updated_at": t_old, "source_gateway_id": g}
    d = decide_road_like_merge(
        incoming=inc,
        incoming_gateway_id=g,
        canonical_existing=snap,
    )
    assert d.action == MutableMergeAction.update
    assert d.row_id == canonical_id


def test_decide_sos_duplicate_is_noop() -> None:
    assert decide_sos_merge(existing_row={"id": uuid.uuid4()}) == SosMergeAction.noop
    assert decide_sos_merge(existing_row=None) == SosMergeAction.insert
