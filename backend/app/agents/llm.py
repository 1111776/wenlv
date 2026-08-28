"""LLMProvider 抽象与 Mock 实现（说明书 §5.3 / S13）。

- ``LLMProvider`` 协议：``complete(messages, *, schema) -> LLMResult``
- ``MockLLMProvider``：按节点返回稳定夹具，保证压测与单测确定性；
  签名与真实 LLM 完全一致，演示时可无缝切换（S13）。
- ``get_llm()`` 工厂：根据 ``WENLV_LLM_MODE`` 返回 mock 或真实实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResult:
    """一次 LLM 调用的统一返回。

    Attributes:
        text: 原始文本输出。
        structured: 若传入 schema，这里是按 schema 校验后的结构化对象。
        model: 命中的模型名（mock 时为 "mock-llm"）。
    """

    text: str
    structured: Any = None
    model: str = "mock-llm"


class LLMProvider(Protocol):
    """LLM 调用协议，真实实现只需实现这一个方法。"""

    async def complete(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
    ) -> LLMResult:
        """发送 messages，返回统一结果。

        Args:
            messages: OpenAI 风格 ``[{"role", "content"}, ...]``。
            schema: 可选 JSON Schema，要求模型返回结构化 JSON。
        """
        ...


# --------------------------------------------------------------------------- #
# Mock 实现：按 agent_type 返回确定夹具
# --------------------------------------------------------------------------- #

# 每个 agent 的 mock 文本输出（确定性，便于断言）
_MOCK_TEXTS: dict[str, str] = {
    "intake": (
        "解析偏好：目的地=云南，天数=7，预算=15000，"
        "出行人=2大1小，兴趣=自然风光/少购物"
    ),
    "planner": "已按 CoT 拆解为 10 个网页调研子任务",
    "web_research": "已抓取本页内容并完成清洗",
    "sentiment": "舆情评估完成，识别风险标签",
    "itinerary": "按日编排行程完成",
    "budget": "分项预算汇总完成",
    "report": "行程单与预算报告生成完成",
}


@dataclass
class MockLLMProvider:
    """确定性 Mock：不调用任何外部 API。

    ``complete`` 会按消息里标记的 ``agent_type`` 返回对应文本，
    若调用方传入 ``schema``，则额外返回一个最小合法 JSON 占位，
    保证结构化解析链路可被单测覆盖。
    """

    model: str = "mock-llm"

    async def complete(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
    ) -> LLMResult:
        agent_type = _extract_agent_type(messages)
        text = _MOCK_TEXTS.get(agent_type, "mock 输出")
        structured = None
        if schema is not None:
            structured = _minimal_for_schema(schema)
        logger.debug("mock llm complete agent=%s schema=%s", agent_type, schema is not None)
        return LLMResult(text=text, structured=structured, model=self.model)


def _extract_agent_type(messages: list[dict]) -> str:
    """从 system 消息里提取 ``agent_type: xxx`` 标记（约定）。"""
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str) and "agent_type:" in content:
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("agent_type:"):
                    return line.split(":", 1)[1].strip()
    return "unknown"


def _minimal_for_schema(schema: dict) -> Any:
    """给一个「最小合法」JSON，满足 JSON Schema 的 required 字段。

    仅用于 Mock 打通结构化解析链路；真实 LLM 会返回真实内容。
    """
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    obj: dict[str, Any] = {}
    for key in required:
        prop = properties.get(key, {})
        ptype = prop.get("type", "string")
        if ptype == "array":
            obj[key] = []
        elif ptype == "object":
            obj[key] = {}
        elif ptype == "number" or ptype == "integer":
            obj[key] = 0
        elif ptype == "boolean":
            obj[key] = False
        else:
            obj[key] = ""
    return obj


# --------------------------------------------------------------------------- #
# 真实 OpenAI 兼容实现（阿里云百炼 / OpenAI / 通义等）
# --------------------------------------------------------------------------- #


@dataclass
class OpenAICompatProvider:
    """OpenAI 兼容的 LLM 实现（chat/completions）。

    支持阿里云百炼 compatible-mode、OpenAI 官方、及任何 OpenAI 兼容端点。
    结构化输出用 ``response_format={"type":"json_object"}`` 要求模型返回 JSON。
    """

    api_key: str
    base_url: str
    model: str

    async def complete(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
    ) -> LLMResult:
        import httpx

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # 百炼要求：用 json_object 时 messages 里必须出现 "json" 字样
        if schema is not None:
            messages = list(messages) + [
                {"role": "user", "content": "请严格按照 JSON 格式输出结果。"}
            ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "") or ""

        structured = None
        if schema is not None and content:
            import json as _json

            try:
                structured = _json.loads(content)
            except _json.JSONDecodeError:
                # 尝试提取 JSON 片段
                import re

                m = re.search(r"\{.*\}", content, re.S)
                if m:
                    try:
                        structured = _json.loads(m.group(0))
                    except _json.JSONDecodeError:
                        structured = None

        return LLMResult(
            text=content,
            structured=structured,
            model=data.get("model", self.model),
        )


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #


def get_llm() -> LLMProvider:
    """按配置返回 LLM 实现。

    ``llm_mode=real`` 且配置了 api_key/base_url/model 时返回真实实现，
    否则回落到 Mock（保证无 key 时也能跑通）。
    """
    if settings.llm_mode == "real" and settings.llm_api_key and settings.llm_model:
        if settings.llm_base_url:
            return OpenAICompatProvider(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
            )
        # 无 base_url 时默认 OpenAI 官方
        return OpenAICompatProvider(
            api_key=settings.llm_api_key,
            base_url="https://api.openai.com/v1",
            model=settings.llm_model,
        )
    return MockLLMProvider()


def build_system_prompt(agent_type: str, extra: str = "") -> str:
    """构造带 agent_type 标记的 system 提示词（供 Mock 识别 + 真实模型路由）。"""
    base = f"agent_type: {agent_type}\n"
    base += "你是文旅行程规划系统中的一个 Agent 节点。"
    if extra:
        base += f"\n{extra}"
    return base
