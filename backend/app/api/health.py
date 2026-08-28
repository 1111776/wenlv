"""健康检查 + Prometheus 指标（说明书 §7.4 / §3.4）。"""

from __future__ import annotations

from fastapi import APIRouter
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from app.core.redis_client import get_redis

router = APIRouter(tags=["ops"])

# Prometheus 指标
REQUEST_COUNT = Counter("wenlv_http_requests_total", "HTTP 请求总数", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("wenlv_http_latency_seconds", "HTTP 请求延迟", ["method", "endpoint"])
PLAN_STATUS_GAUGE = None  # 行程状态计数可在 Worker 侧补充
RECOVER_COUNT = Counter("wenlv_recover_total", "恢复次数")
INJECTION_BLOCK_COUNT = Counter("wenlv_injection_block_total", "注入拦截次数")


@router.get("/health")
async def health():
    """存活探针。"""
    status = "ok"
    try:
        r = get_redis()
        await r.ping()
    except Exception:
        status = "degraded"
    return {"status": status}


@router.get("/metrics")
async def metrics():
    """Prometheus 抓取端点（内网）。"""
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")
