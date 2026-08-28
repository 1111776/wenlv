"""Intake Agent：偏好解析（说明书 §5.1 第 1 节点）。

输入：用户 query + 可选结构化字段 → 输出 preferences 并写回 DB。
- 支持世界任意目的地（中文 / 英文 / 国家 / 城市 / 洲）
- Mock 模式下确定性解析；LLM 失败时正则 Fallback（L2 降级）
- 合并顺序：正则解析 < 请求结构化字段 < LLM 输出
"""

from __future__ import annotations

import re

from app.agents.llm import build_system_prompt, get_llm
from app.core.logging import get_logger
from app.graph.state import TravelState

logger = get_logger(__name__)

# 目的地匹配：中文地名（2~8 字）后跟"游/旅/行/之"；或英文单词（可含空格）
_DEST_CN = re.compile(r"([一-龥]{2,8}?)(?:游|旅|之行|之旅|行)")
_DEST_EN = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Za-z]+){0,2})\b")

# 常见目的地兜底词（若正则没抓到，从 query 里找这些词）
_KNOWN_PLACES = [
    "巴黎", "伦敦", "东京", "纽约", "洛杉矶", "曼谷", "新加坡", "首尔",
    "悉尼", "墨尔本", "迪拜", "罗马", "巴厘岛", "马尔代夫", "冰岛",
    "瑞士", "法国", "意大利", "日本", "泰国", "美国", "澳洲", "新西兰",
    "北京", "上海", "广州", "深圳", "成都", "重庆", "西安", "杭州",
    "苏州", "南京", "厦门", "三亚", "桂林", "张家界", "西藏", "新疆",
    "海南", "青海", "甘肃", "四川", "贵州", "广西", "云南",
]


def _fallback_parse(query: str) -> dict:
    """正则降级：从自然语言里抽目的地/天数/预算/出行人。"""
    prefs: dict = {"tags": []}
    # 天数：N天 / N 天 / N晚
    m = re.search(r"(\d+)\s*(?:天|晚)", query)
    if m:
        prefs["days"] = int(m.group(1))
    # 预算：预算 15000 / 1.5万 / 1.5w
    m = re.search(r"预算\s*([0-9.]+)\s*(万|w|W|元|块)?", query)
    if m:
        amt = float(m.group(1))
        if m.group(2) in ("万",):
            amt *= 10000
        prefs["budget_limit"] = amt
    # 出行人：2大1小 / 3人 / 一家3口
    m = re.search(r"(\d+)\s*大\s*(\d+)\s*小", query)
    if m:
        prefs["party"] = {"adults": int(m.group(1)), "children": int(m.group(2))}
    else:
        m = re.search(r"(\d+)\s*人", query)
        if m:
            prefs["party"] = {"adults": int(m.group(1)), "children": 0}
    # 目的地：中文地名 / 英文地名 / 已知地名兜底
    m = _DEST_CN.search(query)
    if m:
        prefs["destination"] = m.group(1)
    else:
        m = _DEST_EN.search(query)
        if m:
            prefs["destination"] = m.group(1).strip()
        else:
            for place in _KNOWN_PLACES:
                if place in query:
                    prefs["destination"] = place
                    break
    # 兴趣标签
    for kw in ["自然风光", "人文历史", "美食", "亲子", "购物", "海岛", "滑雪", "少购物"]:
        if kw in query:
            prefs["tags"].append(kw)
    return prefs


async def intake_node(state: TravelState) -> dict:
    """解析偏好并落库，合并请求结构化字段。"""
    import uuid

    from app.core.database import session_scope
    from app.models import TravelPlan

    plan_id = state["plan_id"]
    query = state["query"]

    degraded = False

    # 读取 DB 里已有的偏好（创建行程时 API 已写入结构化字段，如 destination）
    async with session_scope() as db:
        plan = await db.get(TravelPlan, uuid.UUID(plan_id))
        existing_prefs = dict(plan.preferences) if plan and plan.preferences else {}

    # LLM 解析（Mock 返回空 structured，主要靠正则）
    llm_prefs: dict = {}
    try:
        llm = get_llm()
        result = await llm.complete(
            [
                {"role": "system", "content": build_system_prompt("intake", "解析旅行偏好")},
                {"role": "user", "content": query},
            ]
        )
        llm_prefs = result.structured or {}
    except Exception as exc:
        logger.warning("Intake LLM 失败，正则降级：%s", exc)
        degraded = True

    # 合并：正则 < 请求结构化字段 < LLM。过滤空值，保留已填写的结构化字段。
    fallback = _fallback_parse(query)
    merged: dict = {**fallback, **{k: v for k, v in existing_prefs.items() if v not in (None, "", [])}, **llm_prefs}

    if degraded:
        merged["quality"] = "degraded"

    async with session_scope() as db:
        plan = await db.get(TravelPlan, uuid.UUID(plan_id))
        if plan is None:
            raise RuntimeError(f"行程不存在：{plan_id}")
        plan.preferences = merged
        # 若正则/结构化解析出了 title，可顺手更新（便于列表展示）
        await db.flush()

    # 节点完成后回调记忆抽取（D5：同步轻量抽取，失败不阻塞主流程）
    try:
        from app.memory import engine as memory_engine

        await memory_engine.extract_and_store(
            query,
            source_node="intake",
            plan_id=uuid.UUID(plan_id),
            owner_user_id=plan.user_id if plan else None,
        )
    except Exception as exc:
        logger.warning("Intake 记忆抽取失败：%s", exc)

    logger.info("Intake 解析结果 plan=%s destination=%s", plan_id, merged.get("destination"))
    return {"preferences": merged}
