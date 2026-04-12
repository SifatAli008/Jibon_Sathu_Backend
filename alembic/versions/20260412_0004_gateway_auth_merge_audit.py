"""gateway auth + merge audit (Issues #7–#8)

Revision ID: 20260412_0004
Revises: 20260412_0003
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260412_0004"
down_revision: Union[str, None] = "20260412_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("gateways", sa.Column("auth_secret_hash", sa.Text(), nullable=True))
    op.add_column("gateways", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_logs", sa.Column("merge_audit", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("sync_logs", "merge_audit")
    op.drop_column("gateways", "revoked_at")
    op.drop_column("gateways", "auth_secret_hash")
