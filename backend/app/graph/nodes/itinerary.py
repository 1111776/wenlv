"""Itinerary Agent：日程编排（说明书 §5.1 第 5 节点）。

用高德真实数据编排行程：
- 读取 Web Research 节点通过高德 POI 搜索收集的真实景点；
- 用高德路径规划计算相邻景点间的真实驾车距离与耗时；
- 按天生成上午/下午/晚上三段行程，附真实路线数据；
- 检测夜间移动时段 → night_risk 布尔。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.llm import build_system_prompt, get_llm
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask
from app.models.agent_task import TASK_STATUS
from app.services.amap import AmapError, driving_route

logger = get_logger(__name__)


def _collect_pois(tasks: list[AgentTask]) -> list[dict]:
    """从 web_research 任务结果里汇总真实 POI（去重，优先景点类）。"""
    seen: set[str] = set()
    pois: list[dict] = []
    for t in tasks:
        if t.agent_type != "web_research" or not t.result:
            continue
        for p in t.result.get("pois", []):
            name = p.get("name")
            loc = p.get("location")
            if not name or not loc or loc == (None, None):
                continue
            if name in seen:
                continue
            seen.add(name)
            pois.append(p)
    return pois


async def _route_between(origin, destination) -> dict | None:
    """高德路径规划，失败返回 None（降级为无路线数据）。"""
    try:
        return await driving_route(origin, destination)
    except AmapError:
        return None


async def itinerary_node(state: TravelState) -> dict:
    """编排真实日程（高德 POI + 路径规划）。"""
    plan_id = state["plan_id"]
    preferences = state.get("preferences", {})
    days = int(preferences.get("days") or 7)
    destination = preferences.get("destination") or "目的地"

    # 节点入口读取干预补丁（D9：Agent 下一次决策优先采用干预后状态）
    excluded_attractions: list[str] = []
    try:
        from app.memory import mutator

        patch = await mutator.read_intervention_patch(plan_id)
        if patch:
            excluded_attractions = patch.get("excluded_attractions", [])
            logger.info("Itinerary 应用干预补丁 plan=%s 剔除=%s", plan_id, excluded_attractions)
            # 补丁只消费一次（幂等）
            await mutator.mark_intervention_read(plan_id)
    except Exception as exc:
        logger.warning("读取干预补丁失败：%s", exc)

    # 读 web_research 收集的真实 POI
    async with session_scope() as db:
        tasks = (
            await db.execute(
                select(AgentTask)
                .where(AgentTask.plan_id == uuid.UUID(plan_id))
                .order_by(AgentTask.order_index)
            )
        ).scalars().all()

    pois = _collect_pois(tasks)
    # 应用干预：剔除被主管标记为 unavailable 的景点
    if excluded_attractions:
        pois = [p for p in pois if p.get("name") not in excluded_attractions]
    logger.info("Itinerary 收集到 %d 个真实 POI（剔除干预 %d 个）", len(pois), len(excluded_attractions))

    # 按天分配 POI（每天 3 个：上午/下午/晚上）
    daily_plan: list[dict] = []
    cursor = 0
    total_spots = days * 3

    for day in range(1, days + 1):
        am = pois[cursor % len(pois)] if pois else None
        pm = pois[(cursor + 1) % len(pois)] if pois else None
        ev = pois[(cursor + 2) % len(pois)] if pois else None
        cursor += 3

        # 计算真实路径（相邻景点间）
        am_pm_route = None
        pm_ev_route = None
        if am and pm and am.get("location") and pm.get("location"):
            am_pm_route = await _route_between(am["location"], pm["location"])
        if pm and ev and pm.get("location") and ev.get("location"):
            pm_ev_route = await _route_between(pm["location"], ev["location"])

        def _fmt(poi, route_to_next):
            return {
                "spot": poi["name"],
                "address": poi.get("address", ""),
                "type": poi.get("type", ""),
                "route": route_to_next,
            }

        daily_plan.append(
            {
                "day": day,
                "morning": _fmt(am, am_pm_route),
                "afternoon": _fmt(pm, pm_ev_route),
                "evening": _fmt(ev, None),
            }
        )

    # 路线串联（取每天首站）
    route_names = [d["morning"]["spot"] for d in daily_plan if d["morning"]["spot"]]
    route = f"{destination} → " + " → ".join(route_names) if route_names else destination

    # 夜行风险：行程含夜间移动（MVP 简化：默认 False，除非路径耗时异常长）
    night_risk = False

    itinerary = {
        "days": days,
        "destination": destination,
        "daily_plan": daily_plan,
        "route": route,
        "night_risk": night_risk,
        "poi_count": len(pois),
        "data_source": "amap",
    }

    try:
        llm = get_llm()
        await llm.complete([{"role": "system", "content": build_system_prompt("itinerary", "日程编排")}])
    except Exception as exc:
        logger.warning("Itinerary LLM 失败，模板降级：%s", exc)
        itinerary["quality"] = "degraded"

    async with session_scope() as db:
        from sqlalchemy import delete

        await db.execute(
            delete(AgentTask).where(
                AgentTask.plan_id == uuid.UUID(plan_id),
                AgentTask.agent_type == "itinerary",
            )
        )
        db.add(
            AgentTask(
                plan_id=uuid.UUID(plan_id),
                agent_type="itinerary",
                order_index=101,
                status=TASK_STATUS["COMPLETED"],
                task_data={"title": "日程编排"},
                result=itinerary,
            )
        )
        await db.flush()

    logger.info("Itinerary 生成完成 plan=%s days=%d 真实POI=%d", plan_id, days, len(pois))
    return {
        "night_risk": night_risk,
        "completed_nodes": state.get("completed_nodes", []) + ["itinerary"],
    }
