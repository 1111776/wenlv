"""Budget Agent：预算计算（说明书 §5.1 第 6 节点）。

分项金额写入 budget_records 与文件预算表；汇总后与用户预算比较，
返回 over_budget_ratio（供条件边判定 HITL）。
"""

from __future__ import annotations

import uuid

from app.agents.llm import build_system_prompt, get_llm
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask, BudgetRecord, TravelPlan
from app.models.agent_task import TASK_STATUS

logger = get_logger(__name__)


def _build_budget_items(days: int) -> list[dict]:
    """确定性预算项（Mock）。"""
    return [
        {"category": "traffic", "item": "往返交通", "amount": 2000},
        {"category": "hotel", "item": f"住宿 {days} 晚", "amount": 500 * days},
        {"category": "ticket", "item": "景点门票", "amount": 150 * days},
        {"category": "food", "item": "餐饮", "amount": 200 * days},
        {"category": "other", "item": "其他", "amount": 300},
    ]


async def budget_node(state: TravelState) -> dict:
    """计算预算并判断超支。"""
    plan_id = state["plan_id"]
    preferences = state.get("preferences", {})
    days = preferences.get("days", 7)
    budget_limit = preferences.get("budget_limit") or 15000

    items = _build_budget_items(days)
    total = sum(i["amount"] for i in items)
    over_ratio = (total - budget_limit) / budget_limit if budget_limit else 0.0

    try:
        llm = get_llm()
        await llm.complete([{"role": "system", "content": build_system_prompt("budget", "预算计算")}])
    except Exception as exc:
        logger.warning("Budget LLM 失败，模板降级：%s", exc)

    async with session_scope() as db:
        from sqlalchemy import delete

        plan = await db.get(TravelPlan, uuid.UUID(plan_id))
        if plan is not None:
            plan.total_budget = total
            await db.flush()
        # 幂等：先删旧的 budget 记录与预算明细再插入
        await db.execute(
            delete(BudgetRecord).where(BudgetRecord.plan_id == uuid.UUID(plan_id))
        )
        await db.execute(
            delete(AgentTask).where(
                AgentTask.plan_id == uuid.UUID(plan_id),
                AgentTask.agent_type == "budget",
            )
        )
        for item in items:
            db.add(
                BudgetRecord(
                    plan_id=uuid.UUID(plan_id),
                    category=item["category"],
                    item=item["item"],
                    amount=item["amount"],
                )
            )
        db.add(
            AgentTask(
                plan_id=uuid.UUID(plan_id),
                agent_type="budget",
                order_index=102,
                status=TASK_STATUS["COMPLETED"],
                task_data={"title": "预算计算"},
                result={"total": total, "over_budget_ratio": over_ratio},
            )
        )
        await db.flush()

    return {
        "over_budget_ratio": over_ratio,
        "completed_nodes": state.get("completed_nodes", []) + ["budget"],
    }
