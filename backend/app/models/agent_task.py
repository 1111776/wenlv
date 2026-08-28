"""Agent 任务表（说明书 6.4 agent_tasks）。

Planner 产出 >=10 条 web_research 任务；其余 agent 各一条执行记录。
task 状态：pending | running | completed | failed | blocked（注入拦截）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TASK_STATUS = {
    "PENDING": "pending",
    "RUNNING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "BLOCKED": "blocked",
}


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("travel_plans.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 全局顺序
    page_no: Mapped[int | None] = mapped_column(Integer)  # 仅 web_research，1-based
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=TASK_STATUS["PENDING"])
    task_data: Mapped[dict | None] = mapped_column(JSONB)  # url / seed_id / 标题
    result: Mapped[dict | None] = mapped_column(JSONB)  # 输出，含 quality
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_tasks_plan_order", "plan_id", "order_index", unique=True),
        Index("idx_tasks_plan_status", "plan_id", "status"),
    )
