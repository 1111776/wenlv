"""行程相关请求/响应模型（说明书 7.2）。"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class Party(BaseModel):
    """出行人组成。"""

    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    elders: int = Field(default=0, ge=0)  # 老人数量
    elder_status: str | None = None  # 老人生活状态：健康/行动不便/需轮椅/慢病等


class PlanCreateRequest(BaseModel):
    """创建行程请求。query 必填，其余可选，Intake 可补全。"""

    query: str = Field(..., min_length=1)
    origin: str | None = None  # 出发地
    destination: str | None = None
    days: int | None = Field(default=None, ge=1)
    start_date: str | None = None  # 出发日期 YYYY-MM-DD
    end_date: str | None = None  # 返程日期 YYYY-MM-DD
    budget_limit: float | None = Field(default=None, gt=0)
    party: Party | None = None
    tags: list[str] | None = None


class PlanCreateOut(BaseModel):
    plan_id: uuid.UUID
    status: str


class ItineraryUpdateRequest(BaseModel):
    """手动修改行程规划（增删景点/餐饮，不重新生成）。

    前端把完整的新 daily_plan 传回来，后端直接覆盖 Itinerary 结果。
    """

    daily_plan: list[dict] = Field(default_factory=list)


class PlanStatusOut(BaseModel):
    """【压测主接口】轻量状态。"""

    plan_id: uuid.UUID
    status: str
    resume_from: str | None
    version: int
    progress: dict  # {"done": int, "total": int}


class PlanDetailOut(BaseModel):
    """行程详情。"""

    id: uuid.UUID
    title: str | None
    status: str
    rejected: bool
    query: str
    preferences: dict | None
    budget_limit: float | None
    total_budget: float | None
    resume_from: str | None
    state_version: int
    progress: dict
    created_at: Any


class PlanListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    rejected: bool
    resume_from: str | None
    progress: dict
    created_at: Any


class PlanListOut(BaseModel):
    items: list[PlanListItem]
    total: int


class PlanFileOut(BaseModel):
    markdown: str
    version: int


class BudgetItemOut(BaseModel):
    category: str
    item: str
    amount: float


class ReportOut(BaseModel):
    markdown: str
    budget: list[BudgetItemOut]
    quality: str | None = None
