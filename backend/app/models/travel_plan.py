"""行程计划主表（说明书 6.3 travel_plans）。

状态枚举（§4.3.2）：
planning | running | suspended | recovering | completed | failed | cancelled
终态：completed / failed / cancelled。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 行程状态常量（集中定义，避免魔法字符串散落）
PLAN_STATUS = {
    "PLANNING": "planning",
    "RUNNING": "running",
    "SUSPENDED": "suspended",
    "RECOVERING": "recovering",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}
TERMINAL_STATUSES = {
    PLAN_STATUS["COMPLETED"],
    PLAN_STATUS["FAILED"],
    PLAN_STATUS["CANCELLED"],
}


class TravelPlan(Base):
    __tablename__ = "travel_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PLAN_STATUS["PLANNING"])
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 审核驳回（S5）
    query: Mapped[str] = mapped_column(Text, nullable=False)  # 原始自然语言需求
    preferences: Mapped[dict | None] = mapped_column(JSONB)  # Intake 输出
    budget_limit: Mapped[float | None] = mapped_column(Numeric(12, 2))  # 用户预算
    total_budget: Mapped[float | None] = mapped_column(Numeric(12, 2))  # Budget 汇总
    resume_from: Mapped[str | None] = mapped_column(String(128))  # 与文件 YAML 同步
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)  # workspace/{id}/
    idempotency_key: Mapped[str | None] = mapped_column(String(64))  # 与 user_id 组合唯一
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_plans_status", "status"),
        Index("idx_plans_user_created", "user_id", "created_at"),
        # 部分唯一索引：同一用户同一幂等键只允许一条（S26）
        Index(
            "uq_plans_user_idem",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=idempotency_key.isnot(None),
        ),
    )
