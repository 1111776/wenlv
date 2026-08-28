"""FastAPI 应用入口（说明书第四章 API 网关层）。

组装：路由、鉴权中间件、统一异常处理、启动时建表 + 种子 + 清理孤儿临时文件。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, health, memory, plans, reviews, ws
from app.core.config import settings
from app.core.database import init_db
from app.core.errors import E
from app.core.logging import get_logger, setup_logging
from app.core.security import _current_user
from app.schemas.common import fail
from app.services.atomic_file import cleanup_orphan_tmp

logger = get_logger(__name__)

# 无需鉴权的路径前缀
_PUBLIC_PREFIXES = ("/api/auth", "/health", "/metrics", "/ws")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动：初始化日志、建表、种子、清理孤儿临时文件。"""
    setup_logging()
    await init_db()
    removed = cleanup_orphan_tmp(settings.workspace_root)
    logger.info("启动完成，清理孤儿临时文件 %d 个", removed)
    yield
    # 关闭 Redis 连接池
    from app.core.redis_client import close_redis

    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（前端开发用；生产由网关统一处理）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# 鉴权中间件：把解析出的用户挂到 request.state.user（公开路径跳过）
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith(_PUBLIC_PREFIXES):
        return await call_next(request)
    try:
        request.state.user = await _current_user(request)
    except StarletteHTTPException as exc:
        # 鉴权失败：直接返回 401/403（转成统一结构）
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": 41001, "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=fail(detail.get("code", 41001), detail.get("message", "未登录")))
    return await call_next(request)


# --------------------------------------------------------------------------- #
# 统一异常处理（转成 {code, message, data}）
# --------------------------------------------------------------------------- #
@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: Request, exc: StarletteHTTPException):
    # FastAPI 抛出的 HTTPException 已携带 {"code","message"} detail
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=fail(exc.detail["code"], exc.detail["message"]))
    return JSONResponse(status_code=exc.status_code, content=fail(50001, str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content=fail(40001, "参数校验失败"))


@app.exception_handler(Exception)
async def generic_exc_handler(request: Request, exc: Exception):
    logger.exception("未处理异常：%s", exc)
    return JSONResponse(status_code=500, content=fail(E.INTERNAL.code, E.INTERNAL.message))


# --------------------------------------------------------------------------- #
# 路由注册
# --------------------------------------------------------------------------- #
app.include_router(auth.router, prefix="/api")
app.include_router(plans.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(health.router)
app.include_router(ws.router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "docs": "/docs"}
