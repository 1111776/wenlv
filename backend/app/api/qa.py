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
    """智能问答：检索知识库 + 图记忆（长期记忆）→ LLM 基于资料回答，带引用来源。"""
    from app.agents.llm import build_system_prompt, get_llm
    from app.core.config import settings
    from app.memory.kb_retrieve import search_kb
    from app.memory.engine import retrieve as memory_retrieve

    query = body.message.strip()

    # 1. 检索知识库（混合检索 + rerank）
    hits = await search_kb(query, top_k=5)

    # 1.5 检索图记忆（长期记忆：用户历史约束/偏好/过敏）
    user_id = request.state.user.get("id")
    memories = []
    try:
        memories = await memory_retrieve(query, user_id=user_id, top_k=5)
    except Exception:
        memories = []  # 记忆检索失败不阻塞

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

    # 拼图记忆（用户个性化约束）
    memory_parts = []
    for m in memories:
        label = f"{m.get('type','')}:{m.get('key','')}"
        props = m.get("properties") or {}
        if props:
            label += f"（{props}）"
        memory_parts.append(f"- {label}")
    memory_context = "\n".join(memory_parts) if memory_parts else "（无历史记忆）"

    # 3. 让 LLM 基于资料回答
    llm = get_llm()
    if settings.llm_mode != "real" or not hits:
        # mock 或检索为空：给出提示，不硬编
        return ok({
            "answer": "抱歉，当前知识库中没有检索到相关内容。请换个问法试试，例如「老人去云南要注意什么」「迪士尼儿童票怎么买」。",
            "sources": [],
        })

    # 多轮对话：把历史上下文拼进 prompt，让 AI 能理解追问/指代
    history = body.history or []
    history_str = ""
    if history:
        # 只取最近几轮，避免 prompt 过长
        recent = history[-6:]
        history_str = "\n".join(
            f"{'用户' if h.get('role') == 'user' else '助手'}：{h.get('content', '')}"
            for h in recent
            if h.get("content")
        )

    prompt = (
        f"用户提问：{query}\n\n"
        + (f"【对话历史（理解追问/指代）】\n{history_str}\n\n" if history_str else "")
        + f"【用户的长期记忆（历史偏好/约束，回答时需考虑）】\n{memory_context}\n\n"
        f"以下是从文旅知识库检索到的参考资料：\n{context}\n\n"
        "请基于上述资料回答用户问题。要求：\n"
        "1) 直接、简洁、口语化，用中文回答；\n"
        "2) 只基于资料内容回答，资料里没有的不要编造；\n"
        "3) 每个关键信息后标注来源编号（如[1][2]）；\n"
        "4) 如果用户长期记忆里有相关约束（如过敏、偏好），请结合到回答中；\n"
        "5) 如果用户的问题是对上一句的追问或指代（如「那儿童呢」「价格呢」），结合对话历史理解。"
    )
    try:
        result = await llm.complete([
            {"role": "system", "content": build_system_prompt("qa", "你是文旅行程规划系统的智能问答助手，基于知识库资料和用户长期记忆回答用户问题。")},
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

    return ok({"answer": answer, "sources": sources, "memories": memory_parts})
