"""行程相关请求/响应模型（说明书 7.2）。"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ElderDetail(BaseModel):
    """单个老人信息：年龄 + 性别（用于按年龄分档计算门票）。"""

    age: int = Field(default=60, ge=0, le=120)
    gender: str = "男"  # 男 / 女


class ChildDetail(BaseModel):
    """单个儿童信息：年龄 + 身高 + 购票状态（用于门票分档和交通购票）。"""

    age: int = Field(default=6, ge=0, le=17)
    height: float | None = Field(default=None, ge=0, le=2.5)  # 身高（米），可选
    seat: bool = Field(default=False)  # 交通购票：是否单独占座（高铁 6 岁以下不占座可免票）


class StudentDetail(BaseModel):
    """单个学生信息：学历（用于判断学生票资格，旅游出行不适用学生票）。"""

    level: str = Field(default="大学本科")  # 小学/初中/高中/中专/大专/本科/研究生等


class Party(BaseModel):
    """出行人组成。"""

    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    elders: int = Field(default=0, ge=0)  # 老人数量
    elder_status: str | None = None  # 老人生活状态：健康/行动不便/需轮椅/慢病等
    adult_relation: str | None = None  # 成人关系：情侣/单身/未婚/已婚/家庭/朋友等
    students: int = Field(default=0, ge=0)  # 学生数量（高铁学生票仅限家校往返，旅游不适用）
    elders_detail: list[ElderDetail] = Field(default_factory=list)  # 老人明细（年龄+性别，可多个）
    children_detail: list[ChildDetail] = Field(default_factory=list)  # 儿童明细（年龄+身高+占座，可多个）
    students_detail: list[StudentDetail] = Field(default_factory=list)  # 学生明细（学历，可多个）


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
    completed_at: Any = None


class PlanListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    rejected: bool
    resume_from: str | None
    progress: dict
    created_at: Any
    completed_at: Any = None


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
