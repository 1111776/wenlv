"""轻量压测脚本：验证 QPS / P95 / 错误率（无需 Locust，纯 asyncio + httpx）。

口径（说明书 §3.1）：以 status 查询为主，测同步接口的 QPS 和延迟。
用法：
    python deploy/loadtest.py [并发数] [持续时间秒]
    python deploy/loadtest.py 20 10   # 20 并发跑 10 秒
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
import uuid

import httpx

BASE = "http://localhost:8001"


async def main() -> None:
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    # 登录拿 token
    async with httpx.AsyncClient(base_url=BASE, timeout=10, trust_env=False, limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)) as client:
        login = await client.post(
            "/api/auth/login",
            json={"username": "advisor_demo", "password": "wenlv123"},
        )
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 创建一个 plan 作为 status 查询目标
        plan = await client.post(
            "/api/plans",
            json={"query": "压测行程", "budget_limit": 30000},
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
        )
        plan_id = plan.json()["data"]["plan_id"]

    latencies: list[float] = []
    errors = 0
    total = 0
    stop = time.time() + duration

    async def worker(client: httpx.AsyncClient) -> None:
        nonlocal errors, total
        while time.time() < stop:
            try:
                start = time.perf_counter()
                resp = await client.get(f"/api/plans/{plan_id}/status", headers=headers)
                lat = (time.perf_counter() - start) * 1000  # ms
                if resp.status_code != 200:
                    errors += 1
                else:
                    latencies.append(lat)
                total += 1
            except Exception:
                errors += 1
                total += 1

    async with httpx.AsyncClient(base_url=BASE, timeout=10, trust_env=False, limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)) as client:
        await asyncio.gather(*[worker(client) for _ in range(concurrency)])

    # 统计
    real_duration = time.time() - (stop - duration)
    qps = total / real_duration if real_duration > 0 else 0
    if latencies:
        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        p50 = statistics.median(latencies)
        avg = sum(latencies) / len(latencies)
        error_rate = errors / total * 100 if total else 0
    else:
        p95 = p50 = avg = 0
        error_rate = 100.0 if total else 0

    print("\n========== 压测结果 ==========")
    print(f"并发数     : {concurrency}")
    print(f"持续时间   : {real_duration}s")
    print(f"总请求数   : {total}")
    print(f"QPS        : {qps:.1f}")
    print(f"平均延迟   : {avg:.1f} ms")
    print(f"P50 延迟   : {p50:.1f} ms")
    print(f"P95 延迟   : {p95:.1f} ms")
    print(f"错误率     : {error_rate:.3f}%")
    print("==============================")
    print(f"\n验收标准：QPS ≥ 200, P95 < 300ms, 错误率 < 0.1%")
    if qps >= 200 and p95 < 300 and error_rate < 0.1:
        print("✅ 全部达标")
    else:
        print("⚠️ 未达标（注意：本压测仅覆盖 status 查询，且受本机资源限制）")


if __name__ == "__main__":
    asyncio.run(main())
