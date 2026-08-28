"""Redis 分布式锁与原子抢占（说明书 13.5 / S28）。

原则：**锁降冲突，DB 条件更新保正确**。

- 审核抢占用 Lua CAS（Suspended→Reviewing 原子转换）；
- 会话租约锁用 ``SET NX PX``（value=持有者 token，释放校验防误删）；
- 行程级互斥锁（同 plan 不并行跑图）。
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.core.redis_client import get_redis, key

# --------------------------------------------------------------------------- #
# 审核抢占（Lua CAS）
# --------------------------------------------------------------------------- #

# 原子地：只有当 review 状态为 pending 时，才置为 reviewing 并写入 reviewer。
_CLAIM_LUA = """
local status = redis.call('HGET', KEYS[1], 'status')
if status == false then
  -- hash 不存在（如 Redis 重启丢失），DB 才是正确性权威，这里放行交给 DB 兜底
  redis.call('HSET', KEYS[1], 'status', 'reviewing', 'reviewer_id', ARGV[1], 'claimed_at', ARGV[2])
  return 1
end
if status == 'pending' then
  redis.call('HSET', KEYS[1], 'status', 'reviewing', 'reviewer_id', ARGV[1], 'claimed_at', ARGV[2])
  return 1
end
return 0
"""


async def init_review_lock(review_id: uuid.UUID | str) -> None:
    """挂起时初始化审核锁 hash（status=pending），供 claim 的 CAS 使用。"""
    r = get_redis()
    hkey = key(f"review:{review_id}")
    await r.hsetnx(hkey, "status", "pending")


async def claim_review(review_id: uuid.UUID | str, reviewer_id: uuid.UUID | str) -> bool:
    """抢占审核任务：pending → reviewing（原子）。成功返回 True。

    注意：Redis 只是性能优化与第二道闸，正确性由 DB 条件更新兜底（S28）。
    """
    r = get_redis()
    hkey = key(f"review:{review_id}")
    claimed_at = _now_iso()
    result = await r.eval(
        _CLAIM_LUA,
        1,
        hkey,
        str(reviewer_id),
        claimed_at,
    )
    return bool(int(result))


async def reset_review_lock(
    review_id: uuid.UUID | str,
    *,
    status: str,
    reviewer_id: str | None = None,
) -> None:
    """强制把 Redis 审核锁 hash 重置为指定状态（修复 DB/Redis 不一致）。"""
    r = get_redis()
    hkey = key(f"review:{review_id}")
    mapping = {"status": status, "reviewer_id": reviewer_id or "", "claimed_at": _now_iso()}
    await r.hset(hkey, mapping=mapping)


# --------------------------------------------------------------------------- #
# 租约锁（SET NX PX）
# --------------------------------------------------------------------------- #

_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


async def acquire_lease(lock_key: str, ttl: int | None = None) -> str | None:
    """获取租约锁，返回 token（失败返回 None）。"""
    r = get_redis()
    token = uuid.uuid4().hex
    ttl = ttl or settings.review_lock_ttl
    ok = await r.set(key(lock_key), token, nx=True, ex=ttl)
    return token if ok else None


async def renew_lease(lock_key: str, token: str, ttl: int | None = None) -> bool:
    """续期（仅持有者可续）。"""
    r = get_redis()
    ttl = ttl or settings.review_lock_ttl
    result = await r.eval(
        """
        if redis.call('get', KEYS[1]) == ARGV[1] then
          return redis.call('expire', KEYS[1], ARGV[2])
        end
        return 0
        """,
        1,
        key(lock_key),
        token,
        ttl,
    )
    return bool(int(result))


async def release_lease(lock_key: str, token: str) -> bool:
    """释放租约（仅持有者可释放，防止误删他人锁）。"""
    r = get_redis()
    result = await r.eval(_RELEASE_LUA, 1, key(lock_key), token)
    return bool(int(result))


# --------------------------------------------------------------------------- #
# 行程级互斥锁（同 plan 不并行跑图）
# --------------------------------------------------------------------------- #


async def acquire_plan_lock(plan_id: uuid.UUID | str) -> str | None:
    """获取行程级锁（30s，Worker 心跳续期）。"""
    return await acquire_lease(f"lock:plan:{plan_id}", settings.plan_lock_ttl)


# --------------------------------------------------------------------------- #
# 提交防抖占位锁（SET NX，无持有者概念，过期自动释放）
# --------------------------------------------------------------------------- #


async def acquire_submit_lock(user_id: uuid.UUID | str) -> bool:
    """提交防抖：同一用户 5 秒内只允许提交一次（S26）。

    返回 True 表示抢到锁、允许提交；False 表示 5 秒内已有提交、拒绝。
    """
    r = get_redis()
    ttl = settings.submit_lock_ttl
    result = await r.set(key(f"submit_lock:{user_id}"), "1", nx=True, ex=ttl)
    return bool(result)


# --------------------------------------------------------------------------- #
# Worker 心跳
# --------------------------------------------------------------------------- #


async def set_heartbeat(plan_id: uuid.UUID | str) -> None:
    """设置/续期行程心跳（TTL 由 heartbeat_ttl 控制）。"""
    r = get_redis()
    await r.set(key(f"plan:{plan_id}:heartbeat"), "1", ex=settings.heartbeat_ttl)


async def has_heartbeat(plan_id: uuid.UUID | str) -> bool:
    """检查行程心跳是否存活（True=有 worker 在持有）。"""
    r = get_redis()
    return bool(await r.exists(key(f"plan:{plan_id}:heartbeat")))


async def clear_heartbeat(plan_id: uuid.UUID | str) -> None:
    """清除心跳（worker 完成/异常退出时）。"""
    r = get_redis()
    await r.delete(key(f"plan:{plan_id}:heartbeat"))


async def release_plan_lock(plan_id: uuid.UUID | str, token: str) -> bool:
    return await release_lease(f"lock:plan:{plan_id}", token)


async def renew_plan_lock(plan_id: uuid.UUID | str, token: str) -> bool:
    return await renew_lease(f"lock:plan:{plan_id}", token, settings.plan_lock_ttl)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
