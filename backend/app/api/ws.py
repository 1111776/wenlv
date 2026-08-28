"""WebSocket 实时推送（说明书 §7.5）。

- WS /ws/plans/{id}?token=<jwt>
- 服务端订阅 Redis Pub/Sub channel，转发事件给客户端；
- 每 15s 发 heartbeat。
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.core.redis_client import get_redis, key
from app.core.security import decode_token
from app.services.events import CHANNEL_PREFIX

logger = get_logger(__name__)

router = APIRouter(tags=["ws"])


@router.websocket("/ws/plans/{plan_id}")
async def ws_plans(websocket: WebSocket, plan_id: uuid.UUID, token: str = Query(default="")):
    """订阅行程实时事件。"""
    # 鉴权
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    # 可选：行程可见性校验（这里简化，MVP 演示用）
    await websocket.accept()
    r = get_redis()
    channel = key(f"{CHANNEL_PREFIX}:{plan_id}")
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(15)
            try:
                await websocket.send_json({"event": "heartbeat", "plan_id": str(plan_id)})
            except Exception:
                break

    hb_task = asyncio.create_task(heartbeat())

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                await websocket.send_text(message["data"])
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        hb_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
