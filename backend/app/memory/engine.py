"""共享图记忆引擎（工单 7 D2：自研轻量 Mem0 风格）。

核心链路：
- 实体抽取：从节点产出文本中抽实体三元组（Mock 下用规则引擎，真模型走 LLMProvider）
- 三元组沉淀：upsert 语义（src_key, dst_key, relation 命中即合并）
- 双路检索：向量（应用层余弦）+ 图拓扑（1-2 跳邻域）融合
- 记忆缓存：Redis，按 memory_version 失效

Schema 三类（D3）：chat_memory / domain_wiki / code_graph。
"""

from __future__ import annotations

import json as _json
import re
import uuid

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.core.redis_client import get_redis, key
from app.models import GraphEdge, GraphNode, MemoryEvent

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# 规则抽取（Mock 确定性）：识别三类关系
# --------------------------------------------------------------------------- #

# 关系模式：(正则, relation, src_type, dst_type, node_class)
# 过敏原用通用名词匹配（不限白名单），支持香菜/花粉/青霉素等任意过敏原
# 优先「对X过敏」结构（X 紧邻「过敏」，最准），兜底「X过敏」（取过敏前 1-3 字）
_EXTRACTION_RULES: list[tuple[re.Pattern, str, str, str, str]] = [
    # 过敏约束一：对XX过敏（最准）
    (re.compile(r"对([一-龥A-Za-z]{1,6}?)(?:严重)?过敏"), "HAS_ALLERGY", "User", "Food", "chat_memory"),
    # 过敏约束二：XX严重过敏（严重前是过敏原）
    (re.compile(r"([一-龥A-Za-z]{1,6}?)(?:严重)过敏"), "HAS_ALLERGY", "User", "Food", "chat_memory"),
    # 过敏约束三：XX过敏（兜底，取过敏前 1-3 字，避免主语粘连）
    (re.compile(r"([一-龥A-Za-z]{1,3})过敏"), "HAS_ALLERGY", "User", "Food", "chat_memory"),
    # 偏好：喜欢/偏好/偏 ...
    (re.compile(r"(?:喜欢|偏好|偏爱|想|要)\s*([一-龥\w]{1,12}?)(?:游|玩|吃|逛|去|住|看|体验|风光|美食)"), "PREFERS", "User", "Preference", "chat_memory"),
    # 目的地：去 X 游 / X 之游
    (re.compile(r"(?:去|到)?([一-龥]{2,8})(?:游|旅|之行|之旅|自由行)"), "PLANS_VISIT", "User", "City", "chat_memory"),
    # 景点位于城市：X 是 Y 的景点（domain_wiki）
    (re.compile(r"([一-龥\w]{2,20})位于([一-龥]{2,8})"), "LOCATED_IN", "Attraction", "City", "domain_wiki"),
]


def rule_extract_triples(text: str, owner_user_id: uuid.UUID | None = None) -> list[dict]:
    """规则抽取（确定性降级，识别常见过敏/偏好/目的地）。"""
    triples: list[dict] = []
    if not text:
        return triples

    allergy_found = False  # 一个文本只保留第一个过敏原（多条过敏规则去重）

    for pattern, relation, src_type, dst_type, node_class in _EXTRACTION_RULES:
        for m in pattern.finditer(text):
            if relation == "HAS_ALLERGY":
                if allergy_found:
                    continue  # 已有过敏三元组，跳过重复
                src_key = "user"
                dst_key = m.group(1)
                props = {"severity": "severe" if "严重" in text[m.start():m.end() + 10] else "normal"}
                allergy_found = True
            elif relation == "PREFERS":
                src_key = "user"
                dst_key = m.group(1)
                props = {}
            elif relation == "PLANS_VISIT":
                src_key = "user"
                dst_key = m.group(1)
                props = {}
            elif relation == "LOCATED_IN":
                src_key = m.group(1)
                dst_key = m.group(2)
                props = {}
            else:
                continue

            triples.append(
                {
                    "src_type": src_type,
                    "src_key": src_key,
                    "dst_type": dst_type,
                    "dst_key": dst_key,
                    "relation": relation,
                    "node_class": node_class,
                    "properties": props,
                }
            )
    return triples


