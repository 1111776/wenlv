"""节点执行上下文：封装节点内需要的 DB / 文件 / 事件 / 状态推进逻辑。

8 个 Agent 节点都通过 ``NodeContext`` 读写数据库、更新 travel_plan.md、
发布事件，从而把「编排」与「业务」解耦。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import session_scope
from app.core.redis_client import get_redis, key
from app.models import AgentTask, BudgetRecord, ReviewRecord, TravelPlan
from app.models.agent_task import TASK_STATUS
from app.models.travel_plan import PLAN_STATUS, TERMINAL_STATUSES
from app.services.audit import add_audit
from app.services.events import build_event, build_progress, publish_plan_event
from app.services.workspace import PlanFileManager


class NodeContext:
    """一个节点执行期间的上下文，封装数据库/文件/事件的统一访问。

    用法：``async with NodeContext(plan_id) as ctx: ...``
    """

    def __init__(self, plan_id: uuid.UUID | str):
        self.plan_id = str(plan_id)
        self.file = PlanFileManager(plan_id)

    async def __aenter__(self) -> "NodeContext":
        self._scope = session_scope()
        self.db: AsyncSession = await self._scope.__aenter__()
        self.plan = await self._load_plan()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._scope.__aexit__(*exc)

    # ------------------------------------------------------------------ #
    # 数据读取
    # ------------------------------------------------------------------ #
    async def _load_plan(self) -> TravelPlan:
        plan = await self.db.get(TravelPlan, uuid.UUID(self.plan_id))
        if plan is None:
            raise RuntimeError(f"行程不存在：{self.plan_id}")
        return plan

    async def load_tasks(self) -> list[AgentTask]:
        result = await self.db.execute(
            select(AgentTask)
            .where(AgentTask.plan_id == uuid.UUID(self.plan_id))
            .order_by(AgentTask.order_index)
        )
        return list(result.scalars().all())

    async def tasks_as_dicts(self) -> list[dict]:
        """任务列表转 dict（用于写入 travel_plan.md 与 state）。"""
        return [
            {
                "order_index": t.order_index,
                "agent_type": t.agent_type,
                "title": (t.task_data or {}).get("title", t.agent_type),
                "status": t.status,
                "page_no": t.page_no,
            }
            for t in await self.load_tasks()
        ]

    def progress(self, tasks: list[AgentTask] | None = None) -> dict:
        """计算 (done, total)。"""
        if tasks is None:
            tasks = []
        done = sum(1 for t in tasks if t.status in (TASK_STATUS["COMPLETED"], TASK_STATUS["BLOCKED"]))
        return build_progress(done, len(tasks))

    # ------------------------------------------------------------------ #
    # 状态推进
    # ------------------------------------------------------------------ #
    async def set_status(self, status: str) -> None:
        """更新 DB 行程状态 + 写 Redis 状态缓存。"""
        self.plan.status = status
        await self.db.flush()
        await self._cache_status(status, self.plan.resume_from, self.plan.state_version)

    async def bump_version(self) -> int:
        """版本 +1 并落库，返回新版本（与文件 version 对账）。"""
        self.plan.state_version += 1
        await self.db.flush()
        return self.plan.state_version

    async def advance(
        self,
        *,
        status: str,
        resume_from: str | None,
        body: str,
        event: str,
        agent: str | None = None,
        progress: dict | None = None,
        hitl: dict | None = None,
    ) -> None:
        """统一推进：写 DB（状态+版本）→ 原子写文件 → 发布事件。

        顺序即说明书 4.3.3 的「同一 Worker 协程内顺序完成」。
        """
        self.plan.status = status
        self.plan.resume_from = resume_from
        version = await self.bump_version()
        await self.db.flush()

        self.file.write(
            body,
            status=status,
            resume_from=resume_from,
            version=version,
            plan_id=self.plan_id,
        )

        await self._cache_status(status, resume_from, version)
        await publish_plan_event(
            build_event(
                event=event,
                plan_id=self.plan_id,
                status=status,
                resume_from=resume_from,
                agent=agent,
                progress=progress,
            )
        )

    # ------------------------------------------------------------------ #
    # 文件正文便捷方法
    # ------------------------------------------------------------------ #
    async def build_body(self, tasks: list[AgentTask] | None = None, logs: list[str] | None = None, hitl: dict | None = None) -> str:
        if tasks is None:
            tasks = await self.load_tasks()
        return self.file.build_body(
            query=self.plan.query,
            preferences=self.plan.preferences,
            tasks=[self._task_dict(t) for t in tasks],
            logs=logs or [],
            hitl=hitl,
        )

    @staticmethod
    def _task_dict(t: AgentTask) -> dict:
        return {
            "order_index": t.order_index,
            "agent_type": t.agent_type,
            "title": (t.task_data or {}).get("title", t.agent_type),
            "status": t.status,
            "page_no": t.page_no,
        }

    # ------------------------------------------------------------------ #
    # Redis 状态缓存
    # ------------------------------------------------------------------ #
    async def _cache_status(self, status: str, resume_from: str | None, version: int) -> None:
        try:
            r = get_redis()
            progress = self.progress(await self.load_tasks())
            payload = {
                "plan_id": self.plan_id,
                "status": status,
                "resume_from": resume_from,
                "version": version,
                "progress": progress,
            }
            import json

            await r.set(
                key(f"plan:{self.plan_id}:status"),
                json.dumps(payload, ensure_ascii=False),
                ex=settings.status_cache_ttl,
            )
        except Exception:
            # 缓存写失败不阻断主流程；status 接口 miss 会回源 DB
            pass


# 供节点使用的常量重导出
PLAN_STATUS = PLAN_STATUS
TASK_STATUS = TASK_STATUS
TERMINAL_STATUSES = TERMINAL_STATUSES
