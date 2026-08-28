"""审核相关请求/响应模型（说明书 7.3）。"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ReviewItem(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    reason: str
    trigger_detail: dict | None
    status: str
    created_at: Any
    # 行程摘要（联表带出，便于审核台展示）
    plan_title: str | None = None
    plan_query: str | None = None


class ReviewPendingOut(BaseModel):
    items: list[ReviewItem]
    total: int


class ReviewDetailOut(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    reason: str
    trigger_detail: dict | None
    status: str
    decision: str
    comment: str | None
    # HITL 证据
    plan_summary: dict | None = None


class ClaimOut(BaseModel):
    ok: bool


class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    comment: str | None = None
