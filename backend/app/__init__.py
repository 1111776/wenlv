"""文旅多 Agent 行程规划系统 — 后端应用包。

目录职责（与《需求与技术方案说明书》第四章一致）：
- core/      配置、数据库、Redis、安全、错误码、日志
- models/    数据库 ORM（六张表）
- schemas/   请求/响应 Pydantic 模型
- agents/    8 个 Agent 的实现
- graph/     LangGraph 编排层（StateGraph + 条件边）
- services/  基础设施服务（原子写、注入检测、队列、恢复等）
- api/       路由层（auth / plans / reviews / ws / health）
"""
