from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"
    __table_args__ = (UniqueConstraint("gateway_id", "batch_id", name="uq_sync_logs_gateway_batch"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gateway_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gateways.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    gateway: Mapped["Gateway"] = relationship(back_populates="sync_logs")
