"""Monotonic `server_sequence_id` allocation (Issue #5).

Conflict resolution uses **server-assigned sequence** ordering, not wall-clock `updated_at` alone,
because gateway clocks may skew in disaster zones. Each successful mutation consumes one value from
`server_sequence_global` so pull/merge ordering stays consistent with Zone A's commit order.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def next_server_sequence(session: AsyncSession) -> int:
    """Return the next globally unique, monotonically increasing sequence id."""
    res = await session.scalar(text("SELECT nextval('server_sequence_global')"))
    if res is None:
        raise RuntimeError("nextval(server_sequence_global) returned NULL")
    return int(res)
