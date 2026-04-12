"""server_sequence_id + tombstones (Issue #5)

Revision ID: 20260412_0003
Revises: 20260412_0002
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260412_0003"
down_revision: Union[str, None] = "20260412_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS server_sequence_global AS BIGINT START 1 INCREMENT 1"))

    op.add_column("reports", sa.Column("server_sequence_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "reports",
        sa.Column("is_tombstone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.execute(
        sa.text(
            """
            UPDATE reports r
            SET server_sequence_id = s.seq
            FROM (
                SELECT id, nextval('server_sequence_global') AS seq
                FROM reports
                ORDER BY id
            ) s
            WHERE r.id = s.id
            """
        )
    )

    op.alter_column("reports", "server_sequence_id", nullable=False)
    op.create_index("ix_reports_server_sequence_id", "reports", ["server_sequence_id"], unique=False)
    op.create_unique_constraint("uq_reports_server_sequence_id", "reports", ["server_sequence_id"])

    op.add_column("sync_logs", sa.Column("server_sequence_id", sa.BigInteger(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE sync_logs sl
            SET server_sequence_id = s.seq
            FROM (
                SELECT id, nextval('server_sequence_global') AS seq
                FROM sync_logs
                ORDER BY id
            ) s
            WHERE sl.id = s.id
            """
        )
    )
    op.alter_column("sync_logs", "server_sequence_id", nullable=False)
    op.create_unique_constraint("uq_sync_logs_server_sequence_id", "sync_logs", ["server_sequence_id"])


def downgrade() -> None:
    op.drop_constraint("uq_sync_logs_server_sequence_id", "sync_logs", type_="unique")
    op.drop_column("sync_logs", "server_sequence_id")

    op.drop_constraint("uq_reports_server_sequence_id", "reports", type_="unique")
    op.drop_index("ix_reports_server_sequence_id", table_name="reports")
    op.drop_column("reports", "is_tombstone")
    op.drop_column("reports", "server_sequence_id")

    op.execute(sa.text("DROP SEQUENCE IF EXISTS server_sequence_global"))
