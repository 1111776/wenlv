"""审批超时自动终止（说明书 S8 / §10 规则10）。

Worker 周期性调用 ``expire_stale_reviews()``：
- 扫描 status ∈ {pending, reviewing} 且超过 ``REVIEW_TIMEOUT_HOURS`` 的审核记录；
- 自动置为 rejected（视为驳回），行程置 completed + rejected=true；
- 写审计日志。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import ReviewRecord, TravelPlan
from app.models.travel_plan import PLAN_STATUS
from app.services.audit import add_audit

logger = get_logger(__name__)


async def expire_stale_reviews() -> int:
    """扫描并终止超时未处理的审核，返回处理条数。

    注意：``created_at`` 为 ``TIMESTAMP WITHOUT TIME ZONE``（func.now()），
    这里统一用无时区 UTC datetime 比较，避免 asyncpg 时区类型不匹配。
    """
    now = datetime.utcnow()
    deadline = now - timedelta(hours=settings.review_timeout_hours)

    # 找超时且未终态的审核记录
    async with session_scope() as db:
        result = await db.execute(
            select(ReviewRecord).where(
                ReviewRecord.status.in_(["pending", "reviewing"]),
                ReviewRecord.created_at < deadline,
            )
        )
        stale = list(result.scalars().all())

    count = 0
    for review in stale:
        try:
            async with session_scope() as db:
                r = await db.get(ReviewRecord, review.id)
                # 双重校验：可能已被其他协程处理
                if r is None or r.status not in ("pending", "reviewing"):
                    continue
                r.status = "rejected"
                r.decision = "rejected"
                r.reviewed_at = now
                r.comment = (r.comment or "") + "（系统：审批超时自动驳回）"
                await db.flush()

                # 行程置 completed + rejected=true（S8：自动终止，不升级）
                plan = await db.get(TravelPlan, r.plan_id)
                if plan is not None and plan.status == PLAN_STATUS["SUSPENDED"]:
                    plan.status = PLAN_STATUS["COMPLETED"]
                    plan.rejected = True
                    await db.flush()

                await add_audit(
                    db,
                    action="review_timeout",
                    plan_id=r.plan_id,
                    detail={"review_id": str(r.id), "reason": r.reason},
                )
            count += 1
            logger.info("审批超时自动驳回 plan=%s review=%s", review.plan_id, review.id)
        except Exception as exc:
            logger.error("审批超时处理异常 review=%s：%s", review.id, exc)

    return count
