"""行程路由（说明书 7.2）。

核心：POST /api/plans 只入队即返回（QPS 200 关键）；
GET /api/plans/{id}/status 为压测主接口（走 Redis 缓存）。
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import Err
from app.core.redis_client import get_redis, key
from app.models import AgentTask, BudgetRecord, TravelPlan
from app.models.agent_task import TASK_STATUS
from app.models.travel_plan import PLAN_STATUS, TERMINAL_STATUSES
from app.schemas.common import ok
from app.schemas.plan import (
    PlanCreateRequest,
    PlanDetailOut,
    PlanFileOut,
    PlanListItem,
    PlanListOut,
    PlanStatusOut,
    ReportOut,
)
from app.services import lock, queue
from app.services.audit import add_audit
from app.services.workspace import PlanFileManager

router = APIRouter(prefix="/plans", tags=["plans"])


async def _progress(db: AsyncSession, plan_id: uuid.UUID) -> dict:
    """计算 (done, total)。"""
    total = (
        await db.execute(
            select(func.count()).select_from(AgentTask).where(AgentTask.plan_id == plan_id)
        )
    ).scalar_one()
    done = (
        await db.execute(
            select(func.count())
            .select_from(AgentTask)
            .where(
                AgentTask.plan_id == plan_id,
                AgentTask.status.in_([TASK_STATUS["COMPLETED"], TASK_STATUS["BLOCKED"]]),
            )
        )
    ).scalar_one()
    return {"done": done or 0, "total": total or 0}


@router.post("", status_code=201)
async def create_plan(
    body: PlanCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """创建行程：校验 → 防抖 → 写 DB(planning) → 入队 → 立即返回 plan_id。"""
    user = request.state.user
    user_id = user["id"]

    # 提交防抖（S26）：同一用户 5 秒内重复提交（无幂等键）直接拒绝
    if not idempotency_key:
        if not await lock.acquire_submit_lock(user_id):
            raise Err.TOO_FREQUENT.to_http()

    # 幂等：同一 Idempotency-Key 返回第一次的 plan_id（S26）
    if idempotency_key:
        existing = (
            await db.execute(
                select(TravelPlan).where(
                    TravelPlan.user_id == user_id,
                    TravelPlan.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return ok({"plan_id": str(existing.id), "status": existing.status}, message="已存在")

    plan = TravelPlan(
        user_id=user_id,
        query=body.query,
        status=PLAN_STATUS["PLANNING"],
        workspace_path=f"workspace/{uuid.uuid4()}",
        idempotency_key=idempotency_key,
        budget_limit=body.budget_limit,
    )
    db.add(plan)
    await db.flush()

    # 可选结构化字段写入 preferences（Intake 会覆盖/补全）
    if body.destination or body.days or body.party or body.tags:
        plan.preferences = {
            "destination": body.destination,
            "days": body.days,
            "budget_limit": body.budget_limit,
            "party": body.party.model_dump() if body.party else None,
            "tags": body.tags,
        }

    await add_audit(db, action="plan_create", actor_id=user_id, plan_id=plan.id, target=body.query[:128])

    # 关键：入队前先 commit，确保 Worker 消费时 DB 里已有该行程（避免读写竞态）
    await db.commit()

    # 入队（同步接口只做入队，即 QPS 能到 200 的关键）
    await queue.publish_request(plan.id)

    return ok({"plan_id": str(plan.id), "status": PLAN_STATUS["PLANNING"]})


@router.get("")
async def list_plans(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """行程列表（advisor 仅自己；supervisor 可按 status 筛）。"""
    user = request.state.user
    stmt = select(TravelPlan)
    if user["role"] == "advisor":
        stmt = stmt.where(TravelPlan.user_id == user["id"])
    if status:
        stmt = stmt.where(TravelPlan.status == status)
    stmt = stmt.order_by(TravelPlan.created_at.desc())

    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    plans = (
        await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()

    items = []
    for p in plans:
        progress = await _progress(db, p.id)
        items.append(
            PlanListItem(
                id=p.id,
                title=p.title,
                status=p.status,
                rejected=p.rejected,
                resume_from=p.resume_from,
                progress=progress,
                created_at=p.created_at,
            ).model_dump(mode="json")
        )
    return ok(PlanListOut(items=items, total=total).model_dump(mode="json"))


@router.get("/{plan_id}")
async def get_plan(plan_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """行程详情。"""
    plan = await db.get(TravelPlan, plan_id)
    if plan is None:
        raise Err.NOT_FOUND.to_http()
    _check_visibility(plan, request.state.user)
    progress = await _progress(db, plan.id)
    return ok(
        PlanDetailOut(
            id=plan.id,
            title=plan.title,
            status=plan.status,
            rejected=plan.rejected,
            query=plan.query,
            preferences=plan.preferences,
            budget_limit=plan.budget_limit,
            total_budget=plan.total_budget,
            resume_from=plan.resume_from,
            state_version=plan.state_version,
            progress=progress,
            created_at=plan.created_at,
        ).model_dump(mode="json")
    )


@router.get("/{plan_id}/status")
async def get_status(plan_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """【压测主接口】轻量状态查询，优先 Redis 缓存。"""
    # 先读 Redis 缓存
    try:
        r = get_redis()
        cached = await r.get(key(f"plan:{plan_id}:status"))
        if cached:
            return ok(json.loads(cached))
    except Exception:
        pass  # Redis 不可用回源 DB

    plan = await db.get(TravelPlan, plan_id)
    if plan is None:
        raise Err.NOT_FOUND.to_http()
    _check_visibility(plan, request.state.user)
    progress = await _progress(db, plan.id)
    return ok(
        PlanStatusOut(
            plan_id=plan.id,
            status=plan.status,
            resume_from=plan.resume_from,
            version=plan.state_version,
            progress=progress,
        ).model_dump(mode="json")
    )


@router.get("/{plan_id}/plan-file")
async def get_plan_file(plan_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """返回 travel_plan.md 原文。"""
    plan = await db.get(TravelPlan, plan_id)
    if plan is None:
        raise Err.NOT_FOUND.to_http()
    _check_visibility(plan, request.state.user)

    fm = PlanFileManager(plan_id)
    try:
        header, body = fm.load()
        markdown = fm.path.read_text(encoding="utf-8")
    except Exception:
        markdown = ""
        header = {"version": plan.state_version}
    return ok(PlanFileOut(markdown=markdown, version=header.get("version", plan.state_version)).model_dump())


@router.get("/{plan_id}/report")
async def get_report(plan_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """获取报告（仅 completed 且非 rejected）。"""
    plan = await db.get(TravelPlan, plan_id)
    if plan is None:
        raise Err.NOT_FOUND.to_http()
    _check_visibility(plan, request.state.user)
    if plan.status != PLAN_STATUS["COMPLETED"] or plan.rejected:
        raise Err.NOT_FOUND.to_http()

    budget_items = (
        await db.execute(select(BudgetRecord).where(BudgetRecord.plan_id == plan_id))
    ).scalars().all()

    fm = PlanFileManager(plan_id)
    report_path = fm.dir / "report.md"
    markdown = report_path.read_text(encoding="utf-8") if report_path.exists() else ""

    from app.schemas.plan import BudgetItemOut

    return ok(
        ReportOut(
            markdown=markdown,
            budget=[
                BudgetItemOut(category=b.category, item=b.item, amount=float(b.amount))
                for b in budget_items
            ],
        ).model_dump()
    )


@router.get("/{plan_id}/agents")
async def get_agents(plan_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """Agent 执行流程状态（前端流程可视化）。

    返回 8 个 agent 的固定顺序 + 各自状态（pending/running/completed/waiting），
    以及 web_research 的逐页任务列表。
    """
    plan = await db.get(TravelPlan, plan_id)
    if plan is None:
        raise Err.NOT_FOUND.to_http()
    _check_visibility(plan, request.state.user)

    # 查所有 agent_tasks
    tasks = (
        await db.execute(
            select(AgentTask)
            .where(AgentTask.plan_id == plan_id)
            .order_by(AgentTask.order_index)
        )
    ).scalars().all()

    from app.models import ReviewRecord

    review = (
        await db.execute(
            select(ReviewRecord).where(ReviewRecord.plan_id == plan_id).order_by(ReviewRecord.created_at.desc()).limit(1)
        )
    ).scalars().first()

    def task_status(agent_type: str) -> str:
        """根据 agent_type 汇总任务状态。"""
        related = [t for t in tasks if t.agent_type == agent_type]
        if not related:
            return "pending"
        statuses = {t.status for t in related}
        if TASK_STATUS["RUNNING"] in statuses:
            return "running"
        if TASK_STATUS["PENDING"] in statuses and TASK_STATUS["COMPLETED"] in statuses:
            return "running"  # 部分完成，仍在进行
        if all(s in (TASK_STATUS["COMPLETED"], TASK_STATUS["BLOCKED"]) for s in statuses):
            return "completed"
        if all(s == TASK_STATUS["PENDING"] for s in statuses):
            return "pending"
        return "running"

    # intake 状态：看 preferences 是否已解析
    intake_status = "completed" if plan.preferences else "pending"

    # 8 个 agent 固定顺序
    agents = [
        {"key": "intake", "name": "偏好解析", "status": intake_status, "icon": "🔍"},
        {"key": "planner", "name": "任务拆解", "status": task_status("planner"), "icon": "📋"},
        {"key": "web_research", "name": "网页调研", "status": task_status("web_research"), "icon": "🌐"},
        {"key": "sentiment", "name": "舆情评估", "status": task_status("sentiment"), "icon": "💬"},
        {"key": "itinerary", "name": "日程编排", "status": task_status("itinerary"), "icon": "🗓️"},
        {"key": "budget", "name": "预算计算", "status": task_status("budget"), "icon": "💰"},
        {"key": "human_review", "name": "人工审核", "status": _review_status(plan, review), "icon": "👤"},
        {"key": "report", "name": "报告生成", "status": task_status("report"), "icon": "📄"},
    ]

    # 网页任务列表
    web_tasks = [
        {
            "order": t.order_index,
            "page_no": t.page_no,
            "title": (t.task_data or {}).get("title", ""),
            "url": (t.task_data or {}).get("url", ""),
            "status": t.status,
            "result": t.result,
        }
        for t in tasks
        if t.agent_type == "web_research"
    ]

    # 行程计划（Itinerary 输出），供前端时间线可视化
    itinerary_task = next((t for t in tasks if t.agent_type == "itinerary"), None)
    itinerary = itinerary_task.result if itinerary_task and itinerary_task.result else None

    return ok(
        {
            "plan_id": str(plan.id),
            "status": plan.status,
            "resume_from": plan.resume_from,
            "agents": agents,
            "tasks": web_tasks,
            "itinerary": itinerary,
            "preferences": plan.preferences,
            "budget_limit": float(plan.budget_limit) if plan.budget_limit else None,
            "total_budget": float(plan.total_budget) if plan.total_budget else None,
            "rejected": plan.rejected,
        }
    )


def _review_status(plan: TravelPlan, review) -> str:
    """人工审核节点状态。"""
    if plan.status == PLAN_STATUS["SUSPENDED"]:
        if review and review.status == "reviewing":
            return "reviewing"
        return "waiting"  # 等待审核
    if review and review.status == "approved":
        return "completed"
    if plan.status == PLAN_STATUS["COMPLETED"] and not review:
        return "skipped"  # 未触发 HITL
    if plan.status == PLAN_STATUS["COMPLETED"] and review and review.status == "rejected":
        return "rejected"
    return "pending"


@router.post("/{plan_id}/cancel")
async def cancel_plan(plan_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """取消非终态行程（advisor 本人或 supervisor）。"""
    plan = await db.get(TravelPlan, plan_id)
    if plan is None:
        raise Err.NOT_FOUND.to_http()
    user = request.state.user
    if user["role"] == "advisor" and plan.user_id != user["id"]:
        raise Err.FORBIDDEN.to_http()
    if plan.status in TERMINAL_STATUSES:
        raise Err.BAD_STATE.to_http()

    plan.status = PLAN_STATUS["CANCELLED"]
    await db.flush()
    await add_audit(db, action="cancel", actor_id=user["id"], plan_id=plan.id)
    return ok({"plan_id": str(plan.id), "status": PLAN_STATUS["CANCELLED"]})


def _check_visibility(plan: TravelPlan, user: dict) -> None:
    """advisor 只能看自己的行程；supervisor 可看全部。"""
    if user["role"] == "advisor" and plan.user_id != user["id"]:
        raise Err.FORBIDDEN.to_http()
