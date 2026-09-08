"""经典线路模板路由。

- GET  /api/routes        ：模板列表
- GET  /api/routes/{id}   ：模板详情
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import Err
from app.models import RouteTemplate
from app.schemas.common import ok

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("")
async def list_routes(request: Request, db: AsyncSession = Depends(get_db)):
    """经典线路模板列表。"""
    rows = (await db.execute(select(RouteTemplate).order_by(RouteTemplate.id))).scalars().all()
    items = [
        {
            "id": r.id,
            "name": r.name,
            "destination": r.destination,
            "days": r.days,
            "tags": r.tags,
            "suitable_for": r.suitable_for,
            "budget_ref": r.budget_ref,
            "description": r.description,
        }
        for r in rows
    ]
    return ok({"items": items, "total": len(items)})


@router.get("/{route_id}")
async def get_route(route_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """经典线路模板详情（含每日行程 daily_plan）。"""
    r = await db.get(RouteTemplate, route_id)
    if r is None:
        raise Err.NOT_FOUND.to_http()
    return ok(
        {
            "id": r.id,
            "name": r.name,
            "destination": r.destination,
            "days": r.days,
            "tags": r.tags,
            "suitable_for": r.suitable_for,
            "budget_ref": r.budget_ref,
            "description": r.description,
            "daily_plan": r.daily_plan,
        }
    )
