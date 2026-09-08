"""智能文旅问答路由（RAG 检索增强问答）。

- POST /api/qa：用户提问 → search_kb 混合检索知识库 → 拼 prompt → LLM 回答
  返回 {answer, sources}，sources 为引用的知识库来源。

复用已有的 search_kb（混合检索+rerank）、llm.complete、引用溯源，几乎零新代码。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.schemas.common import ok

router = APIRouter(prefix="/qa", tags=["qa"])


class QARequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict] = Field(default_factory=list)  # 可选多轮上下文


@router.post("")
async def ask_qa(body: QARequest, request: Request):
    """智能问答：检索知识库 → LLM 基于资料回答，带引用来源。"""
    from app.agents.llm import build_system_prompt, get_llm
    from app.core.config import settings
    from app.memory.kb_retrieve import search_kb

    query = body.message.strip()

    # 1. 检索知识库（混合检索 + rerank）
    hits = await search_kb(query, top_k=5)

    # 2. 拼检索到的资料（带编号，供引用溯源）
    context_parts = []
    ref_map: dict[str, str] = {}
    for i, h in enumerate(hits, start=1):
        txt = (h.get("chunk_text") or "").strip()
        if not txt:
            continue
        ref_id = f"[{i}]"
        ref_map[ref_id] = f"{h.get('doc_id', 'kb')}·{h.get('title', '')}"
        context_parts.append(f"{ref_id} 【{h.get('category','')}·{h.get('title','')}】{txt[:300]}")
    context = "\n\n".join(context_parts)

    # 3. 让 LLM 基于资料回答
    llm = get_llm()
    if settings.llm_mode != "real" or not hits:
        # mock 或检索为空：给出提示，不硬编
        return ok({
            "answer": "抱歉，当前知识库中没有检索到相关内容。请换个问法试试，例如「老人去云南要注意什么」「迪士尼儿童票怎么买」。",
            "sources": [],
        })

    prompt = (
        f"用户提问：{query}\n\n"
        f"以下是从文旅知识库检索到的参考资料：\n{context}\n\n"
        "请基于上述资料回答用户问题。要求：\n"
        "1) 直接、简洁、口语化，用中文回答；\n"
        "2) 只基于资料内容回答，资料里没有的不要编造；\n"
        "3) 每个关键信息后标注来源编号（如[1][2]）。"
    )
    try:
        result = await llm.complete([
            {"role": "system", "content": build_system_prompt("qa", "你是文旅行程规划系统的智能问答助手，基于知识库资料回答用户问题。")},
            {"role": "user", "content": prompt},
        ])
        answer = (result.text or "").strip() or "抱歉，我暂时无法回答这个问题。"
    except Exception as exc:
        answer = f"抱歉，回答问题出错：{exc}"

    # 4. 组装来源（去重，按编号）
    sources = []
    seen = set()
    for ref_id, label in sorted(ref_map.items(), key=lambda x: int(x[0].strip("[]"))):
        if label not in seen:
            seen.add(label)
            sources.append({"ref": ref_id, "source": label})

    return ok({"answer": answer, "sources": sources})
