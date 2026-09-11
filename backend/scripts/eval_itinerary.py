"""行程编排回归测试：对多个城市各生成一份计划，断言编排规则。

用法（容器内，先启动 api+worker+postgres）：
    python scripts/eval_itinerary.py                # 默认用例
    python scripts/eval_itinerary.py "成都" 3       # 追加自定义用例

断言规则（源自行程节奏修复的验收标准）：
  R1 单日白天景点 ≤ 2 个（大景点不硬塞）
  R2 全程无跨天重复景点
  R3 晚上槽位不排公园（公园晚上早关门）
  R4 每天上午槽位非空（前 days-1 天，大景点独占也应有上午）
  R5 夜市不排白天槽位（白天没出摊）

输出：逐条 pass/fail + 汇总；任何失败进程退出码 1（可挂 CI）。
"""

import asyncio
import json
import os
import sys
import time

import httpx

BASE = os.getenv("PLAN_PROBE_BASE", "http://localhost:8000")

# 默认用例：(query, destination, days) —— 覆盖经典大城市 / 小城市 / 短途
DEFAULT_CASES = [
    ("北京3日游，经典大景点", "北京", 3),
    ("成都2日游，休闲美食", "成都", 2),
    ("西安3日游，历史古迹", "西安", 3),
    ("拉萨2日游", "拉萨", 2),
]


def _check_plan(itinerary: dict, destination: str, days: int) -> list[str]:
    """对一个 itinerary 结果跑断言，返回失败原因列表（空 = 全过）。"""
    fails: list[str] = []
    daily = itinerary.get("daily_plan") or []

    seen_names: set[str] = set()
    for d in daily:
        day_no = d.get("day")
        slots = {
            "上午": d.get("morning"),
            "下午": d.get("afternoon"),
            "晚上": d.get("evening"),
        }
        daytime = [s for k, s in slots.items() if k != "晚上" and s]
        evening = slots["晚上"]

        # R1 单日白天景点 ≤ 2
        if len(daytime) > 2:
            fails.append(f"R1 第{day_no}天白天景点 {len(daytime)} 个（>2）：{[s.get('spot') for s in daytime]}")

        # R2 跨天不重复
        for s in daytime + ([evening] if evening else []):
            name = s.get("spot")
            if not name:
                continue
            if name in seen_names:
                fails.append(f"R2 第{day_no}天景点重复：{name}")
            seen_names.add(name)

        # R3 晚上不排公园
        if evening:
            ev_name = evening.get("spot") or ""
            ev_type = evening.get("type") or ""
            if "公园" in ev_name or "公园" in ev_type:
                fails.append(f"R3 第{day_no}天晚上排了公园：{ev_name}")

        # R5 夜市不排白天槽位（白天没出摊）
        for k in ("上午", "下午"):
            s = slots[k]
            if s and "夜市" in (s.get("spot") or ""):
                fails.append(f"R5 第{day_no}天{k}排了夜市：{s.get('spot')}")

        # R4 前几天上午不能为空
        if day_no and day_no < days and not slots["上午"]:
            fails.append(f"R4 第{day_no}天上午为空")

    if len(daily) < days:
        fails.append(f"天数不足：daily_plan {len(daily)} 天 < 计划 {days} 天")
    return fails


async def _run_case(c: httpx.AsyncClient, token: str, query: str, destination: str, days: int) -> tuple[bool, list[str], str]:
    r = await c.post(
        "/api/plans",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": query, "destination": destination, "days": days},
    )
    body = r.json()
    plan = body.get("data") or {}
    plan_id = plan.get("id") or plan.get("plan_id")
    if not plan_id:
        return False, [f"创建计划失败: {json.dumps(body, ensure_ascii=False)[:200]}"], destination

    print(f"  plan_id={plan_id}，轮询中…")
    t0 = time.time()
    st = ""
    while time.time() - t0 < 420:
        await asyncio.sleep(10)
        r = await c.get(f"/api/plans/{plan_id}", headers={"Authorization": f"Bearer {token}"})
        st = r.json()["data"]["status"]
        print(f"  [{time.time()-t0:.0f}s] {st}")
        if st in ("completed", "failed"):
            break
    if st != "completed":
        return False, [f"计划未完成（status={st}）"], destination

    # detail 接口不含 daily_plan，直接用应用自身的 DB 会话取 itinerary 节点结果
    import uuid

    from app.core.database import session_scope
    from app.models import AgentTask
    from sqlalchemy import select

    async with session_scope() as session:
        row = await session.scalar(
            select(AgentTask).where(
                AgentTask.plan_id == uuid.UUID(plan_id),
                AgentTask.agent_type == "itinerary",
            )
        )
    raw = json.dumps(row.result, ensure_ascii=False) if row and row.result else ""
    if not raw:
        return False, [f"DB 中无 itinerary 结果（plan {plan_id}）"], destination
    itinerary = json.loads(raw)
    daily = itinerary.get("daily_plan") or []
    print(f"  === {destination} {days} 日编排 ===")
    for d in daily:
        nm = lambda s: (s.get("spot") if s else "—")
        print(f"  第{d['day']}天: 上午 {nm(d.get('morning'))} | 下午 {nm(d.get('afternoon'))} | 晚上 {nm(d.get('evening'))}")

    fails = _check_plan(itinerary, destination, days)
    return not fails, fails, destination


async def main() -> None:
    cases = list(DEFAULT_CASES)
    if len(sys.argv) >= 3:
        # 追加自定义用例：eval_itinerary.py "查询词" "目的地" [天数]
        cases.append((sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2))

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/login", json={"username": "advisor_demo", "password": "wenlv123"})
        token = r.json()["data"]["access_token"]

        total_fail = 0
        for query, dest, days in cases:
            print(f"\n▶ {query}")
            try:
                ok, fails, _ = await _run_case(c, token, query, dest, days)
            except Exception as exc:
                ok, fails = False, [f"用例异常: {exc}"]
            total_fail += 0 if ok else 1
            if ok:
                print("  ✅ 全部规则通过")
            else:
                for f in fails:
                    print(f"  ❌ {f}")

    print(f"\n=== 汇总：{len(cases) - total_fail}/{len(cases)} 用例通过 ===")
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
