"""数据库：异步 SQLAlchemy 引擎 + 会话工厂。

PostgreSQL 为「对外权威状态源」（说明书 S2）。使用 asyncpg 驱动、
异步会话，与 FastAPI / Worker 的 async 编程模型一致。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


# 创建异步引擎（连接池在 asyncpg 内管理）
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # 取连接前先 ping，避免拿到已断开的连接
)

# 会话工厂：Worker 与 API 各自 ``async with`` 使用
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 后仍可访问已加载属性
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个独立会话。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Worker / 脚本使用的会话上下文管理器，自动提交/回滚。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """建表 + 种子数据（幂等，可反复调用）。

    说明：MVP 用 ``create_all`` 快速建表，等价于说明书六章的六张表；
    生产迁移可切换为 Alembic（此处不引入迁移历史，聚焦“跑通”）。
    """
    # 延迟导入，确保所有模型都已注册到 Base.metadata
    from app.models import (  # noqa: F401
        AgentTask,
        AuditLog,
        BudgetRecord,
        GraphEdge,
        GraphNode,
        Intervention,
        MemoryEvent,
        ReviewRecord,
        TravelPlan,
        User,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 建表完成后写入预置账号（S20 seed）
    from app.services.seed import seed_users

    async with session_scope() as db:
        await seed_users(db)
