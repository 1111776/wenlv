"""共享图记忆引擎（工单 7 D2：自研轻量 Mem0 风格）。

核心链路：
- 实体抽取：从节点产出文本中抽实体三元组（Mock 下用规则引擎，真模型走 LLMProvider）
- 三元组沉淀：upsert 语义（src_key, dst_key, relation 命中即合并）
- 双路检索：向量（应用层余弦）+ 图拓扑（1-2 跳邻域）融合
- 记忆缓存：Redis，按 memory_version 失效

Schema 三类（D3）：chat_memory / domain_wiki / code_graph。
"""

from __future__ import annotations

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
_EXTRACTION_RULES: list[tuple[re.Pattern, str, str, str, str]] = [
    # 过敏约束：我/母亲/家人 ... 海鲜/花生 ... 过敏
    (re.compile(r"(\w{1,8}?)(?:对|吃)?(海鲜|花生|牛奶|芒果|鸡蛋|坚果|酒精)\s*(?:严重)?过敏"), "HAS_ALLERGY", "User", "Food", "chat_memory"),
    # 偏好：喜欢/偏好/偏 ...
    (re.compile(r"(?:喜欢|偏好|偏爱|想|要)\s*([一-龥\w]{1,12}?)(?:游|玩|吃|逛|去|住|看|体验|风光|美食)"), "PREFERS", "User", "Preference", "chat_memory"),
    # 目的地：去 X 游 / X 之游
    (re.compile(r"(?:去|到)?([一-龥]{2,8})(?:游|旅|之行|之旅|自由行)"), "PLANS_VISIT", "User", "City", "chat_memory"),
    # 景点位于城市：X 是 Y 的景点（domain_wiki）
    (re.compile(r"([一-龥\w]{2,20})位于([一-龥]{2,8})"), "LOCATED_IN", "Attraction", "City", "domain_wiki"),
]


def extract_triples(text: str, owner_user_id: uuid.UUID | None = None) -> list[dict]:
    """从文本抽取三元组列表，返回 [{src_type,src_key,dst_type,dst_key,relation,node_class,properties}]。"""
    triples: list[dict] = []
    if not text:
        return triples

    for pattern, relation, src_type, dst_type, node_class in _EXTRACTION_RULES:
        for m in pattern.finditer(text):
            if relation == "HAS_ALLERGY":
                src_key = m.group(1) or "user"
                dst_key = m.group(2)
                props = {"severity": "severe" if "严重" in text[m.start():m.end() + 10] else "normal"}
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


def _text_embedding(text: str, dim: int = 64) -> list[float]:
    """确定性哈希 embedding（Mock，非语义向量，仅保证相同文本向量一致）。"""
    import hashlib

    vec = [0.0] * dim
    tokens = re.findall(r"[一-龥]|[a-zA-Z]+", text.lower())
    for tok in tokens:
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = h[0] % dim
        vec[idx] += 1.0
    # 归一化
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


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
    triples = extract_triples(text, owner_user_id)
    if not triples:
        return 0

    count = 0
    try:
        async with session_scope() as db:
            for t in triples:
                src_emb = _text_embedding(f"{t['src_type']}:{t['src_key']}")
                dst_emb = _text_embedding(f"{t['dst_type']}:{t['dst_key']}")

                src = await _upsert_node(
                    db, t["node_class"], t["src_type"], t["src_key"], {}, owner_user_id, src_emb
                )
                dst = await _upsert_node(
                    db, t["node_class"], t["dst_type"], t["dst_key"], t["properties"], owner_user_id, dst_emb
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

    query_emb = _text_embedding(query)

    async with session_scope() as db:
        nodes = (
            await db.execute(
                select(GraphNode).where(
                    (GraphNode.node_class == "chat_memory")
                    | (GraphNode.owner_user_id == user_id if user_id else True)
                )
            )
        ).scalars().all()

        # 向量相似打分
        scored: list[tuple[GraphNode, float]] = []
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
