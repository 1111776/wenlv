"""经典线路模板表（旅行社固定路线库）。

旅行社有固定线路，用户选模板即可秒出行程（不走 8 Agent），再按需微调。
模板存结构化 JSON：destination/days/tags/suitable_for/budget_ref/daily_plan。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RouteTemplate(Base):
    __tablename__ = "route_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # 线路名
    destination: Mapped[str] = mapped_column(String(64), nullable=False)  # 目的地
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list)  # 标签
    suitable_for: Mapped[str] = mapped_column(String(128), default="")  # 适合人群
    budget_ref: Mapped[int] = mapped_column(Integer, default=0)  # 参考预算（元/人）
    description: Mapped[str] = mapped_column(Text, default="")  # 一句话简介
    daily_plan: Mapped[list] = mapped_column(JSONB, default=list)  # 每日行程（结构化）
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
