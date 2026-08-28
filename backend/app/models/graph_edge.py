"""图记忆边表（工单 7 D4：三元组关系）。

示例：(User:advisor_demo)-[HAS_ALLERGY {severity}]->(Food:seafood)
(src_id, dst_id, relation) 唯一约束支撑 upsert 合并。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    src_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dst_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relation: Mapped[str] = mapped_column(String(64), nullable=False)  # HAS_ALLERGY/PREFERS/LOCATED_IN
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    merged_from: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_graph_edge", "src_id", "dst_id", "relation", unique=True),
        Index("idx_edge_src", "src_id"),
        Index("idx_edge_dst", "dst_id"),
    )
