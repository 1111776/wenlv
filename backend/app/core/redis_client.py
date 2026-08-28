"""Redis 客户端封装。

统一 Redis key 前缀（说明书第八章），并收敛所有对象（连接池、
Streams、锁、缓存、心跳、Checkpointer 热状态）的访问入口。
"""

from __future__ import annotations

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings

# 全局连接池（进程内单例）。decode_responses 让读写自动 str<->bytes。
_pool: aioredis.ConnectionPool | None = None
_redis: Redis | None = None


def get_redis() -> Redis:
    """返回全局异步 Redis 客户端（懒初始化）。"""
    global _pool, _redis
    if _redis is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        _redis = Redis(connection_pool=_pool)
    return _redis


def key(name: str) -> str:
    """拼接带前缀的 Redis key，例如 ``wenlv:plan:{id}:status``。"""
    return f"{settings.redis_prefix}:{name}"


async def close_redis() -> None:
    """进程退出时关闭连接池。"""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
