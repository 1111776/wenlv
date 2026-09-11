"""临时探针：创建一个行程计划并轮询到完成，打印每日景点编排（验证时长预算装填）。"""

import asyncio
import json
import sys
import time

import httpx

import os

BASE = os.getenv("PLAN_PROBE_BASE", "http://localhost:8000")


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "北京2日游，经典景点"
    destination = sys.argv[2] if len(sys.argv) > 2 else "北京"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post(
            "/api/auth/login",
            json={"username": "advisor_demo", "password": "wenlv123"},
        )
        token = r.json()["data"]["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"

        r = await c.post(
            "/api/plans",
            json={"query": query, "destination": destination, "days": days},
        )
        body = r.json()
        print("POST /api/plans ->", json.dumps(body, ensure_ascii=False)[:300])
        plan = body.get("data") or {}
        plan_id = plan.get("id") or plan.get("plan_id")
        if not plan_id:
            return
        print(f"plan_id={plan_id}")

        t0 = time.time()
        while time.time() - t0 < 420:
            await asyncio.sleep(8)
            r = await c.get(f"/api/plans/{plan_id}")
            st = r.json()["data"]["status"]
            print(f"  [{time.time()-t0:.0f}s] status={st}")
            if st in ("completed", "failed"):
                break
        if st != "completed":
            print("计划未完成，退出")
            return

        r = await c.get(f"/api/plans/{plan_id}")
        detail = r.json()["data"]

    # 从 detail 里递归找 daily_plan（不同接口版本位置可能不同）
    def find_daily(node):
        if isinstance(node, dict):
            if "daily_plan" in node and isinstance(node["daily_plan"], list):
                return node
            for v in node.values():
                found = find_daily(v)
                if found:
                    return found
        elif isinstance(node, list):
            for v in node:
                found = find_daily(v)
                if found:
                    return found
        return None

    it = find_daily(detail)
    if not it:
        print("detail keys:", list(detail.keys()) if isinstance(detail, dict) else type(detail))
        print("未找到 daily_plan")
        return
    print(f"\n=== {it.get('destination', destination)} {it.get('days', days)} 日编排 ===")
    for d in it["daily_plan"]:
        def nm(s):
            return s["spot"] if s else "—"
        print(
            f"第{d['day']}天: 上午 {nm(d['morning'])} | 下午 {nm(d['afternoon'])} | 晚上 {nm(d['evening'])}"
        )


def _visit_hours_label(spot: dict) -> str:
    t = spot.get("type", "")
    return t[:12] if t else "?"


asyncio.run(main())
