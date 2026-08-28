"""统一响应结构（说明书 11.1）。

成功：``{code:0, message:"ok", data:{...}}``
失败：``{code:4xxx/5xxx/6xxx, message:"...", data:null}``
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 JSON 响应外壳。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


def ok(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应体。"""
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict:
    """构造失败响应体。"""
    return {"code": code, "message": message, "data": data}


class Page(BaseModel, Generic[T]):
    """分页结果。"""

    items: list[T]
    total: int
