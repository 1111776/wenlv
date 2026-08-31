"""路由公共依赖与辅助。"""

from __future__ import annotations

import uuid

from fastapi import Depends, Request

from app.core.errors import Err
from app.core.security import require_role
from app.schemas.common import ok

# 预构造的 RBAC 依赖（避免每处重复写字符串）
# 游客(tourist) 与旅行顾问(advisor) 权限等价：都能创建/查看/取消自己的行程，不能审核
require_advisor = require_role("advisor", "tourist")
require_supervisor = require_role("supervisor")


async def get_current_user(request: Request) -> dict:
    """已登录用户（任意角色）。"""
    from app.core.security import _current_user

    return await _current_user(request)
