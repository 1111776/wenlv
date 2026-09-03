"""文旅知识库向量化入库（RAG B 部分）。

- 扫描 docs/knowledge/ 下的 markdown/json 语料
- 按标题分块（300~500 字 + 50 字重叠）
- 批量 embed 后写入 document_chunks 表（幂等：按 doc_id+chunk_index upsert）
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import DocumentChunk

logger = get_logger(__name__)

CHUNK_SIZE = 400  # 每块目标字数
CHUNK_OVERLAP = 50  # 重叠字数

# 文件名关键词 → 中文类目
_CATEGORY_MAP = [
    ("food", "美食"),
    ("attraction", "景点"),
    ("ticket", "景区政策"),
    ("policy", "景区政策"),
    ("season", "季节"),
    ("transport", "交通"),
    ("hotel", "住宿"),
    ("住宿", "住宿"),
    ("交通", "交通"),
    ("季节", "季节"),
    ("政策", "景区政策"),
    ("景点", "景点"),
    ("美食", "美食"),
]


def _category_for(doc_id: str, category_map: dict[str, str] | None = None) -> str:
    """按文件名推断类目：优先显式映射，其次关键词。"""
    if category_map and doc_id in category_map:
        return category_map[doc_id]
    for kw, label in _CATEGORY_MAP:
        if kw in doc_id:
            return label
    return "其他"


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """把长文本切成有重叠的块，返回块列表。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _parse_md(path: Path) -> list[dict]:
    """解析 markdown 语料，按「## 标题」切成小节，返回 [{title, text}]。"""
    content = path.read_text(encoding="utf-8")
    doc_id = path.stem
    sections: list[dict] = []
    title = doc_id
    buf: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if buf:
                sections.append({"title": title, "text": "\n".join(buf).strip()})
                buf = []
            title = line[3:].strip()
        else:
            buf.append(line)
    if buf:
        sections.append({"title": title, "text": "\n".join(buf).strip()})
    return sections


def _parse_file(fp: Path) -> list[dict]:
    """解析单个文件为 [{title, text}]。"""
    if fp.suffix == ".md":
        return _parse_md(fp)
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [
                {"title": str(i.get("title", fp.stem)), "text": str(i.get("content", ""))}
                for i in data
            ]
        return [{"title": str(data.get("title", fp.stem)), "text": str(data.get("content", ""))}]
    except Exception:
        return []


def _collect_sections(base: Path, category_map: dict[str, str] | None = None) -> list[tuple[str, str, str, str]]:
    """扫描目录，分块，返回 [(doc_id, title, category, chunk_text)]。"""
    files = sorted(base.glob("*.md")) + sorted(base.glob("*.json"))
    result: list[tuple[str, str, str, str]] = []
    for fp in files:
        doc_id = fp.stem
        cat = _category_for(doc_id, category_map)
        for sec in _parse_file(fp):
            if not sec.get("text"):
                continue
            for chunk in chunk_text(sec["text"]):
                result.append((doc_id, sec["title"], cat, chunk))
    return result


async def ingest_dir(dir_path: str | Path, category_map: dict[str, str] | None = None) -> int:
    """扫描目录，分块 + 向量化 + 写入 document_chunks（幂等），返回 chunk 总数。"""
    from app.memory.engine import _embed

    base = Path(dir_path)
    if not base.exists():
        logger.warning("知识库目录不存在：%s", base)
        return 0

    all_chunks = _collect_sections(base, category_map)
    if not all_chunks:
        logger.warning("知识库目录无有效语料：%s", base)
        return 0

    texts = [c[3] for c in all_chunks]
    embs = await _embed(texts)

    async with session_scope() as db:
        # 按 doc_id 清掉旧的 chunk（幂等重建，避免残留）
        doc_ids = sorted({c[0] for c in all_chunks})
        from sqlalchemy import delete

        for did in doc_ids:
            await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == did))

        for i, (doc_id, title, cat, chunk) in enumerate(all_chunks):
            db.add(
                DocumentChunk(
                    doc_id=doc_id,
                    title=title,
                    category=cat,
                    chunk_index=i,
                    chunk_text=chunk,
                    embedding=embs[i],
                    meta={"source": doc_id},
                )
            )
        await db.flush()

    logger.info("知识库入库完成，共 %d 个 chunk", len(all_chunks))
    return len(all_chunks)
