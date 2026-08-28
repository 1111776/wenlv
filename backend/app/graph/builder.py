"""LangGraph 图构建（说明书 §5.2）。

拓扑（固定 8 节点 + 1 条件边）：

    intake → planner → web_research → sentiment → itinerary → budget
                                                              │
                              ┌─────────── route_after_budget ─┴──────┐
                              │ hitl                                   │ report
                              ▼                                        ▼
                        human_review  ──(审批通过后续跑)──▶ report → END
                              │
                        reject/timeout
                              ▼
                            END

说明：
- 由于挂起后需「释放 Worker、审批通过后重新入队续跑」（S6/S27），
  human_review 节点直接 END，不阻塞等待；审批通过后由 Worker 以
  ``resume_from=report`` 重新启动图，直接走 report 节点。
- 因此图采用「一次 invoke 跑完一轮」的模型；恢复与续跑由 Worker 层
  依据 state 里的 completed_nodes / resume_from 跳过已完成节点。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.graph.state import TravelState
from app.graph.nodes import (
    budget_node,
    human_review_node,
    intake_node,
    itinerary_node,
    planner_node,
    report_node,
    sentiment_node,
    web_research_node,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def route_after_budget(state: TravelState) -> str:
    """条件边：判定是否需要 HITL（说明书 §5.2）。

    审批通过后续跑（hitl_approved=True）时直接放行到 report，不再二次挂起。
    """
    if state.get("hitl_approved"):
        return "report"

    over_ratio = state.get("over_budget_ratio", 0.0)
    night_risk = state.get("night_risk", False)
    sentiment_risk = state.get("sentiment_risk", False)

    if over_ratio > settings.budget_over_ratio:
        return "hitl"
    if night_risk:
        return "hitl"
    if sentiment_risk:
        return "hitl"
    return "report"


def build_graph() -> StateGraph:
    """构建并返回已编译的 StateGraph。"""
    g = StateGraph(TravelState)

    # 注册节点
    g.add_node("intake", intake_node)
    g.add_node("planner", planner_node)
    g.add_node("web_research", web_research_node)
    g.add_node("sentiment", sentiment_node)
    g.add_node("itinerary", itinerary_node)
    g.add_node("budget", budget_node)
    g.add_node("human_review", human_review_node)
    g.add_node("report", report_node)

    # 普通边
    g.add_edge(START, "intake")
    g.add_edge("intake", "planner")
    g.add_edge("planner", "web_research")
    g.add_edge("web_research", "sentiment")
    g.add_edge("sentiment", "itinerary")
    g.add_edge("itinerary", "budget")

    # 条件边
    g.add_conditional_edges(
        "budget",
        route_after_budget,
        {"hitl": "human_review", "report": "report"},
    )

    # human_review 与 report 均为终点（挂起或完成都结束本次 invoke）
    g.add_edge("human_review", END)
    g.add_edge("report", END)

    return g.compile()


# 编译一次，进程内复用
graph = build_graph()
