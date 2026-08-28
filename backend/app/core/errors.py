"""统一错误码与异常（说明书第十一章 11.2 错误码表）。

约定：
- 业务错误抛 ``Err``（携带 code + http status + message）
- 全局异常处理器把它转成统一响应 ``{code, message, data}``

设计：``AppErr`` 是单个错误的 dataclass；``Err`` 是错误码容器
（所有业务错误实例），路由里用 ``Err.XXX`` 引用；``E`` 为别名。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class AppErr:
    """一个可抛出的业务错误。

    Attributes:
        code: 业务错误码（0 成功 / 40xxx 客户端 / 41xxx 鉴权 / 50xxx 服务端 / 60xxx 外部）。
        http: HTTP 状态码。
        message: 人类可读信息。
    """

    code: int
    http: int
    message: str

    def to_http(self) -> HTTPException:
        return HTTPException(
            status_code=self.http,
            detail={"code": self.code, "message": self.message},
        )

    def to_body(self) -> dict:
        return {"code": self.code, "message": self.message, "data": None}


class Err:
    """错误码容器（分组见下）。用法：``Err.NOT_FOUND.to_http()``。"""

    # 参数 / 客户端
    INVALID_PARAM = AppErr(40001, 400, "参数校验失败")
    BUDGET_OVER = AppErr(40002, 400, "预算超限提示")
    BAD_STATE = AppErr(40003, 409, "当前状态不允许该操作")
    NOT_FOUND = AppErr(40004, 404, "资源不存在")
    REVIEW_CONFLICT = AppErr(40005, 409, "审批已处理或抢占失败")
    TOO_FREQUENT = AppErr(40006, 429, "提交过于频繁")
    IDEM_CONFLICT = AppErr(40007, 400, "Idempotency-Key 冲突且内容不一致")
    PLAN_LOCKED = AppErr(40008, 409, "行程正在执行中")
    VERSION_CONFLICT = AppErr(40009, 409, "版本冲突，请重试")

    # 鉴权
    NOT_AUTHENTICATED = AppErr(41001, 401, "未登录或 Token 无效")
    TOKEN_EXPIRED = AppErr(41002, 401, "Token 已过期")
    FORBIDDEN = AppErr(41003, 403, "角色权限不足")

    # 服务端
    INTERNAL = AppErr(50001, 500, "内部错误")
    FILE_CORRUPT = AppErr(50002, 500, "状态文件损坏且无法回退")
    DB_ERROR = AppErr(50003, 500, "数据库错误")

    # 外部依赖
    LLM_UNAVAILABLE = AppErr(60001, 503, "LLM 不可用且降级失败")
    FETCH_FAILED = AppErr(60002, 502, "抓取失败")
    REDIS_UNAVAILABLE = AppErr(60003, 503, "Redis 不可用")


# 别名，兼容旧引用
E = Err