# LLM 抽取的 JSON Schema（要求模型返回三元组列表）
_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "src_type": {"type": "string"},
                    "src_key": {"type": "string"},
                    "dst_type": {"type": "string"},
                    "dst_key": {"type": "string"},
                    "relation": {"type": "string"},
                    "node_class": {"type": "string", "enum": ["chat_memory", "domain_wiki", "code_graph"]},
                    "properties": {"type": "object"},
                },
                "required": ["src_type", "src_key", "dst_type", "dst_key", "relation", "node_class"],
            },
        }
    },
    "required": ["triples"],
}


async def _llm_extract_triples(text: str, owner_user_id: uuid.UUID | None = None) -> list[dict]:
    """用真实 LLM 抽取三元组（支持任意过敏/偏好，不限白名单）。

    返回标准化的三元组列表；LLM 失败或返回空时返回 []（由调用方降级到规则）。
    """
    from app.agents.llm import build_system_prompt, get_llm

    llm = get_llm()
    # 若是 Mock（llm_mode != real 或未配置），直接返回空 → 走规则降级
    from app.core.config import settings

    if settings.llm_mode != "real":
        return []

    prompt = (
        "从下面的旅行需求文本中抽取知识三元组，用于构建用户长期记忆图谱。\n"
        "请严格按以下 JSON 格式输出，字段名必须完全一致：\n"
        '{"triples": [{"src_type": "User", "src_key": "用户", "dst_type": "Food", "dst_key": "香菜", "relation": "HAS_ALLERGY", "node_class": "chat_memory", "properties": {"severity": "severe"}}]}\n'
        "关系类型（relation）可选：HAS_ALLERGY(过敏)、PREFERS(偏好)、PLANS_VISIT(计划去)、LOCATED_IN(位于)、HATES(厌恶)、LIKES(喜欢)。\n"
        "node_class 用 chat_memory（个人偏好/约束）或 domain_wiki（领域实体）。\n"
        "注意：过敏原可以是任意食物或物质（如香菜、花粉、青霉素、尘螨），不要限定范围。\n"
        "src_key 填具体的人/主体名，dst_key 填具体实体名。"
    )
    try:
        result = await llm.complete(
            [
                {"role": "system", "content": build_system_prompt("memory_extract", prompt)},
                {"role": "user", "content": text},
            ],
            schema=_EXTRACT_SCHEMA,
        )
    except Exception as exc:
        logger.warning("LLM 抽取失败，降级规则：%s", exc)
        return []

    structured = result.structured
    if not isinstance(structured, dict):
        return []

    triples = structured.get("triples") or []
    # 规范化 + 过滤非法项
    clean: list[dict] = []
    for t in triples:
        if not isinstance(t, dict):
            continue
        if not all(k in t for k in ("src_type", "src_key", "dst_type", "dst_key", "relation")):
            continue
        clean.append(
            {
                "src_type": str(t["src_type"]),
                "src_key": str(t["src_key"]),
                "dst_type": str(t["dst_type"]),
                "dst_key": str(t["dst_key"]),
                "relation": str(t["relation"]),
                "node_class": t.get("node_class", "chat_memory"),
                "properties": t.get("properties") or {},
            }
        )
    return clean


async def extract_triples(text: str, owner_user_id: uuid.UUID | None = None) -> list[dict]:
    """抽取三元组：优先真 LLM，失败/空则降级到规则引擎。

    返回 [{src_type,src_key,dst_type,dst_key,relation,node_class,properties}]。
    """
    if not text:
        return []

    llm_triples = await _llm_extract_triples(text, owner_user_id)
    if llm_triples:
        return llm_triples

    # 降级：规则引擎
    return rule_extract_triples(text, owner_user_id)


