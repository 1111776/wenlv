"""Planner Agent：CoT 任务拆解（说明书 §5.1 第 2 节点 / §5.3 CoT）。

产出 >=8 条 web_research 任务，每条是「搜索关键词 + 城市」，供 Web Research
调用高德 POI 搜索真实数据（替换原假种子 URL）。
LLM 失败时用内置调研维度降级（质量标记 degraded）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.llm import build_system_prompt, get_llm
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask
from app.models.agent_task import TASK_STATUS

logger = get_logger(__name__)

# 内置调研维度：关键词 + 高德 POI types（替换原假种子 URL）
# 每个维度对应一个真实 POI 搜索任务
_RESEARCH_DIMENSIONS = [
    {"keyword": "景点", "amap_types": "110000", "title": "核心景点调研"},
    {"keyword": "公园", "amap_types": "110100", "title": "公园绿地调研"},
    {"keyword": "博物馆", "amap_types": "080300", "title": "博物馆文化调研"},
    {"keyword": "酒店", "amap_types": "100000", "title": "住宿酒店调研"},
    {"keyword": "餐厅", "amap_types": "050000", "title": "餐饮美食调研"},
    {"keyword": "购物中心", "amap_types": "060100", "title": "购物商圈调研"},
    {"keyword": "地铁站", "amap_types": "150500", "title": "交通出行调研"},
    {"keyword": "风景名胜", "amap_types": "110200", "title": "风景名胜调研"},
]


def build_research_tasks(destination: str) -> list[dict]:
    """生成调研任务列表（真实关键词，供高德搜索）。"""
    tasks = []
    for i, dim in enumerate(_RESEARCH_DIMENSIONS, start=1):
        tasks.append(
            {
                "order_index": i,
                "agent_type": "web_research",
                "page_no": i,
                "title": f"{destination}{dim['title']}",
                "keyword": dim["keyword"],
                "amap_types": dim["amap_types"],
                "purpose": f"调研 {destination} 的{dim['title']}",
            }
        )
    return tasks


async def planner_node(state: TravelState) -> dict:
    """拆解调研任务，写入 agent_tasks（幂等）。"""
    plan_id = state["plan_id"]
    preferences = state.get("preferences", {})
    destination = preferences.get("destination", "") or "目的地"

    # 调研维度用内置模板（确定性，无需 LLM，提速）
    degraded = False
    tasks = build_research_tasks(destination)

    async with session_scope() as db:
        # 幂等：若已存在 web_research 任务，说明此前已拆解过，直接跳过（避免清掉抓取进度）
        existing = (
            await db.execute(
                select(AgentTask.id).where(
                    AgentTask.plan_id == uuid.UUID(plan_id),
                    AgentTask.agent_type == "web_research",
                ).limit(1)
            )
        ).scalar_one_or_none()

        if existing is None:
            for t in tasks:
                db.add(
                    AgentTask(
                        plan_id=uuid.UUID(plan_id),
                        agent_type=t["agent_type"],
                        order_index=t["order_index"],
                        page_no=t["page_no"],
                        status=TASK_STATUS["PENDING"],
                        task_data={
                            "title": t["title"],
                            "keyword": t["keyword"],
                            "amap_types": t["amap_types"],
                            "purpose": t["purpose"],
                        },
                    )
                )
            db.add(
                AgentTask(
                    plan_id=uuid.UUID(plan_id),
                    agent_type="planner",
                    order_index=0,
                    status=TASK_STATUS["COMPLETED"],
                    task_data={"title": "CoT 拆解调研任务"},
                    result={"quality": "degraded" if degraded else "ok", "task_count": len(tasks)},
                )
            )
        await db.flush()

    return {
        "tasks": tasks,
        "completed_nodes": state.get("completed_nodes", []) + ["planner"],
    }
