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
from datetime import datetime, timezone

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

    # 报告用模板 + 前序数据汇总，无需 LLM（提速）
    degraded = False

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

        # 生成虚拟酒店房价（真实酒店 POI 名 + 虚拟价格）
        hotels_data: list[dict] = []
        days = int((plan.preferences or {}).get("days") or 7)
        try:
            from app.agents.hotel_pricing import generate_hotels

            # 收集高德搜到的真实酒店 POI 名
            hotel_names = await _collect_hotel_names(plan_id, ctx)
            hotels_data = generate_hotels(destination, hotel_names, max(days - 1, 1))
        except Exception as exc:
            logger.warning("酒店房价生成失败：%s", exc)

        # RAG 增强：基于检索到的知识库原文生成「目的地深度解读」（失败降级为空）
        rag_insights: str | None = None
        try:
            prefs = plan.preferences or {}
            party = prefs.get("party") or {}
            kb_hits = (itinerary or {}).get("kb_hits") or []
            _has_elder = int(prefs.get("elders") or party.get("elders") or 0) > 0
            _has_child = int(prefs.get("children") or party.get("children") or 0) > 0
            rag_insights = await _generate_rag_insights(
                destination,
                kb_hits,
                prefs.get("tags") or [],
                _has_elder,
                _has_child,
            )
        except Exception as exc:
            logger.warning("RAG 增强跳过：%s", exc)

        # 生成报告 markdown
        markdown = _build_report_markdown(
            plan, budget_items, itinerary, degraded, weather_now_data, weather_forecast_data, hotels_data, rag_insights
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
        # 记录真实完成时间
        ctx.plan.completed_at = datetime.now(timezone.utc)
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


async def _generate_rag_insights(
    destination: str,
    kb_hits: list[dict],
    tags: list[str],
    has_elder: bool,
    has_child: bool,
) -> str | None:
    """RAG 增强：让 LLM 基于检索到的知识库原文生成「目的地深度解读」。

    这是 RAG 的「生成」环节——检索(Retrieval)到的 chunk 原文作为上下文，
    喂给 LLM 生成面向具体人群的景点/美食/注意事项解读。
    失败或非 real 模式返回 None（降级，不阻塞报告）。
    """
    from app.core.config import settings

    if settings.llm_mode != "real" or not kb_hits:
        return None

    # 把检索到的原文拼成参考材料（限制条数/长度，避免 prompt 过长）
    context_parts = []
    for h in kb_hits[:6]:
        ctx_txt = (h.get("chunk_text") or "").strip()
        if ctx_txt:
            context_parts.append(f"【{h.get('category','')}·{h.get('title','')}】{ctx_txt[:300]}")
    if not context_parts:
        return None
    context = "\n\n".join(context_parts)

    audience = []
    if has_elder:
        audience.append("老人")
    if has_child:
        audience.append("儿童")
    audience_str = "、".join(audience) if audience else "普通游客"

    prompt = (
        f"目的地：{destination}\n"
        f"同行人群：{audience_str}\n"
        f"兴趣偏好：{'、'.join(tags) if tags else '无特别偏好'}\n\n"
        f"以下是从文旅知识库检索到的参考资料：\n{context}\n\n"
        "请基于上述资料，生成一段面向该人群的「目的地深度解读」，包含：\n"
        "1) 目的地亮点（2-3 条）；2) 美食推荐（1-2 条）；3) 针对老人/儿童的注意事项（如有）。\n"
        "要求：口语化、简洁、直接基于资料（不要编造资料里没有的景点或价格）；输出纯 Markdown，不要标题。"
    )

    try:
        llm = get_llm()
        result = await llm.complete(
            [
                {"role": "system", "content": build_system_prompt("report_rag", "你是文旅行程规划系统的目的地解读助手。")},
                {"role": "user", "content": prompt},
            ],
        )
        text = (result.text or "").strip()
        return text or None
    except Exception as exc:
        logger.warning("RAG 目的地解读生成失败：%s", exc)
        return None


async def _collect_hotel_names(plan_id: str, ctx: NodeContext) -> list[str]:
    """从 web_research 任务结果里收集真实酒店 POI 名（keyword=酒店）。"""
    from app.models import AgentTask as AT

    result = await ctx.db.execute(
        select(AT).where(AT.plan_id == uuid.UUID(plan_id), AT.agent_type == "web_research")
    )
    names: list[str] = []
    for t in result.scalars().all():
        if not t.result:
            continue
        if t.result.get("keyword") == "酒店" or "酒店" in str(t.result.get("keyword", "")):
            for p in t.result.get("pois", []):
                if p.get("name"):
                    names.append(p["name"])
    return names[:3]  # 取前 3 个真实酒店名


def _route_str(route: dict | None) -> str:
    """格式化路线数据（距离/耗时）。"""
    if not route:
        return "—"
    dist_km = route.get("distance", 0) / 1000
    dur_min = route.get("duration", 0) // 60
    return f"{dist_km:.1f}km / {dur_min}分钟"


def _short_time(opentime: str) -> str:
    """营业时间截短显示（高德 opentime 可能很长，报告里只取关键部分）。"""
    if not opentime:
        return "—"
    # 取前 40 字符，超长省略
    return opentime[:40] + ("..." if len(opentime) > 40 else "")


_CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _sec(n: int) -> str:
    """把数字章节号转中文（1→一，2→二，...）。"""
    if 1 <= n <= len(_CN_NUM):
        return _CN_NUM[n - 1]
    return str(n)


def _build_report_markdown(
    plan: TravelPlan,
    budget_items: list[BudgetRecord],
    itinerary: dict | None,
    degraded: bool,
    weather_now: dict | None = None,
    weather_forecast: list[dict] | None = None,
    hotels: list[dict] | None = None,
    rag_insights: str | None = None,
) -> str:
    """生成完整报告正文。"""
    prefs = plan.preferences or {}
    destination = prefs.get("destination") or "目的地"
    days = prefs.get("days") or "-"
    party = prefs.get("party") or {}
    tags = prefs.get("tags") or []

    # 出行总人数（成人+儿童+老人），用于票价/门票/餐饮按人数计
    _adults = int(prefs.get("adults") or party.get("adults") or 1)
    _children = int(prefs.get("children") or party.get("children") or 0)
    _elders = int(prefs.get("elders") or party.get("elders") or 0)
    people = max(_adults + _children + _elders, 1)

    def _tiered_price_str(tk: dict | None) -> str:
        """票价分档：成人/儿童/老人各 × 人数，合计总价（交通/门票复用）。"""
        if not tk:
            return ""
        parts = []
        if _adults and (tk.get("adult_total") or tk.get("adult_price")):
            parts.append(f"成人 ¥{tk.get('adult_price', 0)}×{_adults}={tk.get('adult_total', 0)}")
        if _children and tk.get("child_total"):
            child_breakdown = tk.get("child_breakdown")
            if child_breakdown:
                # 按年龄/身高逐人展示（6岁以下或1.2米以下免票/6-18半价）
                labels = []
                for b in child_breakdown:
                    h = f"/{b.get('height')}m" if b.get("height") else ""
                    labels.append(f"{b.get('age')}岁{h} ¥{b.get('price', 0)}")
                parts.append("儿童 " + "、".join(labels) + f"={tk.get('child_total', 0)}")
            else:
                parts.append(f"儿童 ¥{tk.get('child_price', 0)}×{_children}={tk.get('child_total', 0)}")
        if _elders:
            breakdown = tk.get("elder_breakdown")
            if breakdown:
                # 按年龄逐人展示（65+免首道大门票/60-64半价/60以下全价）
                labels = []
                for b in breakdown:
                    labels.append(f"{b.get('age')}岁{b.get('gender','')} ¥{b.get('price', 0)}")
                parts.append("老人 " + "、".join(labels) + f"={tk.get('elder_total', 0)}")
            else:
                parts.append(f"老人 ¥{tk.get('elder_price', 0)}×{_elders}={tk.get('elder_total', 0)}")
        if parts:
            return "；".join(parts) + f"（合计¥{tk.get('total', 0)}）"
        return f"¥{tk.get('total', 0)}"

    def _transport_price_str(tk: dict | None) -> str:
        """交通票价分档：成人/老人 + 儿童按年龄/票种逐人展示 + 购票备注。"""
        if not tk:
            return ""
        parts = []
        if _adults and tk.get("adult_total"):
            parts.append(f"成人 ¥{tk.get('adult_price', 0)}×{_adults}={tk.get('adult_total', 0)}")
        if _elders and tk.get("elder_total"):
            parts.append(f"老人 ¥{tk.get('elder_price', 0)}×{_elders}={tk.get('elder_total', 0)}")
        child_bd = tk.get("child_breakdown")
        if child_bd:
            labels = []
            for b in child_bd:
                labels.append(f"{b.get('age')}岁 {b.get('tag','')} ¥{b.get('price', 0)}")
            parts.append("儿童 " + "、".join(labels))
        if parts:
            return "；".join(parts) + f"（合计¥{tk.get('total', 0)}）"
        return f"¥{tk.get('total', 0)}"

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
    origin = prefs.get("origin")
    if origin:
        lines.append(f"| 出发地 | **{origin}** |")
    lines.append(f"| 目的地 | **{destination}** |")
    lines.append(f"| 行程天数 | {days} 天 |")
    if party:
        p = party
        parts = [f"{p.get('adults','-')} 大 {p.get('children',0)} 小"]
        if p.get('elders'):
            parts.append(f"{p['elders']} 老")
        lines.append(f"| 出行人数 | {' '.join(parts)} |")
        if p.get('elder_status'):
            lines.append(f"| 老人状态 | {p['elder_status']} |")
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

    # 章节号递增计数器（一=概览 已写，从「二」开始）
    sec = 2

    # 天气章节（已在上方输出，若存在）
    if weather_now or weather_forecast:
        sec += 1

    # 交通规划（出发地↔目的地，咋去咋回）
    if itinerary and itinerary.get("transport") and origin:
        t = itinerary["transport"]
        lines.append(f"## {_sec(sec)}、往返交通规划")
        lines.append("")
        lines.append(f"- 出发地：**{origin}** ⇄ 目的地：**{destination}**")
        lines.append("")
        lines.append("**🚌 去程**")
        lines.append("")
        lines.append("| 项目 | 内容 |")
        lines.append("| --- | --- |")
        if t.get("method"):
            lines.append(f"| 交通方式 | {t['method']} |")
        if t.get("price"):
            tiered = _transport_price_str(t.get("ticket"))
            lines.append(f"| 票价 | {tiered} |" if tiered else f"| 票价 | ¥{t['price']}/人 |")
        if t.get("ticket") and t["ticket"].get("note"):
            lines.append(f"| 购票提示 | {t['ticket']['note']} |")
        if t.get("duration"):
            lines.append(f"| 耗时 | {t['duration']} |")
        if t.get("depart_time"):
            lines.append(f"| 建议出发时间 | {t['depart_time']} |")
        if t.get("on_the_way"):
            lines.append(f"| 途中建议 | {t['on_the_way']} |")
        lines.append("")
        if t.get("return_method") or t.get("return_price"):
            lines.append("**🏠 返程**")
            lines.append("")
            lines.append("| 项目 | 内容 |")
            lines.append("| --- | --- |")
            if t.get("return_method"):
                lines.append(f"| 交通方式 | {t['return_method']} |")
            if t.get("return_price"):
                tiered = _transport_price_str(t.get("return_ticket"))
                lines.append(f"| 票价 | {tiered} |" if tiered else f"| 票价 | ¥{t['return_price']}/人 |")
            if t.get("return_ticket") and t["return_ticket"].get("note"):
                lines.append(f"| 购票提示 | {t['return_ticket']['note']} |")
            if t.get("return_duration"):
                lines.append(f"| 耗时 | {t['return_duration']} |")
            lines.append("")
        if t.get("note"):
            lines.append(f"> 💡 {t['note']}")
            lines.append("")
        sec += 1

    # 推荐路线
    if itinerary and itinerary.get("route"):
        lines.append(f"## {_sec(sec)}、推荐路线")
        lines.append("")
        lines.append(f"```")
        lines.append(f"{itinerary['route']}")
        lines.append(f"```")
        lines.append("")
        sec += 1

    # 每日行程单
    if itinerary and itinerary.get("daily_plan"):
        lines.append(f"## {_sec(sec)}、每日行程计划（高德真实数据）")
        lines.append("")
        def _spot_price(spot) -> str:
            """门票：分成人/儿童/老人票。"""
            t = spot.get("ticket")
            if t:
                return _tiered_price_str(t)
            p = spot.get("price")
            if not p:
                return ""
            return f"¥{p}/人 × {people}人 = ¥{p * people}"

        for day in itinerary["daily_plan"]:
            lines.append(f"### 第 {day['day']} 天")
            lines.append("")
            lines.append("| 时段 | 景点 | 地址 | 门票 | 营业时间 | 到下一点路线 |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            m = day["morning"]
            a = day["afternoon"]
            e = day["evening"]
            lines.append(f"| 🌅 上午 | **{m.get('spot','-')}** | {m.get('address','')} | {_spot_price(m)} | {_short_time(m.get('opentime',''))} | {_route_str(m.get('route'))} |")
            lines.append(f"| ☀️ 下午 | **{a.get('spot','-')}** | {a.get('address','')} | {_spot_price(a)} | {_short_time(a.get('opentime',''))} | {_route_str(a.get('route'))} |")
            lines.append(f"| 🌙 晚上 | **{e.get('spot','-')}** | {e.get('address','')} | {_spot_price(e)} | {_short_time(e.get('opentime',''))} | — |")
            # 优待备注：有儿童/老人时标注该人群的免/半价政策
            for spot in (m, a, e):
                note = spot.get("note")
                if note:
                    lines.append(f"> 🎫 {spot.get('spot','')}：{note}")
            lines.append("")

            # 餐饮安排
            meals = day.get("meals")
            if meals and any(meals.values()):
                lines.append("**🍽️ 餐饮安排：**")
                lines.append("")
                lines.append("| 餐次 | 餐厅 | 地址 | 人均×人数 | 营业时间 |")
                lines.append("| --- | --- | --- | --- | --- |")
                if meals.get("breakfast"):
                    mp = meals['breakfast'].get('price')
                    mp_str = f"¥{mp} × {people}人 = ¥{mp * people}" if mp else "—"
                    lines.append(f"| 早餐 | {meals['breakfast'].get('name','-')} | {meals['breakfast'].get('address','')} | {mp_str} | {_short_time(meals['breakfast'].get('opentime',''))} |")
                if meals.get("lunch"):
                    mp = meals['lunch'].get('price')
                    mp_str = f"¥{mp} × {people}人 = ¥{mp * people}" if mp else "—"
                    lines.append(f"| 午餐 | {meals['lunch'].get('name','-')} | {meals['lunch'].get('address','')} | {mp_str} | {_short_time(meals['lunch'].get('opentime',''))} |")
                if meals.get("dinner"):
                    mp = meals['dinner'].get('price')
                    mp_str = f"¥{mp} × {people}人 = ¥{mp * people}" if mp else "—"
                    lines.append(f"| 晚餐 | {meals['dinner'].get('name','-')} | {meals['dinner'].get('address','')} | {mp_str} | {_short_time(meals['dinner'].get('opentime',''))} |")
                lines.append("")
        sec += 1
    else:
        lines.append(f"## {_sec(sec)}、每日行程计划")
        lines.append("")
        lines.append("（行程计划生成中，请稍后刷新）")
        lines.append("")
        sec += 1

    # 酒店推荐（虚拟房价）
    if hotels:
        lines.append(f"## {_sec(sec)}、酒店推荐（估算价格）")
        lines.append("")
        lines.append("| 酒店 | 档位 | 房型 | 单价/晚 | 评分 | 合计 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for h in hotels:
            lines.append(
                f"| {h['name']} | {h['tier_label']} | {h['room_type']} | "
                f"¥{h['price_per_night']} | {h['rating']} | ¥{h['total_price']} |"
            )
        lines.append("")
        lines.append("> 注：酒店名来自高德真实 POI，房价为估算值（参考城市等级生成）。")
        lines.append("")
        sec += 1

    # 预算明细
    lines.append(f"## {_sec(sec)}、预算明细")
    lines.append("")
    lines.append("| 类别 | 项目 | 金额 |")
    lines.append("| --- | --- | --- |")
    for b in budget_items:
        lines.append(f"| {b.category} | {b.item} | ¥{float(b.amount):,.0f} |")
    total = sum(float(b.amount) for b in budget_items)
    lines.append(f"| **合计** | | **¥{total:,.0f}** |")
    lines.append("")
    sec += 1

    # 数据来源与提示
    lines.append(f"## {_sec(sec)}、数据来源与温馨提示")
    lines.append("")
    lines.append("- 本报告由 8 个 AI Agent 协作生成：偏好解析 → 任务拆解 → 网页调研 → 舆情评估 → 日程编排 → 预算计算。")
    lines.append("- 景点/路线/天气数据均来自高德地图 API（真实数据）。")
    lines.append("- 酒店房价为估算值（真实房价 API 未接入）。")
    lines.append("- 出行前请再次确认景点开放时间、天气与交通状况。")
    lines.append("")
    sec += 1

    # RAG 增强：目的地深度解读（LLM 基于知识库生成）
    if rag_insights:
        lines.append(f"## {_sec(sec)}、目的地深度解读（AI 生成）")
        lines.append("")
        lines.append(rag_insights)
        lines.append("")
        lines.append("> 本解读由 AI 基于文旅知识库检索生成，仅供参考。")
        lines.append("")
        sec += 1

    lines.append(f"---")
    lines.append(f"*生成时间：由系统自动生成*")

    return "\n".join(lines)
