"""崩溃恢复（说明书 §13.4 / 场景 B / S12）。

Worker 启动时调用 ``recover_all()``：
1. 扫描 DB 中 running/recovering 的行程；
2. **心跳判定**：只有心跳已失效（真崩溃）才恢复，仍在被其他 worker 持有的跳过；
3. 置 recovering；
4. 校验文件 checksum（Workspace 已封装），失败回退快照；
5. 依据文件 resume_from 跳过已完成任务，重新入队续跑。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models import TravelPlan
from app.models.travel_plan import PLAN_STATUS
from app.services import lock, queue
from app.services.audit import add_audit
from app.services.workspace import PlanFileManager, WorkspaceError

logger = get_logger(__name__)


async def recover_all() -> list[str]:
    """恢复所有未完成行程，返回已恢复的 plan_id 列表。"""
    recovered: list[str] = []

    async with session_scope() as db:
        result = await db.execute(
            select(TravelPlan).where(
                TravelPlan.status.in_([PLAN_STATUS["RUNNING"], PLAN_STATUS["RECOVERING"]])
            )
        )
        plans = list(result.scalars().all())

    for plan in plans:
        plan_id = str(plan.id)

        # 心跳判定：仍有心跳说明被存活 worker 持有，跳过（避免多 worker 误恢复）
        if await lock.has_heartbeat(plan_id):
            logger.info("行程 %s 心跳存活，跳过恢复（仍在处理中）", plan_id)
            continue

        try:
            # 校验文件（失败自动回退快照）
            fm = PlanFileManager(plan_id)
            header, _ = fm.load()
            resume_from = header.get("resume_from")

            # 置 recovering 并重新入队
            async with session_scope() as db:
                p = await db.get(TravelPlan, uuid.UUID(plan_id))
                if p is not None:
                    p.status = PLAN_STATUS["RECOVERING"]
                    await db.flush()
                await add_audit(db, action="recover", plan_id=uuid.UUID(plan_id), detail={"resume_from": resume_from})

            await queue.publish_request(plan_id)
            recovered.append(plan_id)
            logger.info("已恢复行程 %s resume_from=%s", plan_id, resume_from)
        except WorkspaceError as exc:
            # 文件损坏且无快照 → failed（说明书 13.4）
            logger.error("恢复失败，行程置 failed：%s", exc)
            async with session_scope() as db:
                p = await db.get(TravelPlan, uuid.UUID(plan_id))
                if p is not None:
                    p.status = PLAN_STATUS["FAILED"]
                    await db.flush()
        except Exception as exc:
            logger.error("恢复行程 %s 异常：%s", plan_id, exc)

    return recovered
