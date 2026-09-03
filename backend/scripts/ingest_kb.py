"""知识库入库脚本：扫描语料目录，分块 + 向量化 + 写入 document_chunks。

用法（本地）：
    cd backend && python scripts/ingest_kb.py [语料目录]

用法（容器内，目录已挂载到 /app/knowledge）：
    python scripts/ingest_kb.py /app/knowledge
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def main() -> None:
    from app.memory.vectorstore import ingest_dir

    if len(sys.argv) > 1:
        kb_dir = Path(sys.argv[1])
    else:
        # 默认：项目根 docs/knowledge
        base = Path(__file__).resolve().parents[2]
        kb_dir = base / "docs" / "knowledge"
    n = await ingest_dir(kb_dir)
    print(f"知识库入库完成：{n} 个 chunk（目录 {kb_dir}）")


if __name__ == "__main__":
    asyncio.run(main())
