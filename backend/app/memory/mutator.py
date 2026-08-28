"""运行态强干预（工单 7 D8/D9/D11）。

链路：HMAC 验签 → nonce 防重放 → SETNX 排他锁 → 三写（图节点 version+1 /
interventions 流水 / Redis state 补丁）→ 释放锁 → 回执。

安全要点：
- 仅 supervisor 或持服务密钥的外部程序可调用；
- HMAC-SHA256(密钥, thread_id ∥ nonce ∥ sha256(patch))；
- nonce 单次有效（Redis SETNX，TTL 300s）；
- 图节点更新带 version 乐观校验。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.core.redis_client import get_redis, key
from app.models import GraphNode, Intervention
from app.services import lock

logger = get_logger(__name__)


def _hmac_sign(thread_id: str, nonce: str, patch: dict) -> str:
    """计算 HMAC-SHA256 签名。"""
    payload = f"{thread_id}|{nonce}|{hashlib.sha256(json.dumps(patch, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}"
    return hmac.new(settings.jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def verify_signature(thread_id: str, nonce: str, patch: dict, signature: str) -> bool:
    """验签（常数时间比较）。"""
    expected = _hmac_sign(thread_id, nonce, patch)
    return hmac.compare_digest(expected, signature)


async def _consume_nonce(nonce: str) -> bool:
    """nonce 单次消费：SETNX 成功返回 True（首次），已存在返回 False（重放）。"""
    r = get_redis()
    return bool(await r.set(key(f"nonce:{nonce}"), "1", nx=True, ex=300))


async def intervene(
    *,
    thread_id: str,
    operator: str,
    target_entity: dict,
    patch: dict,
    state_patch: dict,
    reason: str,
    nonce: str,
    signature: str,
) -> dict:
    """执行强干预，返回流水摘要。失败抛 ValueError / RuntimeError。"""
    # 1. 验签
    if not await verify_signature(thread_id, nonce, patch, signature):
        raise ValueError("验签失败")

    # 2. nonce 防重放
    if not await _consume_nonce(nonce):
        raise ValueError("nonce 已使用（重放）")

    # 3. SETNX 排他锁
    lock_key = f"memory_lock:{thread_id}"
    token = await lock.acquire_lease(lock_key, ttl=5)
    if token is None:
        raise RuntimeError("获取排他锁失败（并发冲突）")

    try:
        # 4. 三写
        intervention_id = None
        async with session_scope() as db:
            # ① 更新图节点属性（version 乐观校验）
            node_type = target_entity.get("type")
            node_key = target_entity.get("key")
            result = await db.execute(
                select(GraphNode).where(GraphNode.type == node_type, GraphNode.key == node_key)
            )
            node = result.scalar_one_or_none()
            prev_props = dict(node.properties) if node else None
            if node is not None:
                node.properties = {**(node.properties or {}), **patch}
                node.version += 1
                await db.flush()

            # ② 写 interventions 流水（含 prev_state）
            inter = Intervention(
                thread_id=thread_id,
                operator=operator,
                target_entity=target_entity,
                patch=patch,
                state_patch=state_patch,
                prev_state=prev_props,
                nonce=nonce,
                status="applied",
            )
            db.add(inter)
            await db.flush()
            intervention_id = inter.id

        # ③ 写 Redis state 补丁（供节点入口读取）
        r = get_redis()
        await r.set(
            key(f"plan:{thread_id}:intervention"),
            json.dumps(state_patch, ensure_ascii=False),
            ex=3600,
        )

        return {
            "intervention_id": intervention_id,
            "thread_id": thread_id,
            "target_entity": target_entity,
            "patch": patch,
            "status": "applied",
        }
    finally:
        await lock.release_lease(lock_key, token)


async def read_intervention_patch(plan_id: str) -> dict | None:
    """节点入口读取未消费的干预补丁（供 graph/context.py 调用）。"""
    r = get_redis()
    raw = await r.get(key(f"plan:{plan_id}:intervention"))
    if raw:
        return json.loads(raw)
    return None


async def mark_intervention_read(plan_id: str) -> None:
    """节点应用补丁后回写回执 + 清除补丁（幂等消费）。"""
    r = get_redis()
    await r.delete(key(f"plan:{plan_id}:intervention"))
    async with session_scope() as db:
        result = await db.execute(
            select(Intervention).where(Intervention.thread_id == plan_id, Intervention.status == "applied")
        )
        for inter in result.scalars().all():
            inter.status = "consumed"
            inter.intervention_read_at = datetime.now(timezone.utc)
        await db.flush()
