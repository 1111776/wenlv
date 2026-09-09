"""文旅知识库检索（RAG B 部分）— 混合检索 + rerank 重排 + 引用溯源。

检索链路：
1. 双路召回：pgvector 语义向量（SQL 级 cosine_distance，库内算距离）+ BM25 关键词（语料级 IDF），
   RRF 融合取候选
2. rerank 精排：百炼 text-rerank 对候选按相关性重排（网关不可用时降级，见 llm.rerank）
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


def _build_idf(docs_tokens: list[list[str]]) -> dict[str, float]:
    """语料级 BM25 IDF：log((N - df + 0.5) / (df + 0.5) + 1)，df = 含该词的文档数。

    罕见词 IDF 高（区分度高），常见字（如「的」「景区」）IDF 低，替代旧版写死的 idf=1.0。
    """
    n_docs = max(len(docs_tokens), 1)
    df: dict[str, int] = {}
    for toks in docs_tokens:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((n_docs - d + 0.5) / (d + 0.5) + 1.0) for t, d in df.items()}


def _bm25_score(
    query: str,
    doc_tokens: list[str],
    idf: dict[str, float],
    avg_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """BM25 打分：query 与单个 doc（已分词）的相关性。"""
    q_tokens = _tokenize(query)
    if not q_tokens or not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    tf: dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for qt in q_tokens:
        f = tf.get(qt)
        if not f:
            continue
        idf_w = idf.get(qt, 0.0)
        denom = f + k1 * (1 - b + b * doc_len / max(avg_len, 1.0))
        score += idf_w * (f * (k1 + 1)) / max(denom, 1e-9)
    return score


def _rrf_fusion(vector_ranked: list[dict], bm25_ranked: list[dict], k: int = 60) -> list[dict]:
    """RRF（Reciprocal Rank Fusion）融合两路结果，返回按融合分排序的列表。

    双路都命中的 chunk 标记为 hybrid，并保留直观的 0-1 向量相似度分
    （BM25 是原始相关分，量纲不同，前端按「BM25 分」单独展示）。
    """
    rrf: dict[int, float] = {}
    doc_map: dict[int, dict] = {}
    vector_items: dict[int, dict] = {}
    for rank, item in enumerate(vector_ranked):
        vector_items[item["id"]] = item
        doc_map[item["id"]] = item
        rrf[item["id"]] = rrf.get(item["id"], 0.0) + 1.0 / (k + rank + 1)
    for rank, item in enumerate(bm25_ranked):
        rrf[item["id"]] = rrf.get(item["id"], 0.0) + 1.0 / (k + rank + 1)
        if item["id"] in vector_items:
            # 双路命中：保留向量相似度分，标 hybrid
            item = dict(item, score=vector_items[item["id"]]["score"], retrieval="hybrid")
        doc_map[item["id"]] = item
    merged = [(doc_map[did], score) for did, score in rrf.items()]
    merged.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in merged]


# --------------------------------------------------------------------------- #
# 向量召回：pgvector SQL 级 + 应用层兜底
# --------------------------------------------------------------------------- #

async def _vector_recall(query_emb: list[float], category: str | None) -> list[dict]:
    """向量召回 top50：pgvector 在库内算 cosine 距离（SQL 级）。

    vector_backend=cosine 或 SQL 异常时，退回应用层余弦打分（全量载入）。
    """
    if settings.vector_backend == "pgvector":
        try:
            async with session_scope() as db:
                dist_expr = DocumentChunk.embedding.cosine_distance(query_emb).label("dist")
                stmt = select(DocumentChunk, dist_expr).where(
                    DocumentChunk.embedding.isnot(None)
                )
                if category:
                    stmt = stmt.where(DocumentChunk.category == category)
                stmt = stmt.order_by(DocumentChunk.embedding.cosine_distance(query_emb)).limit(50)
                rows = (await db.execute(stmt)).all()
            return [
                _to_item(chunk, 1.0 - float(dist), "vector")
                for chunk, dist in rows
                if dist is not None and (1.0 - float(dist)) > 0
            ]
        except Exception as exc:
            logger.warning("pgvector SQL 召回失败，退回应用层余弦：%s", exc)

    # 应用层兜底：全量载入 + Python 余弦（vector_backend=cosine 时走这里）
    from app.memory.engine import _cosine

    async with session_scope() as db:
        stmt = select(DocumentChunk).where(DocumentChunk.embedding.isnot(None))
        if category:
            stmt = stmt.where(DocumentChunk.category == category)
        all_chunks = (await db.execute(stmt)).scalars().all()
    scored = []
    for c in all_chunks:
        sim = _cosine(query_emb, c.embedding or [])
        if sim > 0:
            scored.append((c, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [_to_item(c, s, "vector") for c, s in scored[:50]]


# --------------------------------------------------------------------------- #
# 主检索入口
# --------------------------------------------------------------------------- #

async def search_kb(
    query: str,
    top_k: int = 5,
    category: str | None = None,
    use_rerank: bool = True,
) -> list[dict]:
    """混合检索知识库：向量 + BM25 双路召回 → RRF 融合 → rerank 重排，返回带来源的 chunk。

    返回 [{id, title, category, doc_id, chunk_text, score, retrieval}]
    """
    from app.memory.engine import _embed

    if not query:
        return []

    # 1. 向量召回（语义，pgvector SQL 级 cosine_distance）
    try:
        query_emb = (await _embed([query]))[0]
    except Exception as exc:
        logger.warning("知识库检索 embed 失败：%s", exc)
        return []
    vector_ranked = await _vector_recall(query_emb, category)

    # 2. BM25 关键词召回（语料级 IDF + 真实平均文档长度）
    async with session_scope() as db:
        stmt = select(DocumentChunk)
        if category:
            stmt = stmt.where(DocumentChunk.category == category)
        all_chunks = (await db.execute(stmt)).scalars().all()

    if not all_chunks and not vector_ranked:
        return []

    docs_tokens = [_tokenize(c.chunk_text) for c in all_chunks]
    idf = _build_idf(docs_tokens)
    avg_len = (sum(len(t) for t in docs_tokens) / len(docs_tokens)) if docs_tokens else 1.0

    bm25_scored = []
    for c, d_toks in zip(all_chunks, docs_tokens):
        s = _bm25_score(query, d_toks, idf, avg_len)
        if s > 0:
            bm25_scored.append((c, s))
    bm25_scored.sort(key=lambda x: x[1], reverse=True)
    bm25_ranked = [_to_item(c, s, "bm25") for c, s in bm25_scored[:50]]

    # 3. RRF 融合
    fused = _rrf_fusion(vector_ranked, bm25_ranked)

    # 4. rerank 精排
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
