"""认证路由（说明书 7.1）。

- POST /api/auth/register：公开注册（role 固定 advisor）
- POST /api/auth/login：签发 access token
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import Err
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.schemas.common import ok
from app.services.audit import add_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """公开注册，默认游客（tourist），也可选 advisor（旅行顾问）。supervisor 只能 seed。"""
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise Err.INVALID_PARAM.to_http()

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()
    await add_audit(db, action="register", actor_id=user.id, target=body.username)
    return ok(UserOut(id=user.id, username=user.username, role=user.role).model_dump())


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录，返回 access token（S19：单 token，24h）。"""
    user = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise Err.INVALID_PARAM.to_http()

    token, expires_in = create_access_token(user.id, user.role)
    await add_audit(db, action="login", actor_id=user.id, target=body.username)
    return ok(
        TokenOut(
            access_token=token,
            expires_in=expires_in,
            role=user.role,
        ).model_dump()
    )
