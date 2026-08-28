"""编排服务：运行 LangGraph 图 + 断点恢复（说明书 §4.3 / 场景 B）。

职责：
- ``run_plan``：从 DB 组装初始 TravelState 并跑图；
- ``resume_plan``：崩溃/HITL 通过后，从文件 resume_from 组装 state 续跑；
- 依据 completed_nodes / resume_from 让已完成的节点幂等跳过（S25）。

模型：图采用「一次 invoke 跑完一轮」，恢复时重新 invoke，
各节点内部幂等（已完成的 web_research 页不重复请求）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.builder import graph
from app.graph.state import TravelState
from app.models import TravelPlan
from app.models.travel_plan import PLAN_STATUS

logger = get_logger(__name__)


async def _load_plan_dict(plan_id: str) -> dict:
    """从 DB 组装图执行的初始 state。"""
    async with session_scope() as db:
        plan = await db.get(TravelPlan, uuid.UUID(plan_id))
        if plan is None:
            raise RuntimeError(f"行程不存在：{plan_id}")
        return {
            "plan_id": plan_id,
            "query": plan.query,
            "preferences": plan.preferences or {},
            "resume_from": plan.resume_from or "",
            "status": plan.status,
            "completed_nodes": [],
            "over_budget_ratio": 0.0,
            "night_risk": False,
            "sentiment_risk": False,
            "hitl_approved": False,
        }


async def run_plan(plan_id: str, *, hitl_approved: bool = False) -> None:
    """执行（或续跑）一个行程的 Agent 图。

    Args:
        plan_id: 行程 UUID。
        hitl_approved: True 表示这是审批通过后的续跑，跳过 HITL 直接报告。
    """
    initial = await _load_plan_dict(plan_id)
    initial["hitl_approved"] = hitl_approved

    # 若 hitl_approved，恢复 state 里带入之前各节点的风险结论，
    # 以便 report 直接生成（预算/舆情已在前一轮算出）。
    if hitl_approved:
        initial.update(await _load_risk_state(plan_id))

    logger.info("开始执行图 plan=%s hitl_approved=%s", plan_id, hitl_approved)
    config = {"configurable": {"thread_id": plan_id}}
    # 一次性跑完整个图；LangGraph 会在节点间自动推进
    final = await graph.ainvoke(initial, config=config)
    logger.info("图执行结束 plan=%s final_status=%s", plan_id, final.get("status", initial.get("status")))
    return final


async def _load_risk_state(plan_id: str) -> dict:
    """审批通过续跑时，从上一轮结果里读取风险结论，避免重算。"""
    from app.models import AgentTask

    out: dict = {"over_budget_ratio": 0.0, "night_risk": False, "sentiment_risk": False}
    async with session_scope() as db:
        tasks = (
            await db.execute(
                select(AgentTask).where(AgentTask.plan_id == uuid.UUID(plan_id))
            )
        ).scalars().all()
        for t in tasks:
            if t.agent_type == "budget" and t.result:
                out["over_budget_ratio"] = t.result.get("over_budget_ratio", 0.0)
            if t.agent_type == "itinerary" and t.result:
                out["night_risk"] = t.result.get("night_risk", False)
            if t.agent_type == "sentiment" and t.result:
                out["sentiment_risk"] = t.result.get("sentiment_risk", False)
    return out
