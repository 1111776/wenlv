"""Worker 入口（说明书第九章 / §4.3）。

职责：
- 消费 Redis Streams（request/resume 两个流）；
- 单 Worker 同时只跑 1 个 plan（行程锁）；
- 每节点推进时写 DB + 文件 + 事件（编排层负责）；
- SIGTERM 优雅退出（停止领取新消息、当前页抓完再退出）；
- 启动时 recover_all() + claim_pending()（崩溃接管）。

运行：``python -m worker`` 或 ``python worker.py``
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import uuid

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import get_logger, setup_logging
from app.services import lock, queue
from app.services.orchestrator import run_plan
from app.services.recovery import recover_all
from app.services.review_timeout import expire_stale_reviews

logger = get_logger("worker")

# 优雅退出标志
_stopping = False


def _consumer_name() -> str:
    """consumer 名：worker-{hostname}（说明书 9.2）。"""
    host = socket.gethostname()
    return f"worker-{host}"


def _install_signal_handlers() -> None:
    """SIGTERM/SIGINT → 置停止标志（优雅退出，说明书 3.2）。"""

    def _handler(signum, frame):
        global _stopping
        logger.info("收到信号 %s，开始优雅退出", signum)
        _stopping = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


async def _process_one(plan_id: str, *, hitl_approved: bool = False) -> None:
    """处理单个行程：加行程锁 → 跑图（心跳续期）→ 释放锁。"""
    plan_lock_token = await lock.acquire_plan_lock(plan_id)
    if plan_lock_token is None:
        # 已有 worker 在处理（或锁被占），稍后重试
        logger.warning("行程锁占用，跳过 plan=%s", plan_id)
        return

    # 心跳：处理期间每 1s 续期，崩溃后由 recover_all 依据心跳判定真死
    hb_task = asyncio.create_task(_heartbeat_loop(plan_id))

    try:
        await run_plan(plan_id, hitl_approved=hitl_approved)
    except Exception as exc:
        logger.exception("行程执行失败 plan=%s：%s", plan_id, exc)
    finally:
        hb_task.cancel()
        await lock.clear_heartbeat(plan_id)
        await lock.release_plan_lock(plan_id, plan_lock_token)


async def _heartbeat_loop(plan_id: str) -> None:
    """心跳续期协程：每 1s 刷新一次 plan 心跳（TTL=heartbeat_ttl）。"""
    try:
        while True:
            await lock.set_heartbeat(plan_id)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return


async def _review_timeout_loop() -> None:
    """审批超时扫描协程：每 60s 检查一次超时未处理的审核。"""
    try:
        while not _stopping:
            try:
                n = await expire_stale_reviews()
                if n > 0:
                    logger.info("审批超时扫描：自动驳回 %d 条", n)
            except Exception as exc:
                logger.warning("审批超时扫描异常：%s", exc)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        return


async def _main() -> None:
    setup_logging()
    await init_db()

    # 启动恢复：崩溃接管
    recovered = await recover_all()
    claimed = await queue.claim_pending(_consumer_name())
    logger.info("启动恢复完成：recover=%d claimed=%d", len(recovered), claimed)

    consumer = _consumer_name()
    logger.info("Worker 启动：consumer=%s", consumer)

    # 启动审批超时扫描后台协程
    timeout_task = asyncio.create_task(_review_timeout_loop())

    try:
        await _consume_loop(consumer)
    finally:
        timeout_task.cancel()


async def _consume_loop(consumer: str) -> None:
    """消费主循环（从 _main 抽出，便于 finally 清理后台任务）。"""
    while not _stopping:
        try:
            messages = await queue.consume(consumer, count=1)
        except Exception as exc:
            logger.warning("消费失败，稍后重试：%s", exc)
            await asyncio.sleep(1)
            continue

        if not messages:
            continue  # 阻塞超时，无消息

        for msg_id, fields in messages:
            plan_id = fields.get("plan_id")
            if not plan_id:
                # 无法识别，直接 ack 避免 PEL 堆积
                await queue.ack(settings.request_stream, msg_id)
                continue

            reason = fields.get("reason", "")
            hitl_approved = reason == "approved"

            logger.info("处理消息 plan=%s hitl_approved=%s", plan_id, hitl_approved)
            try:
                await _process_one(plan_id, hitl_approved=hitl_approved)
            except Exception as exc:
                logger.exception("处理消息异常 plan=%s：%s", plan_id, exc)

            # 无论成功/挂起/异常，都 ack（HITL 挂起也要 ack，避免 PEL 无限重放）
            # 判断消息来自哪个流：resume 消息含 reason
            stream = settings.resume_stream if reason else settings.request_stream
            await queue.ack(stream, msg_id)

    logger.info("Worker 已停止")


if __name__ == "__main__":
    _install_signal_handlers()
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，退出")
