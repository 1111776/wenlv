"""Human Review Agent：人机协作审核路由（说明书 §5.1 第 7 节点 / §5.2）。

不调用 LLM，只做路由：
- 写 review_records(decision=pending)；
- DB status=suspended；文件 resume_from=human_review:wait；
- 发布 hitl_suspended 事件；
- 直接结束本次图执行（Worker ack，释放，不阻塞等待）。
"""

from __future__ import annotations

import uuid

from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.context import NodeContext
from app.graph.state import TravelState
from app.models import ReviewRecord

logger = get_logger(__name__)


def _build_reason_and_detail(state: TravelState) -> tuple[str, dict]:
    """根据风险类型确定挂起原因与证据。"""
    from app.core.config import settings

    total_budget = state.get("total_budget", 0.0)
    # 预算金额超阈值（默认 30000）
    if total_budget > settings.budget_review_threshold:
        return "budget_over", {
            "total_budget": total_budget,
            "threshold": settings.budget_review_threshold,
            "说明": f"预算 {total_budget} 元超过审核阈值 {settings.budget_review_threshold} 元",
        }
    # 超预算比例（默认 20%）——与 route_after_budget 口径一致
    if state.get("over_budget_ratio", 0) > settings.budget_over_ratio:
        return "budget_over", {
            "over_budget_ratio": state.get("over_budget_ratio"),
            "threshold_ratio": settings.budget_over_ratio,
        }
    if state.get("night_risk"):
        return "risk_night", {"night_risk": True, "时段": "22:00-06:00"}
    if state.get("sentiment_risk"):
        return "sentiment_risk", {"sentiment_risk": True}
    return "budget_over", {}


async def human_review_node(state: TravelState) -> dict:
    """挂起等待人工审批（结束后图暂停，审批通过后重新入队续跑）。"""
    plan_id = state["plan_id"]
    reason, detail = _build_reason_and_detail(state)

    async with NodeContext(plan_id) as ctx:
        # 写审核记录
        review = ReviewRecord(
            plan_id=uuid.UUID(plan_id),
            reason=reason,
            trigger_detail=detail,
            decision="pending",
            status="pending",
        )
        ctx.db.add(review)
        await ctx.db.flush()

        # 初始化 Redis 审核锁 hash，供 claim 的 CAS 使用
        from app.services.lock import init_review_lock

        await init_review_lock(review.id)

        # 更新状态 + 文件 + 事件
        await ctx.advance(
            status="suspended",
            resume_from="human_review:wait",
            body=await ctx.build_body(hitl={"reason": reason, "detail": detail}),
            event="hitl_suspended",
            agent="human_review",
            progress=ctx.progress(),
            hitl={"reason": reason, "detail": detail},
        )

    return {"hitl": {"reason": reason, "detail": detail}}
