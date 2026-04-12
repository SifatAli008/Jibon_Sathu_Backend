"""initial schema: gateways, reports, sync_logs

Revision ID: 20260412_0001
Revises:
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260412_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("segment_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_gateway_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_gateway_id"], ["gateways.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_kind", "reports", ["kind"], unique=False)
    op.create_index("ix_reports_segment_key", "reports", ["segment_key"], unique=False)
    op.create_index("ix_reports_source_gateway_id", "reports", ["source_gateway_id"], unique=False)
    op.create_index("ix_reports_kind_segment", "reports", ["kind", "segment_key"], unique=False)
    op.create_index("ix_reports_updated_at", "reports", ["updated_at"], unique=False)
    op.create_table(
        "sync_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("applied_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway_id", "batch_id", name="uq_sync_logs_gateway_batch"),
    )
    op.create_index("ix_sync_logs_gateway_id", "sync_logs", ["gateway_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sync_logs_gateway_id", table_name="sync_logs")
    op.drop_table("sync_logs")
    op.drop_index("ix_reports_updated_at", table_name="reports")
    op.drop_index("ix_reports_kind_segment", table_name="reports")
    op.drop_index("ix_reports_source_gateway_id", table_name="reports")
    op.drop_index("ix_reports_segment_key", table_name="reports")
    op.drop_index("ix_reports_kind", table_name="reports")
    op.drop_table("reports")
    op.drop_table("gateways")
