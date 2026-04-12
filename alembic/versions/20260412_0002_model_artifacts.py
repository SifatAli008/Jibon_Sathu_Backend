"""model_artifacts for ONNX distribution

Revision ID: 20260412_0002
Revises: 20260412_0001
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260412_0002"
down_revision: Union[str, None] = "20260412_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("file_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_model_artifacts_name_version"),
    )
    op.create_index("ix_model_artifacts_name", "model_artifacts", ["name"], unique=False)
    op.create_index(
        "uq_model_artifacts_one_latest_per_name",
        "model_artifacts",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_latest IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_model_artifacts_one_latest_per_name", table_name="model_artifacts")
    op.drop_index("ix_model_artifacts_name", table_name="model_artifacts")
    op.drop_table("model_artifacts")
