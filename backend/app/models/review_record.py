"""人工审核记录表（说明书 6.5 review_records）。

同一 plan 同时只允许一条 pending|reviewing 记录（防重复挂起）。
decision: pending | approved | rejected
status:   pending | reviewing | approved | rejected（reviewing 不进 DB 主状态，见 S31）
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

REVIEW_REASON = {
    "BUDGET_OVER": "budget_over",
    "RISK_NIGHT": "risk_night",
    "SENTIMENT_RISK": "sentiment_risk",
}


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("travel_plans.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_detail: Mapped[dict | None] = mapped_column(JSONB)  # 超支金额/路段/舆情证据
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # 抢占后填写
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    comment: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_reviews_pending", "status"),
        Index("idx_reviews_plan", "plan_id"),
    )
