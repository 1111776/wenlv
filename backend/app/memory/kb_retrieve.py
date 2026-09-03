"""文旅知识库检索（RAG B 部分）。

语义检索 document_chunks，返回原文 chunk + 来源，供调研/编排节点注入 prompt。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import DocumentChunk

logger = get_logger(__name__)


async def search_kb(query: str, top_k: int = 5, category: str | None = None) -> list[dict]:
    """语义检索知识库，返回 [{title, category, chunk_text, score}]。

    pgvector 余弦距离排序；失败降级返回空列表（不阻塞主流程）。
    """
    from app.memory.engine import _embed

    if not query:
        return []
    try:
        query_emb = (await _embed([query]))[0]
    except Exception as exc:
        logger.warning("知识库检索 embed 失败：%s", exc)
        return []

    try:
        async with session_scope() as db:
            stmt = select(
                DocumentChunk,
                DocumentChunk.embedding.cosine_distance(query_emb).label("dist"),
            )
            if category:
                stmt = stmt.where(DocumentChunk.category == category)
            stmt = (
                stmt.where(DocumentChunk.embedding.isnot(None))
                .order_by(DocumentChunk.embedding.cosine_distance(query_emb))
                .limit(top_k)
            )
            rows = (await db.execute(stmt)).all()
            return [
                {
                    "title": c.title,
                    "category": c.category,
                    "chunk_text": c.chunk_text,
                    "score": round(1.0 - float(dist), 4),
                }
                for c, dist in rows
            ]
    except Exception as exc:
        logger.warning("知识库检索失败：%s", exc)
        return []
