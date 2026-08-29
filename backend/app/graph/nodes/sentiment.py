"""Sentiment Agent：舆情评估（说明书 §5.1 第 4 节点 / §4.3 串行依赖）。

对 Web Research 收集的真实 POI 做风险识别：
- 用规则引擎（负面关键词）对 POI 名称/类型/地址做打分；
- 识别严重负面 → high_risk=true（真实场景可扩展接点评/舆情 API）；
- 高德真实数据下通常无负面，sentiment_risk=False 属正常。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.llm import build_system_prompt, get_llm
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask
from app.models.agent_task import TASK_STATUS

logger = get_logger(__name__)

# 负面/风险关键词（POI 名称或类型命中即标记）
_SEVERE_KEYWORDS = ["差评", "强制购物", "诱导消费", "投诉", "恶劣", "欺骗", "宰客", "黑店"]


def _score(text: str) -> float:
    """本地规则打分：命中负面词越多分越低（0~1）。"""
    hits = sum(1 for kw in _SEVERE_KEYWORDS if kw in text)
    return max(0.0, 1.0 - 0.3 * hits)


async def sentiment_node(state: TravelState) -> dict:
    """对真实 POI 做舆情评估，返回 sentiment_risk 标志。"""
    plan_id = state["plan_id"]

    # 读 web_research 收集的真实 POI
    async with session_scope() as db:
        tasks = (
            await db.execute(
                select(AgentTask).where(
                    AgentTask.plan_id == uuid.UUID(plan_id),
                    AgentTask.agent_type == "web_research",
                )
            )
        ).scalars().all()

    high_risk: list[dict] = []
    for t in tasks:
        if not t.result:
            continue
        for p in t.result.get("pois", []):
            text = f"{p.get('name','')} {p.get('type','')} {p.get('address','')}"
            score = _score(text)
            if score < settings.sentiment_min_score:
                high_risk.append({"name": p.get("name"), "score": score, "category": p.get("type", "")})

    # 舆情风险：真实高德数据无差评，默认 False；hitl_demo 时演示触发
    severe_found = len(high_risk) > 0
    if settings.hitl_demo and not severe_found:
        # 演示模式：人为注入一个舆情风险，触发 HITL 审核
        severe_found = True
        high_risk.append({"name": "(演示)示例景点", "score": 0.1, "category": "演示舆情风险"})

    try:
        llm = get_llm()
        await llm.complete([{"role": "system", "content": build_system_prompt("sentiment", "舆情评估")}])
    except Exception as exc:
        logger.warning("Sentiment LLM 失败，本地规则降级：%s", exc)

    async with session_scope() as db:
        from sqlalchemy import delete

        await db.execute(
            delete(AgentTask).where(
                AgentTask.plan_id == uuid.UUID(plan_id),
                AgentTask.agent_type == "sentiment",
            )
        )
        db.add(
            AgentTask(
                plan_id=uuid.UUID(plan_id),
                agent_type="sentiment",
                order_index=100,
                status=TASK_STATUS["COMPLETED"],
                task_data={"title": "舆情评估"},
                result={"high_risk": high_risk, "sentiment_risk": severe_found},
            )
        )
        await db.flush()

    return {
        "sentiment_risk": severe_found,
        "completed_nodes": state.get("completed_nodes", []) + ["sentiment"],
    }
