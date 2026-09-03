"""Budget Agent：预算计算（说明书 §5.1 第 6 节点）。

分项金额写入 budget_records 与文件预算表；汇总后与用户预算比较，
返回 over_budget_ratio（供条件边判定 HITL）。
酒店住宿用虚拟房价（按目的地城市等级 + 天数），非写死 500/晚。
"""

from __future__ import annotations

import uuid

from app.agents.hotel_pricing import hotel_total
from app.agents.llm import build_system_prompt, get_llm
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask, BudgetRecord, TravelPlan
from app.models.agent_task import TASK_STATUS

logger = get_logger(__name__)


def _party_counts(preferences: dict) -> tuple[int, int, int, list[dict], list[dict]]:
    """取成人/儿童/老人人数 + 老人明细 + 儿童明细。

    优先从 preferences 顶层字段（Intake 归一化后写入的 adults/children/elders），
    否则从 party 结构化字段。保证至少 1 个成人。
    """
    adults = preferences.get("adults")
    children = preferences.get("children", 0)
    elders = preferences.get("elders", 0)
    party = preferences.get("party") or {}
    # 老人明细（年龄+性别）优先从顶层取，其次从 party 取 —— 不依赖 adults 是否为 None，
    # 否则 intake 已把 adults 写到顶层时，party 里的 elders_detail 会被漏掉导致老人误按全免兜底。
    elders_detail = preferences.get("elders_detail") or party.get("elders_detail") or []
    children_detail = preferences.get("children_detail") or party.get("children_detail") or []

    if adults is None:
        adults = party.get("adults", 1)
        children = party.get("children", 0)
        elders = party.get("elders", 0)

    adults = int(adults or 0)
    children = int(children or 0)
    elders = int(elders or 0)
    if adults + children + elders <= 0:
        adults = 1
    return adults, children, elders, elders_detail, children_detail


def _build_budget_items(
    destination: str, days: int, adults: int, children: int, elders: int,
    elders_detail: list[dict] | None = None, children_detail: list[dict] | None = None,
) -> list[dict]:
    """预算项按成人/儿童/老人分档计费（车票/门票折扣与报告一致；餐饮按总人数）。"""
    from app.agents.ticket_pricing import elder_ticket_discount, child_ticket_discount

    people = adults + children + elders
    hotel_nights = max(days - 1, 1)  # 住宿晚数 = 天数 - 1（N 天住 N-1 晚）
    hotel_cost = hotel_total(destination, hotel_nights)
    # 住宿：按人数折算房间数（2人一间，向上取整）
    rooms = max((people + 1) // 2, 1)
    hotel_cost = hotel_cost * rooms

    # 往返交通：成人全价，儿童/老人按配置折扣
    traffic_base = 1000
    traffic = (
        traffic_base * adults
        + int(traffic_base * settings.transport_child_discount) * children
        + int(traffic_base * settings.transport_elder_discount) * elders
    )
    # 门票：成人全价；儿童按年龄/身高分档（6岁以下或1.2米以下免票，6-18半价）；
    # 老人按年龄分档（65+ 免首道大门票 / 60-64 半价 / 60 以下全价）
    ticket_daily = 150 * days
    ticket = ticket_daily * adults
    if children_detail:
        for c in children_detail:
            if not isinstance(c, dict):
                continue
            ticket += int(ticket_daily * child_ticket_discount(c.get("age", 0), c.get("height")))
    else:
        ticket += int(ticket_daily * settings.ticket_child_discount) * children
    if elders_detail:
        for e in elders_detail:
            if not isinstance(e, dict):
                continue
            ticket += int(ticket_daily * elder_ticket_discount(e.get("age", 0)))
    else:
        ticket += int(ticket_daily * settings.ticket_elder_discount) * elders

    party_label = f"{adults}大{children}小{elders}老" if elders else f"{adults}大{children}小"

    return [
        {"category": "traffic", "item": f"往返交通（{party_label}）", "amount": traffic},
        {"category": "hotel", "item": f"住宿 {hotel_nights} 晚（{rooms}间）", "amount": hotel_cost},
        {"category": "ticket", "item": f"景点门票（{party_label}）", "amount": ticket},
        {"category": "food", "item": f"餐饮（{people}人）", "amount": 200 * days * people},
        {"category": "other", "item": "其他", "amount": 300 * people},
    ]


async def budget_node(state: TravelState) -> dict:
    """计算预算并判断超支。"""
    plan_id = state["plan_id"]
    preferences = state.get("preferences", {})
    days = preferences.get("days", 7)
    destination = preferences.get("destination") or "目的地"
    budget_limit = preferences.get("budget_limit") or 15000
    adults, children, elders, elders_detail, children_detail = _party_counts(preferences)

    items = _build_budget_items(destination, days, adults, children, elders, elders_detail, children_detail)
    total = sum(i["amount"] for i in items)
    over_ratio = (total - budget_limit) / budget_limit if budget_limit else 0.0

    # 预算用规则公式计算，无需 LLM（提速）
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
        "total_budget": total,
        "completed_nodes": state.get("completed_nodes", []) + ["budget"],
    }
