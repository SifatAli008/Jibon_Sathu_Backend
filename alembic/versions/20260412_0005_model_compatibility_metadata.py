"""model compatibility metadata (Issue #9)

Revision ID: 20260412_0005
Revises: 20260412_0004
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260412_0005"
down_revision: Union[str, None] = "20260412_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_artifacts",
        sa.Column("min_gateway_version", sa.Text(), nullable=False, server_default="0.0.0"),
    )
    op.add_column("model_artifacts", sa.Column("input_schema_hash", sa.Text(), nullable=True))
    op.alter_column("model_artifacts", "min_gateway_version", server_default=None)


def downgrade() -> None:
    op.drop_column("model_artifacts", "input_schema_hash")
    op.drop_column("model_artifacts", "min_gateway_version")
