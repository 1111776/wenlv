"""审计日志表（说明书 6.7 audit_logs，安全验收必建）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column()  # 可空（系统拦截）
    plan_id: Mapped[uuid.UUID | None] = mapped_column()  # 可空（匿名拦截）
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # login/plan_create/security_block/...
    target: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict | None] = mapped_column(JSONB)  # 注入 pattern / 原文片段 / source_url
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_audit_plan", "plan_id", "created_at"),
        Index("idx_audit_action", "action", "created_at"),
    )