async def _embed(texts: list[str]) -> list[list[float]]:
    """语义向量化（真 LLM / Mock 哈希兜底），返回等长向量列表。

    分批请求（每批 16 个），避免百炼 embedding 单次 input 过大导致服务器断连/400。
    """
    from app.agents.llm import get_llm

    if not texts:
        return []

    batch_size = 10  # 百炼 text-embedding-v3 单次 input 上限为 10
    llm = get_llm()
    out: list[list[float]] = []
    try:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            out.extend(await llm.embed(batch))
        return out
    except Exception as exc:
        logger.warning("embed 失败，降级哈希：%s", exc)
        from app.agents.llm import _hash_embedding

        return [_hash_embedding(t, settings.embedding_dim) for t in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(0.0, dot)  # a,b 已归一化


# --------------------------------------------------------------------------- #
# 三元组 upsert
# --------------------------------------------------------------------------- #


async def _upsert_node(db, node_class: str, type_: str, key_: str, properties: dict, owner_user_id, embedding: list | None) -> GraphNode:
    """获取或创建节点，返回节点（含 id）。"""
    result = await db.execute(
        select(GraphNode).where(
            GraphNode.node_class == node_class,
            GraphNode.type == type_,
            GraphNode.key == key_,
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        node = GraphNode(
            node_class=node_class,
            type=type_,
            key=key_,
            owner_user_id=owner_user_id,
            properties=properties,
            embedding=embedding,
        )
        db.add(node)
        await db.flush()
    else:
        # 合并属性（新值覆盖，version+1）
        merged = {**(node.properties or {}), **properties}
        node.properties = merged
        node.version += 1
        if embedding is not None:
            node.embedding = embedding
        await db.flush()
    return node


async def _upsert_edge(db, src_id: int, dst_id: int, relation: str, properties: dict, confidence: float) -> None:
    """获取或创建边，命中则合并（confidence 取较大值）。"""
    result = await db.execute(
        select(GraphEdge).where(
            GraphEdge.src_id == src_id,
            GraphEdge.dst_id == dst_id,
            GraphEdge.relation == relation,
        )
    )
    edge = result.scalar_one_or_none()
    if edge is None:
        edge = GraphEdge(
            src_id=src_id,
            dst_id=dst_id,
            relation=relation,
            properties=properties,
            confidence=confidence,
            merged_from=[],
        )
        db.add(edge)
    else:
        edge.properties = {**(edge.properties or {}), **properties}
        edge.confidence = max(edge.confidence, confidence)
        merged_list = list(edge.merged_from or [])
        merged_list.append({"confidence": confidence})
        edge.merged_from = merged_list
    await db.flush()


async def extract_and_store(
    text: str,
    *,
    source_node: str,
    plan_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> int:
    """抽取三元组并持久化，返回成功写入的三元组数量。失败不抛（降级）。"""
    triples = await extract_triples(text, owner_user_id)
    if not triples:
        return 0

    count = 0
    try:
        # 批量向量化所有 (src_key, dst_key) 文本，减少 embedding 调用次数
        texts_to_embed = [
            f"{t['src_type']}:{t['src_key']}" for t in triples
        ] + [
            f"{t['dst_type']}:{t['dst_key']}" for t in triples
        ]
        embs = await _embed(texts_to_embed)
        src_embs = embs[: len(triples)]
        dst_embs = embs[len(triples):]

        async with session_scope() as db:
            for i, t in enumerate(triples):
                src = await _upsert_node(
                    db, t["node_class"], t["src_type"], t["src_key"], {}, owner_user_id, src_embs[i]
                )
                dst = await _upsert_node(
                    db, t["node_class"], t["dst_type"], t["dst_key"], t["properties"], owner_user_id, dst_embs[i]
                )
                await _upsert_edge(db, src.id, dst.id, t["relation"], t["properties"], 0.9)

                db.add(
                    MemoryEvent(
                        plan_id=plan_id,
                        source_node=source_node,
                        raw_excerpt=text[:500],
                        extracted=t,
                        status="ok",
                    )
                )
                count += 1
    except Exception as exc:
        logger.warning("记忆抽取失败 source=%s err=%s", source_node, exc)
        # 记录失败事件（降级，不阻塞主流程）
        try:
            async with session_scope() as db:
                db.add(MemoryEvent(plan_id=plan_id, source_node=source_node, raw_excerpt=text[:500], extracted={}, status="failed"))
        except Exception:
            pass
    return count


# --------------------------------------------------------------------------- #
# 双路检索
# --------------------------------------------------------------------------- #


async def retrieve(
    query: str,
    *,
    user_id: uuid.UUID | None = None,
    top_k: int = 20,
) -> list[dict]:
    """双路检索：向量相似 + 图拓扑（1 跳邻域），按 confidence × 距离衰减排序。

    带 Redis 缓存（TTL 60s，D7），热路径命中缓存保证 P95 < 150ms。
    """
    import json as _json

    from app.core.config import settings

    # 缓存 key：查询词 + 用户域（hash 稳定）
    cache_key = key(f"memory:retrieve:{_hash_key(query, user_id)}")

    # 先查缓存
    try:
        r = get_redis()
        cached = await r.get(cache_key)
        if cached:
            return _json.loads(cached)
    except Exception:
        pass  # 缓存不可用直接查 DB

    query_emb = (await _embed([query]))[0]

    async with session_scope() as db:
        if settings.vector_backend == "pgvector":
            # pgvector 余弦距离：<=> 越小越相似，取 top_k 候选
            from sqlalchemy import text as _text

            stmt = (
                select(GraphNode, GraphNode.embedding.cosine_distance(query_emb).label("dist"))
                .where(
                    (GraphNode.node_class == "chat_memory")
                    | (GraphNode.owner_user_id == user_id if user_id else True)
                )
                .order_by(GraphNode.embedding.cosine_distance(query_emb))
                .limit(top_k)
            )
            rows = (await db.execute(stmt)).all()
            scored: list[tuple[GraphNode, float]] = [
                (n, round(1.0 - float(dist), 4)) for n, dist in rows if n.embedding is not None
            ]
        else:
            nodes = (
                await db.execute(
                    select(GraphNode).where(
                        (GraphNode.node_class == "chat_memory")
                        | (GraphNode.owner_user_id == user_id if user_id else True)
                    )
                )
            ).scalars().all()
            scored = []
            for n in nodes:
                sim = _cosine(query_emb, n.embedding or [])
                if sim > 0:
                    scored.append((n, sim))

        # 图拓扑：从命中节点出发取 1 跳邻域
        result: list[dict] = []
        seen: set[str] = set()
        for node, sim in scored:
            if node.key in seen:
                continue
            seen.add(node.key)
            result.append(
                {
                    "node_class": node.node_class,
                    "type": node.type,
                    "key": node.key,
                    "properties": node.properties,
                    "score": round(sim, 4),
                    "retrieval_path": f"vector:{node.type}:{node.key}",
                }
            )

            # 1 跳出边
            edges = (
                await db.execute(
                    select(GraphEdge).where(GraphEdge.src_id == node.id).limit(top_k)
                )
            ).scalars().all()
            for e in edges:
                dst = await db.get(GraphNode, e.dst_id)
                if dst and dst.key not in seen:
                    seen.add(dst.key)
                    result.append(
                        {
                            "node_class": dst.node_class,
                            "type": dst.type,
                            "key": dst.key,
                            "properties": dst.properties,
                            "score": round(sim * e.confidence, 4),
                            "retrieval_path": f"graph:{node.key}-[{e.relation}]->{dst.key}",
                        }
                    )

    result.sort(key=lambda x: x["score"], reverse=True)
    result = result[:top_k]

    # 写缓存（60s）
    try:
        r = get_redis()
        await r.set(cache_key, _json.dumps(result, ensure_ascii=False), ex=60)
    except Exception:
        pass

    return result


def _hash_key(query: str, user_id: uuid.UUID | None) -> str:
    """稳定的缓存 key 后缀。"""
    import hashlib

    raw = f"{query}:{user_id or 'all'}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
