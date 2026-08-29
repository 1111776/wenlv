"""Itinerary Agent：日程编排（说明书 §5.1 第 5 节点）。

用高德真实数据编排行程：
- 读取 Web Research 节点通过高德 POI 搜索收集的真实景点；
- 用高德路径规划计算相邻景点间的真实驾车距离与耗时（并发，加速）；
- 按天生成上午/下午/晚上三段行程，附真实路线数据；
- night_risk 由 hitl_demo 开关控制（演示 HITL 用，真实数据下默认不触发）。
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.agents.llm import build_system_prompt, get_llm
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask
from app.models.agent_task import TASK_STATUS
from app.services.amap import AmapError, driving_route

logger = get_logger(__name__)


def _collect_pois(tasks: list[AgentTask]) -> tuple[list[dict], list[dict]]:
    """从 web_research 任务结果里汇总真实 POI，按类别分成「景点」和「餐厅」。

    返回 (attractions, restaurants)：
    - attractions：风景/公园/博物馆/购物等游玩类
    - restaurants：餐饮美食类（keyword=餐厅 的任务结果）
    """
    seen: set[str] = set()
    attractions: list[dict] = []
    restaurants: list[dict] = []

    for t in tasks:
        if t.agent_type != "web_research" or not t.result:
            continue
        keyword = t.result.get("keyword", "")
        is_food = keyword == "餐厅" or "餐厅" in keyword or "美食" in keyword

        for p in t.result.get("pois", []):
            name = p.get("name")
            loc = p.get("location")
            if not name or not loc or loc == (None, None):
                continue
            if name in seen:
                continue
            seen.add(name)
            # 附带 keyword 信息，便于分类
            p = {**p, "_keyword": keyword}
            if is_food:
                restaurants.append(p)
            else:
                attractions.append(p)

    return attractions, restaurants


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

    attractions, restaurants = _collect_pois(tasks)
    # 应用干预：剔除被主管标记为 unavailable 的景点
    if excluded_attractions:
        attractions = [p for p in attractions if p.get("name") not in excluded_attractions]
    logger.info(
        "Itinerary 收集到 %d 个景点、%d 个餐厅（剔除干预 %d 个）",
        len(attractions), len(restaurants), len(excluded_attractions),
    )

    # 按天分配景点（每天 3 个：上午/下午/晚上）
    daily_plan: list[dict] = []
    cursor = 0

    # 先收集所有需要路径规划的点对，一次性并发计算（加速）
    route_pairs: list[tuple[int, int, tuple, tuple]] = []
    spots_per_day: list[tuple] = []
    for day in range(1, days + 1):
        am = attractions[cursor % len(attractions)] if attractions else None
        pm = attractions[(cursor + 1) % len(attractions)] if attractions else None
        ev = attractions[(cursor + 2) % len(attractions)] if attractions else None
        cursor += 3
        spots_per_day.append((am, pm, ev))
        if am and pm and am.get("location") and pm.get("location"):
            route_pairs.append((day - 1, "am_pm", am["location"], pm["location"]))
        if pm and ev and pm.get("location") and ev.get("location"):
            route_pairs.append((day - 1, "pm_ev", pm["location"], ev["location"]))

    # 并发计算所有路径（asyncio.gather）
    route_results = await asyncio.gather(
        *[_route_between(o, d) for _, _, o, d in route_pairs],
        return_exceptions=True,
    )
    route_map: dict[tuple[int, str], dict | None] = {}
    for (day_idx, seg, o, d), res in zip(route_pairs, route_results):
        route_map[(day_idx, seg)] = res if not isinstance(res, Exception) else None

    # 组装 daily_plan（景点 + 三餐餐饮）
    def _fmt_spot(poi, route_to_next):
        return {
            "spot": poi["name"],
            "address": poi.get("address", ""),
            "type": poi.get("type", ""),
            "route": route_to_next,
        }

    def _fmt_meal(poi):
        return {"name": poi["name"], "address": poi.get("address", ""), "type": poi.get("type", "")}

    for day_idx, (am, pm, ev) in enumerate(spots_per_day):
        am_pm_route = route_map.get((day_idx, "am_pm"))
        pm_ev_route = route_map.get((day_idx, "pm_ev"))

        # 三餐：按天从餐厅列表轮转取（早餐/午餐/晚餐各一家）
        def _meal_at(i: int):
            return restaurants[i % len(restaurants)] if restaurants else None

        breakfast = _meal_at(day_idx * 3)
        lunch = _meal_at(day_idx * 3 + 1)
        dinner = _meal_at(day_idx * 3 + 2)

        daily_plan.append(
            {
                "day": day_idx + 1,
                "morning": _fmt_spot(am, am_pm_route),
                "afternoon": _fmt_spot(pm, pm_ev_route),
                "evening": _fmt_spot(ev, None),
                "meals": {
                    "breakfast": _fmt_meal(breakfast) if breakfast else None,
                    "lunch": _fmt_meal(lunch) if lunch else None,
                    "dinner": _fmt_meal(dinner) if dinner else None,
                },
            }
        )

    # 路线串联（取每天首站）
    route_names = [d["morning"]["spot"] for d in daily_plan if d["morning"]["spot"]]
    route = f"{destination} → " + " → ".join(route_names) if route_names else destination

    # 夜行风险：hitl_demo=true 时演示触发 HITL（真实数据下默认 False）
    night_risk = settings.hitl_demo

    itinerary = {
        "days": days,
        "destination": destination,
        "daily_plan": daily_plan,
        "route": route,
        "night_risk": night_risk,
        "poi_count": len(attractions),
        "restaurant_count": len(restaurants),
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
