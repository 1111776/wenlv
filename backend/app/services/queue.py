"""Redis Streams 异步队列封装（说明书第九章）。

- ``publish_request``：新行程入队；
- ``publish_resume``：HITL 通过后续跑；
- ``consume``：Worker 用 consumer group 阻塞读；
- ``ack``：消息完成确认（HITL 挂起也要 ack，避免 PEL 无限重放）；
- ``claim_pending``：崩溃后自认领（XAUTOCLAIM）。
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis, key

logger = get_logger(__name__)


async def _ensure_group(stream_key: str) -> None:
    """确保 consumer group 存在（幂等）。"""
    r = get_redis()
    try:
        await r.xgroup_create(stream_key, settings.consumer_group, id="0", mkstream=True)
    except Exception as exc:
        # BUSYGROUP 表示已存在，忽略；其余向上抛
        if "BUSYGROUP" not in str(exc):
            raise


async def publish_request(plan_id: uuid.UUID | str) -> str:
    """新计划入队，返回消息 ID。"""
    r = get_redis()
    stream_key = key(settings.request_stream)
    await _ensure_group(stream_key)
    msg_id = await r.xadd(stream_key, {"plan_id": str(plan_id)}, maxlen=settings.stream_maxlen, approximate=True)
    return msg_id


async def publish_resume(plan_id: uuid.UUID | str, reason: str = "approved") -> str:
    """HITL 通过后重新入队续跑。"""
    r = get_redis()
    stream_key = key(settings.resume_stream)
    await _ensure_group(stream_key)
    msg_id = await r.xadd(
        stream_key,
        {"plan_id": str(plan_id), "reason": reason},
        maxlen=settings.stream_maxlen,
        approximate=True,
    )
    return msg_id


async def consume(consumer_name: str, count: int = 1, block_ms: int | None = None) -> list[tuple[str, dict]]:
    """阻塞读，返回 [(message_id, fields_dict), ...]。"""
    r = get_redis()
    block_ms = block_ms if block_ms is not None else settings.stream_block_ms
    streams = {
        key(settings.request_stream): ">",
        key(settings.resume_stream): ">",
    }
    for s in streams:
        await _ensure_group(s)

    result = await r.xreadgroup(
        settings.consumer_group,
        consumer_name,
        streams,
        count=count,
        block=block_ms,
    )
    messages: list[tuple[str, dict]] = []
    for _stream, entries in result:
        for msg_id, fields in entries:
            messages.append((msg_id, fields))
    return messages


async def ack(stream_key: str, message_id: str) -> None:
    """确认消息。"""
    r = get_redis()
    await r.xack(key(stream_key), settings.consumer_group, message_id)


async def claim_pending(consumer_name: str) -> int:
    """启动时自认领自己 PEL 里超时未确认的消息（崩溃接管）。"""
    r = get_redis()
    min_idle = settings.claim_min_idle_ms
    total = 0
    for s in (settings.request_stream, settings.resume_stream):
        stream_key = key(s)
        try:
            claimed = await r.xautoclaim(
                stream_key,
                settings.consumer_group,
                consumer_name,
                min_idle_time=min_idle,
            )
            # xautoclaim 返回 [next_cursor, [(id, fields), ...], deleted_ids]
            entries = claimed[1] if len(claimed) > 1 else []
            total += len(entries)
        except Exception as exc:
            logger.warning("xautoclaim 失败 stream=%s err=%s", s, exc)
    return total


async def stream_length(stream: str) -> int:
    """队列长度（监控用）。"""
    r = get_redis()
    return await r.xlen(key(stream))
