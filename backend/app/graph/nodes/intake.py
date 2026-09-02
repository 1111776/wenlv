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

# LLM 解析偏好用的 JSON Schema
_INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "origin": {"type": "string", "description": "出发地"},
        "destination": {"type": "string", "description": "目的地"},
        "days": {"type": "integer", "description": "行程天数"},
        "budget_limit": {"type": "number", "description": "预算上限"},
        "adults": {"type": "integer"},
        "children": {"type": "integer"},
        "elders": {"type": "integer"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


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


def _parse_origin(query: str) -> str | None:
    """解析出发地：从X到/去/前往 / 自X出发 / 开头「X到/去」。"""
    m = re.search(r"(?:从|自)\s*([一-龥]{2,8}?)\s*(?:到|去|前往|出发|飞|坐|乘)", query)
    if m:
        return m.group(1)
    m = re.search(r"([一-龥]{2,8}?)\s*出发", query)
    if m:
        return m.group(1)
    # 开头直接「X到/去」：北京到新疆 → 北京
    m = re.match(r"^([一-龥]{2,8}?)\s*(?:到|去|前往)", query)
    if m:
        return m.group(1)
    return None


def _parse_destination(query: str) -> str | None:
    """解析目的地。优先级：「到/去/前往X」 > 已知地名（取最后一个出现）> 英文地名。"""
    # 1. 到/去/前往 X（用已知地名精确截断，避免吞入「旅游/玩」等后缀）
    m = re.search(r"(?:到|去|前往)\s*([一-龥]{2,8})", query)
    if m:
        cand = m.group(1)
        for place in sorted(_KNOWN_PLACES, key=len, reverse=True):
            if cand == place or cand.startswith(place) or place in cand:
                return place
        # 列表外城市：去掉常见尾部动词/后缀
        cand = re.sub(r"(玩|游|旅|行|天|晚|住|吃)+$", "", cand)
        if cand:
            return cand
    # 2. 已知地名兜底：取最后一个出现的（「从A到B」中 B 是目的地，位置靠后）
    best_idx, best = -1, None
    for place in _KNOWN_PLACES:
        idx = query.find(place)
        if idx >= 0 and idx > best_idx:
            best_idx, best = idx, place
    if best:
        return best
    # 3. 英文地名
    m = _DEST_EN.search(query)
    if m:
        return m.group(1).strip()
    return None


def _parse_party(query: str) -> dict | None:
    """解析出行人数。支持 3成人2儿童1老人 / 3大2小1老 / 2大2儿童2老人 / 2大2小 / 4人 等。"""
    adults = children = elders = None

    m = re.search(r"(\d+)\s*(?:成\s*人|大\s*人|成\s*年\s*人)", query)
    if m:
        adults = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:儿\s*童|小\s*孩|孩\s*子)", query)
    if m:
        children = int(m.group(1))
    m = re.search(r"(\d+)\s*老\s*人", query)
    if m:
        elders = int(m.group(1))

    # 兜底：单字「大/小/老」（旅游语境 2大1小1老）
    if adults is None:
        m = re.search(r"(\d+)\s*大", query)
        if m:
            adults = int(m.group(1))
    if children is None:
        m = re.search(r"(\d+)\s*小", query)
        if m:
            children = int(m.group(1))
    if elders is None:
        m = re.search(r"(\d+)\s*老", query)
        if m:
            elders = int(m.group(1))

    if adults is None and children is None and elders is None:
        m = re.search(r"(\d+)\s*人", query)
        if m:
            return {"adults": int(m.group(1)), "children": 0, "elders": 0}
        return None

    return {
        "adults": adults or 0,
        "children": children or 0,
        "elders": elders or 0,
    }


def _fallback_parse(query: str) -> dict:
    """正则降级：从自然语言里抽出发地/目的地/天数/预算/出行人。"""
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
    # 出行人
    party = _parse_party(query)
    if party:
        prefs["party"] = party
    # 出发地 / 目的地（区分「从A到B」）
    origin = _parse_origin(query)
    if origin:
        prefs["origin"] = origin
    dest = _parse_destination(query)
    if dest:
        prefs["destination"] = dest
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

    # LLM 解析偏好（传 schema，真正提取 origin/destination/days/budget 等）
    llm_prefs: dict = {}
    try:
        llm = get_llm()
        result = await llm.complete(
            [
                {"role": "system", "content": build_system_prompt(
                    "intake",
                    "解析旅行偏好，严格按以下 JSON 字段输出（不要用其他字段名）："
                    "{\"origin\":\"出发地\",\"destination\":\"目的地\",\"days\":整数天数,"
                    "\"budget_limit\":预算数字,\"adults\":成人,\"children\":儿童,"
                    "\"elders\":老人,\"tags\":[\"兴趣\"]}。"
                    "注意区分「从A到B」的 A 是出发地(origin)、B 是目的地(destination)。"
                )},
                {"role": "user", "content": query},
            ],
            schema=_INTAKE_SCHEMA,
        )
        llm_prefs = result.structured or {}
        if not isinstance(llm_prefs, dict):
            llm_prefs = {}
    except Exception as exc:
        logger.warning("Intake LLM 失败，正则降级：%s", exc)
        degraded = True

    # 合并优先级：LLM < 查询文本正则 < 表单结构化字段。
    # 表单是用户显式输入，最权威；查询文本里的显式数字（N天/N成人等）其次；
    # LLM 只兜底填空 —— LLM 可能幻觉（如返回 days=1 / 人数错乱），
    # 数字类字段绝不能让它覆盖掉用户已明确给出的值。
    fallback = _fallback_parse(query)
    merged: dict = {
        **{k: v for k, v in llm_prefs.items() if v not in (None, "", [], {})},
        **{k: v for k, v in fallback.items() if v not in (None, "", [])},
        **{k: v for k, v in existing_prefs.items() if v not in (None, "", [])},
    }
    if degraded:
        merged["quality"] = "degraded"

    # 归一化出行人：party（表单/正则）优先于顶层字段（LLM），
    # 使预算/门票/报告统一按「成人+儿童+老人」正确计算人数。
    # 用显式 None 判断，避免 party 里明确的 0（如不带儿童）被 LLM 顶层幻觉覆盖。
    _party = merged.get("party") or {}
    adults = _party.get("adults")
    children = _party.get("children")
    elders = _party.get("elders")
    if adults is None:
        adults = merged.get("adults")
    if children is None:
        children = merged.get("children")
    if elders is None:
        elders = merged.get("elders")
    adults = int(adults or 0)
    children = int(children or 0)
    elders = int(elders or 0)
    if adults + children + elders <= 0:
        adults = 1
    merged["adults"] = adults
    merged["children"] = children
    merged["elders"] = elders
    merged["party"] = {
        **_party,
        "adults": adults,
        "children": children,
        "elders": elders,
    }

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
