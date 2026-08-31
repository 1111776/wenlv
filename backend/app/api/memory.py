"""记忆与强干预 API（工单 7 §2.2/§2.3）。

- POST /api/memory/intervene：强干预（supervisor，HMAC + nonce）
- POST /api/memory/intervene/{id}/rollback：回滚（图属性）
- GET  /api/memory/graph：子图查询
- GET  /api/memory/search：记忆检索
- GET  /api/memory/interventions：干预历史
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import Err
from app.core.logging import get_logger
from app.memory import engine, mutator
from app.models import GraphEdge, GraphNode, Intervention
from app.schemas.common import ok
from app.services.audit import add_audit

logger = get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/intervene")
async def intervene(
    request: Request,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """强干预：仅 supervisor。body 需含 thread_id/target_entity/patch/state_patch/reason/nonce/signature。"""
    user = request.state.user
    if user["role"] != "supervisor":
        raise Err.FORBIDDEN.to_http()

    try:
        result = await mutator.intervene(
            thread_id=body["thread_id"],
            operator=user["role"],  # 简化：用角色名，实际应存 username
            target_entity=body["target_entity"],
            patch=body["patch"],
            state_patch=body.get("state_patch", {}),
            reason=body.get("reason", ""),
            nonce=body["nonce"],
            signature=body["signature"],
        )
    except ValueError as exc:
        raise Err.FORBIDDEN.to_http() if "验签" in str(exc) else Err.REVIEW_CONFLICT.to_http()
    except RuntimeError as exc:
        raise Err.PLAN_LOCKED.to_http()

    await add_audit(
        db,
        action="state_override",
        actor_id=user["id"],
        plan_id=uuid.UUID(body["thread_id"]) if _is_uuid(body["thread_id"]) else None,
        target=f"{body['target_entity'].get('type')}:{body['target_entity'].get('key')}",
        detail={"patch": body["patch"], "reason": body.get("reason")},
    )
    return ok(result)


@router.post("/intervene/{intervention_id}/rollback")
async def rollback(intervention_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """回滚干预：恢复图属性 + 清除 state 补丁（按流水 prev_state 恢复）。"""
    if request.state.user["role"] != "supervisor":
        raise Err.FORBIDDEN.to_http()

    try:
        result = await mutator.rollback_intervention(intervention_id)
    except ValueError:
        raise Err.NOT_FOUND.to_http()

    await add_audit(db, action="state_rollback", actor_id=request.state.user["id"], detail={"intervention_id": intervention_id})
    return ok(result)


@router.get("/graph")
async def graph(
    request: Request,
    db: AsyncSession = Depends(get_db),
    plan_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
):
    """子图查询：返回节点 + 边列表。"""
    stmt = select(GraphNode)
    if user_id:
        stmt = stmt.where(GraphNode.owner_user_id == uuid.UUID(user_id))
    nodes = (await db.execute(stmt)).scalars().all()

    edges = (await db.execute(select(GraphEdge))).scalars().all()

    node_dicts = [
        {
            "id": n.id,
            "node_class": n.node_class,
            "type": n.type,
            "key": n.key,
            "properties": n.properties,
            "version": n.version,
        }
        for n in nodes
    ]
    edge_dicts = [
        {"src_id": e.src_id, "dst_id": e.dst_id, "relation": e.relation, "confidence": e.confidence}
        for e in edges
    ]
    return ok({"nodes": node_dicts, "edges": edge_dicts})


@router.get("/search")
async def search(
    request: Request,
    db: AsyncSession = Depends(get_db),
    q: str = Query(..., min_length=1),
):
    """记忆检索（顾问/游客限本人域）。"""
    user = request.state.user
    results = await engine.retrieve(q, user_id=user["id"] if user["role"] in ("advisor", "tourist") else None)
    return ok({"items": results})


@router.get("/interventions")
async def interventions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    thread_id: str | None = Query(default=None),
):
    """干预历史流水。"""
    stmt = select(Intervention).order_by(Intervention.created_at.desc())
    if thread_id:
        stmt = stmt.where(Intervention.thread_id == thread_id)
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        {
            "id": r.id,
            "thread_id": r.thread_id,
            "operator": r.operator,
            "target_entity": r.target_entity,
            "patch": r.patch,
            "state_patch": r.state_patch,
            "status": r.status,
            "intervention_read_at": r.intervention_read_at.isoformat() if r.intervention_read_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return ok({"items": items})


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False
