"""记忆事件流水表（工单 7 §4.2）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MemoryEvent(Base):
    __tablename__ = "memory_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column()  # 可空（跨行程记忆）
    source_node: Mapped[str] = mapped_column(String(32), nullable=False)  # intake/sentiment/itinerary
    raw_excerpt: Mapped[str | None] = mapped_column(Text)
    extracted: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # 抽取出的三元组
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok/failed/merged
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_mem_plan", "plan_id"),)
