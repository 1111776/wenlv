"""事件发布（WS 广播辅助，说明书 §7.5 / 第八章）。

Worker 每节点推进时 ``publish`` 一个 JSON 事件到 Redis Pub/Sub，
API 进程订阅后扇出给对应 plan 的 WebSocket 客户端。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.core.redis_client import get_redis, key

logger = get_logger(__name__)

CHANNEL_PREFIX = "events:plan"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(
    *,
    event: str,
    plan_id: uuid.UUID | str,
    status: str,
    resume_from: str | None = None,
    agent: str | None = None,
    progress: dict | None = None,
) -> dict:
    """构造统一事件结构（与说明书 §7.5 一致）。"""
    return {
        "event": event,
        "plan_id": str(plan_id),
        "status": status,
        "resume_from": resume_from,
        "agent": agent,
        "progress": progress or {},
        "ts": _now_iso(),
    }


async def publish_plan_event(event: dict) -> None:
    """发布事件到 Redis Pub/Sub（channel: events:plan:{id}）。"""
    try:
        r = get_redis()
        plan_id = event["plan_id"]
        await r.publish(key(f"{CHANNEL_PREFIX}:{plan_id}"), json.dumps(event, ensure_ascii=False))
    except Exception as exc:  # 事件发布失败不影响主流程
        logger.warning("事件发布失败：%s", exc)


def build_progress(done: int, total: int) -> dict:
    """进度摘要。"""
    return {"done": done, "total": max(total, 0)}
