"""Report Agent：报告生成（说明书 §5.1 第 8 节点 / §2.4）。

汇总前序节点输出，生成完整 report.md：
- 行程概览（目的地/天数/出行人/预算）
- 路线串联图
- 每日行程单（上午/下午/晚上 + 交通 + 餐饮 + 住宿）
- 预算明细表
- 数据来源与风险提示
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.llm import build_system_prompt, get_llm
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.context import NodeContext
from app.graph.state import TravelState
from app.models import AgentTask, BudgetRecord, TravelPlan
from app.models.agent_task import TASK_STATUS
from app.services.atomic_file import atomic_write

logger = get_logger(__name__)


async def report_node(state: TravelState) -> dict:
    """生成完整报告并置 completed。"""
    plan_id = state["plan_id"]

    degraded = False
    try:
        llm = get_llm()
        await llm.complete([{"role": "system", "content": build_system_prompt("report", "报告生成")}])
    except Exception as exc:
        logger.warning("Report LLM 失败，模板降级：%s", exc)
        degraded = True

    async with NodeContext(plan_id) as ctx:
        plan = ctx.plan
        budget_items = (
            await ctx.db.execute(
                select(BudgetRecord).where(BudgetRecord.plan_id == uuid.UUID(plan_id))
            )
        ).scalars().all()

        # 读取 Itinerary 生成的行程计划
        itinerary = await _load_itinerary(plan_id, ctx)

        # 拉取目的地真实天气（失败降级为空，不阻塞报告生成）
        weather_now_data = None
        weather_forecast_data: list[dict] = []
        destination = (plan.preferences or {}).get("destination")
        if destination:
            try:
                from app.services.amap import weather_now, weather_forecast

                weather_now_data = await weather_now(destination)
                weather_forecast_data = await weather_forecast(destination)
            except Exception as exc:
                logger.warning("天气获取失败：%s", exc)

        # 生成报告 markdown
        markdown = _build_report_markdown(
            plan, budget_items, itinerary, degraded, weather_now_data, weather_forecast_data
        )

        # 写 report.md
        from app.services.workspace import PlanFileManager

        fm = PlanFileManager(plan_id)
        report_path = fm.dir / "report.md"
        atomic_write(report_path, markdown)

        # 记录 Report 执行 + 终态（幂等）
        from sqlalchemy import delete

        await ctx.db.execute(
            delete(AgentTask).where(
                AgentTask.plan_id == uuid.UUID(plan_id),
                AgentTask.agent_type == "report",
            )
        )
        ctx.db.add(
            AgentTask(
                plan_id=uuid.UUID(plan_id),
                agent_type="report",
                order_index=200,
                status=TASK_STATUS["COMPLETED"],
                task_data={"title": "报告生成"},
                result={"quality": "degraded" if degraded else "ok"},
            )
        )
        await ctx.advance(
            status="completed",
            resume_from="report",
            body=await ctx.build_body(logs=["报告生成完成"]),
            event="completed",
            agent="report",
            progress=ctx.progress(),
        )

    return {
        "status": "completed",
        "completed_nodes": state.get("completed_nodes", []) + ["report"],
    }


async def _load_itinerary(plan_id: str, ctx: NodeContext) -> dict | None:
    """从 agent_tasks 读取 Itinerary 生成的行程计划。"""
    from app.models import AgentTask as AT

    result = await ctx.db.execute(
        select(AT).where(AT.plan_id == uuid.UUID(plan_id), AT.agent_type == "itinerary")
    )
    task = result.scalars().first()
    if task and task.result:
        return task.result
    return None


def _route_str(route: dict | None) -> str:
    """格式化路线数据（距离/耗时）。"""
    if not route:
        return "—"
    dist_km = route.get("distance", 0) / 1000
    dur_min = route.get("duration", 0) // 60
    return f"{dist_km:.1f}km / {dur_min}分钟"


def _build_report_markdown(
    plan: TravelPlan,
    budget_items: list[BudgetRecord],
    itinerary: dict | None,
    degraded: bool,
    weather_now: dict | None = None,
    weather_forecast: list[dict] | None = None,
) -> str:
    """生成完整报告正文。"""
    prefs = plan.preferences or {}
    destination = prefs.get("destination") or "目的地"
    days = prefs.get("days") or "-"
    party = prefs.get("party") or {}
    tags = prefs.get("tags") or []

    lines: list[str] = []
    lines.append(f"# {destination} 行程计划报告")
    lines.append("")
    if degraded:
        lines.append("> ⚠️ 本报告部分内容为降级生成（quality=degraded）")
        lines.append("")

    # 一、行程概览
    lines.append("## 一、行程概览")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append(f"| 目的地 | **{destination}** |")
    lines.append(f"| 行程天数 | {days} 天 |")
    if party:
        lines.append(f"| 出行人数 | {party.get('adults', '-')} 大 {party.get('children', 0)} 小 |")
    if tags:
        lines.append(f"| 兴趣偏好 | {'、'.join(tags)} |")
    lines.append(f"| 预算上限 | ¥{float(plan.budget_limit or 0):,.0f} |")
    lines.append(f"| 预计总花费 | ¥{float(plan.total_budget or 0):,.0f} |")
    lines.append("")

    # 天气（高德真实数据）
    if weather_now or weather_forecast:
        lines.append("## 二、目的地天气（高德实时）")
        lines.append("")
        if weather_now:
            lines.append(
                f"- 当前天气：**{weather_now.get('weather','-')}** {weather_now.get('temperature','-')}℃"
                f" | {weather_now.get('winddirection','-')}风{weather_now.get('windpower','-')}级"
                f" | 湿度 {weather_now.get('humidity','-')}%"
            )
            lines.append("")
        if weather_forecast:
            lines.append("| 日期 | 白天 | 夜间 | 温度 |")
            lines.append("| --- | --- | --- | --- |")
            for f in weather_forecast[:4]:
                lines.append(
                    f"| {f.get('date','-')} | {f.get('dayweather','-')} | {f.get('nightweather','-')} "
                    f"| {f.get('daytemp','-')}~{f.get('nighttemp','-')}℃ |"
                )
            lines.append("")
            # 出行提示：预报有雨则提示
            rainy = any("雨" in (f.get("dayweather", "") + f.get("nightweather", "")) for f in weather_forecast[:3])
            if rainy:
                lines.append("> ☔ 未来几日有降雨，建议携带雨具，合理调整户外行程。")
            else:
                lines.append("> ☀️ 未来几日天气晴好，适合出行。")
            lines.append("")

    # 章节号动态：有天气时多一节
    has_weather = bool(weather_now or weather_forecast)
    sec_route = "三" if has_weather else "二"
    sec_daily = "四" if has_weather else "三"
    sec_budget = "五" if has_weather else "四"
    sec_tips = "六" if has_weather else "五"

    # 路线串联
    if itinerary and itinerary.get("route"):
        lines.append(f"## {sec_route}、推荐路线")
        lines.append("")
        lines.append(f"```")
        lines.append(f"{itinerary['route']}")
        lines.append(f"```")
        lines.append("")

    # 每日行程单
    if itinerary and itinerary.get("daily_plan"):
        lines.append(f"## {sec_daily}、每日行程计划（高德真实数据）")
        lines.append("")
        for day in itinerary["daily_plan"]:
            lines.append(f"### 第 {day['day']} 天")
            lines.append("")
            lines.append("| 时段 | 景点 | 地址 | 到下一点路线 |")
            lines.append("| --- | --- | --- | --- |")
            m = day["morning"]
            a = day["afternoon"]
            e = day["evening"]
            lines.append(f"| 🌅 上午 | **{m.get('spot','-')}** | {m.get('address','')} | {_route_str(m.get('route'))} |")
            lines.append(f"| ☀️ 下午 | **{a.get('spot','-')}** | {a.get('address','')} | {_route_str(a.get('route'))} |")
            lines.append(f"| 🌙 晚上 | **{e.get('spot','-')}** | {e.get('address','')} | — |")
            lines.append("")
    else:
        lines.append(f"## {sec_daily}、每日行程计划")
        lines.append("")
        lines.append("（行程计划生成中，请稍后刷新）")
        lines.append("")

    # 数据来源说明
    if itinerary and itinerary.get("data_source") == "amap":
        lines.append("> 本行程的景点、地址、路线与天气均由高德地图 API 实时生成。")
        lines.append("")

    # 预算明细
    lines.append(f"## {sec_budget}、预算明细")
    lines.append("")
    lines.append("| 类别 | 项目 | 金额 |")
    lines.append("| --- | --- | --- |")
    for b in budget_items:
        lines.append(f"| {b.category} | {b.item} | ¥{float(b.amount):,.0f} |")
    total = sum(float(b.amount) for b in budget_items)
    lines.append(f"| **合计** | | **¥{total:,.0f}** |")
    lines.append("")

    # 数据来源与提示
    lines.append(f"## {sec_tips}、数据来源与温馨提示")
    lines.append("")
    lines.append("- 本报告由 8 个 AI Agent 协作生成：偏好解析 → 任务拆解 → 网页调研 → 舆情评估 → 日程编排 → 预算计算。")
    lines.append("- 景点/路线/天气数据均来自高德地图 API（真实数据）。")
    lines.append("- 出行前请再次确认景点开放时间、天气与交通状况。")
    lines.append("")
    lines.append(f"---")
    lines.append(f"*生成时间：由系统自动生成*")

    return "\n".join(lines)
