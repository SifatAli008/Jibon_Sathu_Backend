"""report triage_status + priority_score (Issue #11)

Revision ID: 20260412_0006
Revises: 20260412_0005
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260412_0006"
down_revision: Union[str, None] = "20260412_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "triage_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("reports", sa.Column("priority_score", sa.Float(), nullable=True))
    op.create_index("ix_reports_triage_status", "reports", ["triage_status"], unique=False)
    op.create_index("ix_reports_priority_score", "reports", ["priority_score"], unique=False)
    op.alter_column("reports", "triage_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_reports_priority_score", table_name="reports")
    op.drop_index("ix_reports_triage_status", table_name="reports")
    op.drop_column("reports", "priority_score")
    op.drop_column("reports", "triage_status")
