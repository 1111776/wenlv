"""补全历史节点的 embedding（RAG 升级后，旧节点向量被置 NULL）。

扫描 embedding 为空的 graph_nodes，按 `type:key` 文本重新向量化并写回。
"""

import asyncio

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import GraphNode

logger = get_logger(__name__)


async def main():
    from app.memory.engine import _embed

    async with session_scope() as db:
        nodes = (
            await db.execute(select(GraphNode).where(GraphNode.embedding.is_(None)))
        ).scalars().all()

    if not nodes:
        print("没有需要补全的节点")
        return

    texts = [f"{n.type}:{n.key}" for n in nodes]
    embs = await _embed(texts)

    async with session_scope() as db:
        for i, n in enumerate(nodes):
            node = await db.get(GraphNode, n.id)
            if node is not None:
                node.embedding = embs[i]
        await db.flush()

    print(f"补全完成：{len(nodes)} 个节点")


if __name__ == "__main__":
    asyncio.run(main())
