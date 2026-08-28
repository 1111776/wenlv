"""审核路由（说明书 7.3）。

- GET  /api/reviews/pending：待审列表
- GET  /api/reviews/{id}：审核详情 + HITL 证据
- POST /api/reviews/{id}/claim：抢占（Lua CAS）
- POST /api/reviews/{id}/decision：通过/驳回
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import Err
from app.models import ReviewRecord, TravelPlan
from app.models.travel_plan import PLAN_STATUS
from app.schemas.common import ok
from app.schemas.review import (
    ClaimOut,
    DecisionRequest,
    ReviewDetailOut,
    ReviewItem,
    ReviewPendingOut,
)
from app.services import lock, queue
from app.services.audit import add_audit

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/pending")
async def pending_reviews(request: Request, db: AsyncSession = Depends(get_db)):
    """待审队列（supervisor）。"""
    result = await db.execute(
        select(ReviewRecord)
        .where(ReviewRecord.status.in_(["pending", "reviewing"]))
        .order_by(ReviewRecord.created_at)
    )
    records = result.scalars().all()

    items = []
    for r in records:
        plan = await db.get(TravelPlan, r.plan_id)
        items.append(
            ReviewItem(
                id=r.id,
                plan_id=r.plan_id,
                reason=r.reason,
                trigger_detail=r.trigger_detail,
                status=r.status,
                created_at=r.created_at,
                plan_title=plan.title if plan else None,
                plan_query=plan.query if plan else None,
            ).model_dump(mode="json")
        )
    return ok(ReviewPendingOut(items=items, total=len(items)).model_dump(mode="json"))


@router.get("/{review_id}")
async def get_review(review_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """审核详情。"""
    r = await db.get(ReviewRecord, review_id)
    if r is None:
        raise Err.NOT_FOUND.to_http()
    plan = await db.get(TravelPlan, r.plan_id)
    return ok(
        ReviewDetailOut(
            id=r.id,
            plan_id=r.plan_id,
            reason=r.reason,
            trigger_detail=r.trigger_detail,
            status=r.status,
            decision=r.decision,
            comment=r.comment,
            plan_summary={
                "query": plan.query if plan else None,
                "preferences": plan.preferences if plan else None,
                "total_budget": float(plan.total_budget) if plan and plan.total_budget else None,
            },
        ).model_dump(mode="json")
    )


@router.post("/{review_id}/claim")
async def claim_review(review_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """抢占审核（supervisor）。

    正确性唯一由 DB 条件更新保证：``UPDATE ... WHERE status='pending'``。
    Redis 锁只做加速/降冲突，任何 Redis 状态残留或丢失都不影响正确性——
    Redis CAS 失败时，以 DB 当前状态强制重置 Redis，避免双写不一致卡死。
    """
    user = request.state.user
    reviewer_id = user["id"]

    # 先读 DB 当前状态
    r = await db.get(ReviewRecord, review_id)
    if r is None:
        raise Err.NOT_FOUND.to_http()

    # DB 条件更新：仅当仍为 pending 才置 reviewing（正确性唯一保证）
    result = await db.execute(
        update(ReviewRecord)
        .where(ReviewRecord.id == review_id, ReviewRecord.status == "pending")
        .values(status="reviewing", reviewer_id=reviewer_id, claimed_at=datetime.now(timezone.utc))
    )
    if result.rowcount == 0:
        raise Err.REVIEW_CONFLICT.to_http()

    # Redis CAS 辅助：DB 已成功，这里强制同步 Redis 状态（幂等，失败不影响正确性）
    claimed = await lock.claim_review(review_id, reviewer_id)
    if not claimed:
        # Redis 状态残留不一致，强制重置为当前 DB 状态
        await lock.reset_review_lock(review_id, status="reviewing", reviewer_id=str(reviewer_id))

    await add_audit(db, action="review_claim", actor_id=reviewer_id, plan_id=r.plan_id)
    return ok(ClaimOut(ok=True).model_dump())


@router.post("/{review_id}/decision")
async def decide_review(review_id: uuid.UUID, body: DecisionRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """通过/驳回（必须已是本人 reviewing）。"""
    user = request.state.user
    reviewer_id = user["id"]

    r = await db.get(ReviewRecord, review_id)
    if r is None:
        raise Err.NOT_FOUND.to_http()
    if r.reviewer_id != reviewer_id:
        raise Err.FORBIDDEN.to_http()
    if r.status != "reviewing":
        raise Err.REVIEW_CONFLICT.to_http()

    # DB 条件更新：decision 仍为 pending 才生效（防重复审批）
    result = await db.execute(
        update(ReviewRecord)
        .where(ReviewRecord.id == review_id, ReviewRecord.decision == "pending")
        .values(
            decision=body.decision,
            status="approved" if body.decision == "approved" else "rejected",
            comment=body.comment,
            reviewed_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount == 0:
        raise Err.REVIEW_CONFLICT.to_http()

    # 更新行程状态
    plan = await db.get(TravelPlan, r.plan_id)
    if plan is not None:
        if body.decision == "approved":
            plan.status = PLAN_STATUS["RUNNING"]
            plan.resume_from = "report"
            await db.flush()
        else:
            # 驳回 → 终态（S5：不 rework）
            plan.status = PLAN_STATUS["COMPLETED"]
            plan.rejected = True
            await db.flush()

    await add_audit(
        db,
        action="review_decision",
        actor_id=reviewer_id,
        plan_id=r.plan_id,
        detail={"decision": body.decision, "comment": body.comment},
    )

    # 关键：入队前先 commit，确保 Worker 消费时 DB 状态已持久化（避免读写竞态）
    await db.commit()

    if body.decision == "approved":
        # 审批通过 → 重新入队续跑（S6/S27）
        await queue.publish_resume(r.plan_id, reason="approved")

    return ok({"plan_id": str(r.plan_id), "decision": body.decision})
