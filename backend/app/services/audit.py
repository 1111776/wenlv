"""审计日志写入（说明书 6.7 / 场景 C 验收）。"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import AuditLog

logger = get_logger(__name__)


async def add_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    target: str | None = None,
    detail: dict | None = None,
) -> None:
    """写入一条审计日志（幂等无返回值，失败只记日志不抛）。"""
    try:
        db.add(
            AuditLog(
                actor_id=actor_id,
                plan_id=plan_id,
                action=action,
                target=target,
                detail=detail,
            )
        )
        await db.flush()
    except Exception as exc:  # 审计失败不应阻断业务
        logger.warning("审计日志写入失败：%s", exc)
