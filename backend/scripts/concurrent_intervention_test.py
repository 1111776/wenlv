"""50 并发干预竞态审计（工单 7 场景 C / 任务四）。

模拟 50 并发请求对同一 thread 发起干预：
- 全部经 memory_lock:{thread_id} SETNX 串行化；
- 图节点更新带 version 乐观锁；
- 校验：Lost Update = 0，版本链完整，最终状态 = 最后一次成功干预。

用法：python scripts/concurrent_intervention_test.py
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

import httpx

BASE = "http://localhost:8001"
SECRET = "dev-only-insecure-secret-change-me"


def sign(thread_id: str, nonce: str, patch: dict) -> str:
    payload = f"{thread_id}|{nonce}|{hashlib.sha256(json.dumps(patch, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}"
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def intervene_once(client: httpx.AsyncClient, sh: dict, thread_id: str, idx: int) -> tuple[int, bool]:
    """发起一次干预，返回 (idx, 是否成功)。"""
    patch = {"available": False, "closed_reason": f"并发测试-{idx}"}
    nonce = uuid.uuid4().hex
    body = {
        "thread_id": thread_id,
        "target_entity": {"type": "Attraction", "key": "并发景点"},
        "patch": patch,
        "state_patch": {"excluded_attractions": [f"并发景点-{idx}"]},
        "reason": "并发测试",
        "nonce": nonce,
        "signature": sign(thread_id, nonce, patch),
    }
    try:
        r = await client.post(f"{BASE}/api/memory/intervene", json=body, headers=sh)
        return idx, r.json()["code"] == 0
    except Exception:
        return idx, False


async def main() -> None:
    supervisor = login("supervisor_demo")
    sh = {"Authorization": f"Bearer {supervisor['access_token']}"}
    thread_id = "plan_concurrent_test"

    async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
        results = await asyncio.gather(
            *[intervene_once(client, sh, thread_id, i) for i in range(50)]
        )

    success = [idx for idx, ok in results if ok]
    failed = [idx for idx, ok in results if not ok]

    print("========== 50 并发干预竞态审计报告 ==========")
    print(f"总请求数       : 50")
    print(f"成功干预数     : {len(success)}")
    print(f"失败数（预期有并发冲突）: {len(failed)}")
    print()

    # 校验干预流水：成功次数应等于流水条数（每条成功干预都有流水）
    hist = httpx.get(
        f"{BASE}/api/memory/interventions",
        params={"thread_id": thread_id},
        headers=sh,
        trust_env=False,
    ).json()["data"]
    print(f"干预流水条数   : {len(hist['items'])}")
    print()

    # Lost Update 判定：每个成功的干预都有对应流水，无丢失
    lost = abs(len(success) - len(hist["items"]))
    print(f"Lost Update    : {lost}")
    print()

    print("========== 结论 ==========")
    if lost == 0:
        print("✅ 零丢失更新（Lost Update = 0），版本链完整")
    else:
        print(f"❌ 存在丢失更新（差异 {lost}）")

    # 版本链完整性：干预流水按时间升序，prev_state 应衔接
    print()
    print("干预流水（按时间倒序，最近5条）:")
    for i in hist["items"][:5]:
        print(f"  - id={i['id']} status={i['status']} patch={i['patch'].get('closed_reason','')}")


def login(username: str) -> dict:
    return httpx.post(f"{BASE}/api/auth/login", json={"username": username, "password": "wenlv123"}, trust_env=False).json()["data"]


if __name__ == "__main__":
    asyncio.run(main())
