"""图记忆节点表（工单 7 D4：Labeled Property Graph）。

node_class 区分三类 Schema（D3）：
- chat_memory：对话偏好事实（用户过敏/偏好等）
- domain_wiki：领域实体（景点/城市/餐厅等）
- code_graph：系统内 Agent 节点与依赖
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    node_class: Mapped[str] = mapped_column(String(32), nullable=False)  # chat_memory/domain_wiki/code_graph
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # User/Attraction/Food/City/Constraint...
    key: Mapped[str] = mapped_column(String(128), nullable=False)  # 业务键
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column()  # user_scoped 节点归属
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list | None] = mapped_column(Vector(768))  # 语义向量（pgvector，维度=embedding_dim）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_graph_node", "node_class", "type", "key", unique=True),
    )
