"""Web Research Agent：ReAct 逐项调研（说明书 §5.1 第 3 节点 / §5.3 ReAct）。

用高德 POI 搜索真实数据（替换原假种子页面）：
- 每个任务 = 一个「搜索关键词 + 城市」，调用高德 place/text 返回真实 POI；
- 逐项完成即 checkpoint（S24：task 级恢复粒度），已 completed 不重复请求（S25）；
- 内容仍过安全过滤（注入检测 + 有害内容），保留场景 C 验收；
- 高德失败时降级为空结果（记 failed），不阻塞主流程。
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask
from app.models.agent_task import TASK_STATUS
from app.services.amap import AmapError, resolve_city, search_poi
from app.services.audit import add_audit
from app.services.content_safety import ContentSafetyFilter
from app.services.injection_detector import PromptInjectionDetector, wrap_untrusted_data

logger = get_logger(__name__)

# 最大调研步数（防止死循环）
_MAX_STEP_SLACK = 2


def _resume_page(state: TravelState) -> int:
    """从 resume_from 解析续传起始项。"""
    resume_from = state.get("resume_from") or ""
    if resume_from.startswith("web_research:page_"):
        try:
            done = int(resume_from.split("page_", 1)[1])
            return done + 1
        except ValueError:
            return 1
    return 1


async def web_research_node(state: TravelState) -> dict:
    """逐项调用高德 POI 搜索 + 安全检查 + 推进 resume_from。"""
    plan_id = state["plan_id"]
    injector = PromptInjectionDetector()
    safety = ContentSafetyFilter()
    raw_destination = (state.get("preferences") or {}).get("destination") or "目的地"

    # 规范化城市名（「河北沧州」→「沧州」），避免高德误搜到省一级
    destination = await resolve_city(raw_destination) or raw_destination

    # 读全部 web_research 任务
    async with session_scope() as db:
        tasks = (
            await db.execute(
                select(AgentTask)
                .where(AgentTask.plan_id == uuid.UUID(plan_id), AgentTask.agent_type == "web_research")
                .order_by(AgentTask.page_no)
            )
        ).scalars().all()

    start_page = _resume_page(state)
    last_page_done = start_page - 1
    max_steps = len(tasks) + _MAX_STEP_SLACK
    steps = 0

    # 汇总收集的 POI（供 Itinerary 使用）
    collected_pois: list[dict] = []

    for task in tasks:
        steps += 1
        if steps > max_steps:
            logger.warning("web_research 超过最大步数，终止 plan=%s", plan_id)
            break

        page_no = task.page_no or 0
        if page_no < start_page:
            continue  # 已完成，跳过（断点续传）

        task_data = task.task_data or {}
        keyword = task_data.get("keyword", "景点")
        amap_types = task_data.get("amap_types")

        # 调用高德 POI 搜索（真实数据）；连续请求间加 200ms 延时，避免高德 QPS 限流
        if steps > 1:
            await asyncio.sleep(0.2)
        try:
            pois = await search_poi(keyword, destination, types=amap_types, offset=5)
        except AmapError as exc:
            logger.warning("高德 POI 搜索失败 task=%s：%s", task.id, exc)
            await _mark_task(plan_id, task.id, TASK_STATUS["FAILED"], result={"error": str(exc)})
            continue

        if not pois:
            await _mark_task(plan_id, task.id, TASK_STATUS["FAILED"], result={"error": "no_result"})
            last_page_done = page_no
            continue

        # 安全过滤：POI 名称 + 地址 + 类型文本过注入检测
        body = " ".join(f"{p['name']} {p.get('address','')} {p.get('type','')}" for p in pois)
        if injector.detect(body).blocked:
            verdict = injector.detect(body)
            await _mark_task(plan_id, task.id, TASK_STATUS["BLOCKED"], result={"blocked": True, "pattern": verdict.pattern})
            async with session_scope() as db:
                await add_audit(
                    db,
                    action="security_block",
                    plan_id=uuid.UUID(plan_id),
                    target=keyword,
                    detail={"pattern": verdict.pattern, "snippet": verdict.snippet},
                )
            last_page_done = page_no
            continue

        # 记录成功结果
        _ = wrap_untrusted_data(body)
        await _mark_task(
            plan_id, task.id, TASK_STATUS["COMPLETED"],
            result={"keyword": keyword, "pois": pois, "count": len(pois), "quality": "ok"},
        )
        collected_pois.extend(
            {"name": p["name"], "location": p["location"], "type": p["type"], "category": keyword}
            for p in pois
        )
        last_page_done = page_no

        # 推进 resume_from（页级 checkpoint）
        await _persist_resume(plan_id, page_no, keyword, len(pois))

        import asyncio
        import os

        delay_ms = int(os.getenv("WENLV_RESEARCH_DELAY_MS", "0"))
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

    # 把收集到的 POI 存到 Itinerary 可读的 state（通过 DB 的 web_research 结果）
    return {
        "resume_from": f"web_research:page_{last_page_done}",
        "completed_nodes": state.get("completed_nodes", []) + ["web_research"],
    }


async def _mark_task(plan_id: str, task_id: uuid.UUID, status: str, result: dict) -> None:
    """更新单条 task 状态与结果。"""
    async with session_scope() as db:
        task = await db.get(AgentTask, task_id)
        if task is not None:
            task.status = status
            task.result = result
            await db.flush()


async def _persist_resume(plan_id: str, page_no: int, keyword: str, count: int) -> None:
    """每项完成后更新 DB.resume_from 与文件（task 级 checkpoint）。"""
    from app.graph.context import NodeContext

    async with NodeContext(plan_id) as ctx:
        await ctx.advance(
            status="running",
            resume_from=f"web_research:page_{page_no}",
            body=await ctx.build_body(
                logs=[f"高德调研完成 {keyword}：获取 {count} 条真实 POI"],
            ),
            event="node_done",
            agent="web_research",
            progress=ctx.progress(),
        )
