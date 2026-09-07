"""文旅知识库检索（RAG B 部分）— 混合检索 + rerank 重排 + 引用溯源。

检索链路：
1. 双路召回：pgvector 语义向量 + BM25 关键词，RRF 融合取候选
2. rerank 精排：百炼 text-rerank 对候选按相关性重排
3. 返回带来源(doc_id/title/category)的 chunk，供生成时引用溯源
"""

from __future__ import annotations

import math
import re

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import DocumentChunk

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# BM25 关键词检索（纯内存，chunk 量级小，够用）
# --------------------------------------------------------------------------- #

def _tokenize(text: str) -> list[str]:
    """中文按字 + 英文按词切分（简单但有效的分词）。"""
    tokens = re.findall(r"[a-zA-Z0-9]+|[一-鿿]", (text or "").lower())
    return tokens


def _bm25_score(query: str, doc: str, k1: float = 1.5, b: float = 0.75) -> float:
    """BM25 打分：query 与单个 doc 的相关性。"""
    q_tokens = _tokenize(query)
    d_tokens = _tokenize(doc)
    if not q_tokens or not d_tokens:
        return 0.0
    avg_len = 100.0  # 假设平均长度（chunk 级，量小可近似）
    doc_len = len(d_tokens)
    score = 0.0
    tf = {}
    for t in d_tokens:
        tf[t] = tf.get(t, 0) + 1
    for qt in q_tokens:
        if qt not in tf:
            continue
        f = tf[qt]
        idf = 1.0  # 简化：单文档语料 idf 近似
        denom = f + k1 * (1 - b + b * doc_len / max(avg_len, 1))
        score += idf * (f * (k1 + 1)) / max(denom, 1e-9)
    return score


def _rrf_fusion(vector_ranked: list[dict], bm25_ranked: list[dict], k: int = 60) -> list[dict]:
    """RRF（Reciprocal Rank Fusion）融合两路结果，返回按融合分排序的列表。"""
    rrf: dict[int, float] = {}
    doc_map: dict[int, dict] = {}
    for rank, item in enumerate(vector_ranked):
        doc_map[item["id"]] = item
        rrf[item["id"]] = rrf.get(item["id"], 0.0) + 1.0 / (k + rank + 1)
    for rank, item in enumerate(bm25_ranked):
        doc_map[item["id"]] = item
        rrf[item["id"]] = rrf.get(item["id"], 0.0) + 1.0 / (k + rank + 1)
    merged = [(doc_map[did], score) for did, score in rrf.items()]
    merged.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in merged]


# --------------------------------------------------------------------------- #
# 主检索入口
# --------------------------------------------------------------------------- #

async def search_kb(
    query: str,
    top_k: int = 5,
    category: str | None = None,
    use_rerank: bool = True,
) -> list[dict]:
    """混合检索知识库：向量 + BM25 双路召回 → rerank 重排，返回带来源的 chunk。

    返回 [{id, title, category, doc_id, chunk_text, score, retrieval}]
    """
    from app.memory.engine import _embed

    if not query:
        return []

    # 1. 向量召回（语义）
    try:
        query_emb = (await _embed([query]))[0]
    except Exception as exc:
        logger.warning("知识库检索 embed 失败：%s", exc)
        return []

    async with session_scope() as db:
        # 取全部候选（chunk 量级小，直接全量拿，避免漏召回）
        stmt = select(DocumentChunk)
        if category:
            stmt = stmt.where(DocumentChunk.category == category)
        stmt = stmt.where(DocumentChunk.embedding.isnot(None))
        all_chunks = (await db.execute(stmt)).scalars().all()

    if not all_chunks:
        return []

    # 向量相似度
    vector_scored = []
    for c in all_chunks:
        # pgvector cosine_distance 转相似度
        try:
            dist = c.embedding.cosine_distance(query_emb)
            sim = 1.0 - float(dist)
        except Exception:
            sim = 0.0
        if sim > 0:
            vector_scored.append((c, sim))
    vector_scored.sort(key=lambda x: x[1], reverse=True)
    vector_ranked = [_to_item(c, sim, "vector") for c, sim in vector_scored[:50]]

    # BM25 关键词召回
    bm25_scored = []
    for c in all_chunks:
        s = _bm25_score(query, c.chunk_text)
        if s > 0:
            bm25_scored.append((c, s))
    bm25_scored.sort(key=lambda x: x[1], reverse=True)
    bm25_ranked = [_to_item(c, s, "bm25") for c, s in bm25_scored[:50]]

    # 2. RRF 融合
    fused = _rrf_fusion(vector_ranked, bm25_ranked)

    # 3. rerank 精排
    candidates = fused[: max(top_k * 3, 10)]
    if use_rerank and candidates:
        try:
            from app.agents.llm import get_llm

            llm = get_llm()
            scores = await llm.rerank(query, [c["chunk_text"] for c in candidates])
            for item, s in zip(candidates, scores):
                item["score"] = round(float(s), 4)
                item["retrieval"] = "rerank"
            candidates.sort(key=lambda x: x["score"], reverse=True)
        except Exception as exc:
            logger.warning("rerank 失败，用 RRF 融合分：%s", exc)

    return candidates[:top_k]


def _to_item(chunk: DocumentChunk, score: float, retrieval: str) -> dict:
    """DocumentChunk → 字典。"""
    return {
        "id": chunk.id,
        "doc_id": chunk.doc_id,
        "title": chunk.title,
        "category": chunk.category,
        "chunk_text": chunk.chunk_text,
        "score": round(float(score), 4),
        "retrieval": retrieval,
    }
