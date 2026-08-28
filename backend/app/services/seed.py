"""种子数据：预置演示账号（S20）。

- advisor_demo   : 旅行顾问（创建行程）
- supervisor_demo: 主管（审批）
密码均为 wenlv123（仅开发/验收用）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import User

SEED_USERS = [
    {"username": "advisor_demo", "role": "advisor"},
    {"username": "supervisor_demo", "role": "supervisor"},
]
SEED_PASSWORD = "wenlv123"


async def seed_users(db: AsyncSession) -> None:
    """幂等写入预置账号：已存在则跳过。"""
    for u in SEED_USERS:
        existing = await db.execute(select(User).where(User.username == u["username"]))
        if existing.scalar_one_or_none() is None:
            db.add(User(username=u["username"], password_hash=hash_password(SEED_PASSWORD), role=u["role"]))
    await db.flush()
