"""LangGraph 共享状态（TravelState TypedDict，说明书 §5.1/5.2）。

注意：state 只放**可序列化**的数据（会进 Checkpointer）。
数据库 session、Redis 连接等不可序列化对象绝不入 state；
节点内部自行用 ``session_scope()`` 打开。
"""

from __future__ import annotations

from typing import TypedDict


class TravelState(TypedDict, total=False):
    """图执行过程中节点间流转的共享状态。

    字段说明：
    - plan_id: 行程 UUID（字符串，作为 Checkpointer 的 thread_id）
    - query: 用户原始自然语言需求
    - preferences: Intake 解析出的结构化偏好
    - tasks: Planner 拆解的调研任务列表（含 web_research 每页）
    - resume_from: 当前断点指针（与文件 YAML 头同步）
    - hitl: HITL 触发上下文（reason / detail）
    - completed_nodes: 已完成节点名列表（用于恢复跳过）
    - status: 行程状态（与 DB 同步的冗余，便于图内判断）
    - over_budget_ratio: 预算超支比例
    - night_risk: 是否含高危夜行
    - sentiment_risk: 是否含严重舆情风险
    """

    plan_id: str
    query: str
    preferences: dict
    tasks: list[dict]
    resume_from: str
    hitl: dict | None
    hitl_approved: bool  # 审批通过后为 True，条件边据此直接放行到 report
    completed_nodes: list[str]
    status: str
    over_budget_ratio: float
    total_budget: float  # 预算总金额（用于超阈值审核）
    night_risk: bool
    sentiment_risk: bool
