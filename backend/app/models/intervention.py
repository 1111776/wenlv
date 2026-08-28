"""强干预流水表（工单 7 §4.2）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False)  # = plan_id 字符串
    operator: Mapped[str] = mapped_column(String(64), nullable=False)  # supervisor 用户名 / service:xxx
    target_entity: Mapped[dict] = mapped_column(JSONB, nullable=False)
    patch: Mapped[dict] = mapped_column(JSONB, nullable=False)  # 图属性补丁
    state_patch: Mapped[dict] = mapped_column(JSONB, nullable=False)  # LangGraph State 补丁
    prev_state: Mapped[dict | None] = mapped_column(JSONB)  # 干预前快照
    nonce: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")  # applied/consumed/rolled_back
    intervention_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_intervention_thread", "thread_id"),)
