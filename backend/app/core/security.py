"""安全：密码哈希 + JWT + RBAC 依赖。

- bcrypt 哈希密码（S20）
- PyJWT 签发/校验 HS256 token（S19：单 access token，TTL 24h）
- ``require_role`` FastAPI 依赖实现 RBAC（S17/S18：advisor / supervisor）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.errors import Err

# --------------------------------------------------------------------------- #
# 密码哈希
# --------------------------------------------------------------------------- #


def hash_password(plain: str) -> str:
    """bcrypt 哈希，返回可直接入库的字符串。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #

_bearer = HTTPBearer(auto_error=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    """签发 access token，返回 (token, 过期秒数)。

    payload 含 ``sub``（用户 id）、``role``、``jti``（可选黑名单用）、``exp``。
    """
    expires_in = settings.jwt_expire_seconds
    now = _now()
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_token(token: str) -> dict:
    """校验并解析 token，返回 payload；非法/过期抛 Err.INVALID_TOKEN / EXPIRED。"""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise Err.TOKEN_EXPIRED.to_http()
    except jwt.InvalidTokenError:
        raise Err.INVALID_TOKEN.to_http()


async def _current_user(request: Request) -> dict:
    """从 ``Authorization: Bearer`` 解析当前用户，返回 {id, role}。"""
    cred: HTTPAuthorizationCredentials | None = await _bearer(request)
    if cred is None:
        raise Err.NOT_AUTHENTICATED.to_http()
    payload = decode_token(cred.credentials)
    try:
        return {"id": uuid.UUID(payload["sub"]), "role": payload["role"]}
    except (KeyError, ValueError):
        raise Err.INVALID_TOKEN.to_http()


def require_role(*roles: str):
    """RBAC 依赖工厂：要求当前用户属于 ``roles`` 之一。

    用法：``deps=[Depends(require_role("advisor"))]``。
    越权统一返回 41003。
    """

    async def _dep(request: Request) -> dict:
        user = await _current_user(request)
        if user["role"] not in roles:
            raise Err.FORBIDDEN.to_http()
        return user

    return _dep


async def require_auth(request: Request) -> dict:
    """仅要求已登录，不限制角色。"""
    return await _current_user(request)
