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

# 高德 QPS 限流：免费配额约 3 QPS，并发抓取时用全局节流保证
# 相邻两次高德请求间隔 ≥ 0.4s（≈2.5 QPS），超限时再退避重试
_amap_gap = 0.4
_amap_lock: asyncio.Lock | None = None
_last_amap_at: float = 0.0


async def _amap_throttle() -> None:
    """进程内全局限速：保证相邻两次高德请求间隔不小于 _amap_gap 秒。"""
    global _amap_lock, _last_amap_at
    if _amap_lock is None:
        _amap_lock = asyncio.Lock()
    async with _amap_lock:
        loop = asyncio.get_running_loop()
        wait = _last_amap_at + _amap_gap - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_amap_at = loop.time()


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
    """并发调用高德 POI 搜索（信号量限流）+ 安全检查 + 按页序推进 resume_from。"""
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

    # 汇总收集的 POI（供 Itinerary 使用）
    collected_pois: list[dict] = []

    # 待处理任务（跳过已完成页，断点续传），并发抓取后按页序写回
    pending = [t for t in tasks if (t.page_no or 0) >= start_page][:max_steps]

    _SEM = asyncio.Semaphore(4)  # 高德/embed 网关限流：最多 4 页同时抓

    async def _fetch(task: AgentTask) -> dict:
        """单页 IO 抓取：KB 检索 + 高德 POI（只做网络请求，不写 DB）。"""
        task_data = task.task_data or {}
        keyword = task_data.get("keyword", "景点")
        amap_types = task_data.get("amap_types")

        # 知识库检索（RAG B）：按目的地+关键词召回文旅语料，附到任务结果供后续节点使用
        kb_hits: list[dict] = []
        try:
            from app.memory.kb_retrieve import search_kb

            kb_hits = await search_kb(f"{destination} {keyword}", top_k=3)
        except Exception as exc:
            logger.warning("知识库检索失败（忽略）：%s", exc)

        async with _SEM:
            pois = None
            for attempt in range(3):  # 首次 + 2 次 QPS 限流退避重试
                await _amap_throttle()
                try:
                    pois = await search_poi(keyword, destination, types=amap_types, offset=5)
                    break
                except AmapError as exc:
                    # 高德 QPS 超限（infocode=10021/CUQPS）：退避后重试；其他错误直接失败
                    if ("10021" in str(exc) or "CUQPS" in str(exc)) and attempt < 2:
                        await asyncio.sleep(0.6 * (attempt + 1))
                        continue
                    logger.warning("高德 POI 搜索失败 task=%s：%s", task.id, exc)
                    return {"keyword": keyword, "amap_error": str(exc)}

        import os

        delay_ms = int(os.getenv("WENLV_RESEARCH_DELAY_MS", "0"))
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)
        return {"keyword": keyword, "kb_hits": kb_hits, "pois": pois}

    # 并发抓取全部待处理页（gather 保持输入顺序 = 页序）
    fetch_results = await asyncio.gather(*[_fetch(t) for t in pending], return_exceptions=True)

    # 按页序写回：安全过滤 → 落库 → 推进页级 checkpoint（语义与串行版一致）
    for task, res in zip(pending, fetch_results):
        page_no = task.page_no or 0
        if isinstance(res, Exception):
            await _mark_task(plan_id, task.id, TASK_STATUS["FAILED"], result={"error": str(res)})
            continue

        keyword = res["keyword"]

        if "amap_error" in res:
            await _mark_task(plan_id, task.id, TASK_STATUS["FAILED"], result={"error": res["amap_error"]})
            continue  # 高德失败不推进 checkpoint，下次续传重试

        pois = res["pois"]
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
            result={"keyword": keyword, "pois": pois, "count": len(pois), "quality": "ok", "kb_hits": res["kb_hits"]},
        )
        collected_pois.extend(
            {"name": p["name"], "location": p["location"], "type": p["type"], "category": keyword}
            for p in pois
        )
        last_page_done = page_no

        # 推进 resume_from（页级 checkpoint）
        await _persist_resume(plan_id, page_no, keyword, len(pois))

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
