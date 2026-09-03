"""知识库文档分块表（RAG B 部分：文旅领域语料）。

每行 = 一篇文档的一个 chunk，embedding 用 pgvector 存语义向量，
检索时按余弦距离召回原文，供 Agent 调研/编排节点注入 prompt。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(128), nullable=False)  # 文档标识（文件名去扩展）
    title: Mapped[str] = mapped_column(String(256), nullable=False)  # 文档标题
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # 景点/美食/景区政策/季节/交通/住宿
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 分块序号
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)  # 原文 chunk
    embedding: Mapped[list | None] = mapped_column(Vector(768))  # 语义向量
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)  # 附加信息（来源等）
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_doc_chunk", "doc_id", "chunk_index", unique=True),
        Index("idx_doc_category", "category"),
    )
