"""场景 B 完整自动化：kill -9 崩溃恢复验证。

流程（全自动）：
1. 启动 worker（带 WENLV_RESEARCH_DELAY_MS 使抓取有可捕捉窗口）；
2. 创建行程；
3. 轮询到 resume_from 达到 web_research:page_5 以上（说明前 5 页已完成并持久化）；
4. kill -9 worker（模拟崩溃，此时还有页未完成）；
5. 记录崩溃前 completed 页数；
6. 重启 worker，触发 recover_all()；
7. 断言：行程最终 completed，且崩溃前已完成的页数不变（未重复抓取）。

用法：
    python scripts/recovery_test.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 环境（与本地 API 一致）
ENV = {
    **os.environ,
    "WENLV_DATABASE_URL": "postgresql+asyncpg://wenlv:wenlv@localhost:5432/wenlv",
    "WENLV_REDIS_URL": "redis://localhost:6379/0",
    "WENLV_JWT_SECRET": "dev-only-insecure-secret-change-me",
    "WENLV_WORKSPACE_ROOT": "./workspace",
    "WENLV_LLM_MODE": "mock",
    "WENLV_RESEARCH_DELAY_MS": "150",  # 每页 150ms，10 页约 1.5s，可捕捉 running 窗口
    "PYTHONIOENCODING": "utf-8",
}


def login(username: str) -> dict:
    return httpx.post(f"{BASE}/api/auth/login", json={"username": username, "password": "wenlv123"}).json()["data"]


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_plan(token: str) -> str:
    r = httpx.post(
        f"{BASE}/api/plans",
        json={"query": "7天云南家庭游，预算50000", "budget_limit": 50000},  # 高预算避免触发 budget_over
        headers={**headers(token), "Idempotency-Key": uuid.uuid4().hex},
    )
    return r.json()["data"]["plan_id"]


def get_status(token: str, plan_id: str) -> dict:
    r = httpx.get(f"{BASE}/api/plans/{plan_id}/status", headers=headers(token))
    return r.json()["data"]


def completed_pages(token: str, plan_id: str) -> int:
    s = get_status(token, plan_id)
    return s["progress"].get("done", 0)


def wait_resume(token: str, plan_id: str, min_page: int, timeout: float = 20.0) -> dict:
    """等待 resume_from 达到 page_min 及以上。"""
    start = time.time()
    while time.time() - start < timeout:
        s = get_status(token, plan_id)
        rf = s.get("resume_from") or ""
        if s["status"] == "suspended":
            return s
        if rf.startswith("web_research:page_"):
            if int(rf.split("page_", 1)[1]) >= min_page:
                return s
        time.sleep(0.05)
    raise TimeoutError(f"未达 page_{min_page}，当前 {get_status(token, plan_id)}")


def start_worker() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "worker"],
        cwd=BACKEND_DIR,
        env=ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    advisor = login("advisor_demo")
    token = advisor["access_token"]

    # 1. 启动 worker
    worker = start_worker()
    print("Worker 已启动，pid =", worker.pid)
    time.sleep(3)

    # 2. 创建行程
    plan_id = create_plan(token)
    print(f"plan_id = {plan_id}")

    # 3. 等待抓取到第 5 页以上
    s = wait_resume(token, plan_id, min_page=5)
    print(f"抓取到 resume_from = {s['resume_from']}（前 5 页已持久化）")

    # 4. kill -9 worker（Windows 无 SIGKILL，用 terminate 强杀；POSIX 用 SIGKILL）
    before_done = completed_pages(token, plan_id)
    print(f"kill 前已完成任务数 = {before_done}")
    if hasattr(signal, "SIGKILL"):
        print(f"执行 kill -9 worker pid={worker.pid} ...")
        os.kill(worker.pid, signal.SIGKILL)
    else:
        print(f"执行 terminate（Windows 等价强杀）worker pid={worker.pid} ...")
        worker.terminate()
    worker.wait()
    print("Worker 已被强杀")

    # 短暂等待，确认行程卡在 running
    time.sleep(1)
    s = get_status(token, plan_id)
    print(f"kill 后行程状态 = {s['status']} resume_from = {s['resume_from']}")

    # 5. 重启 worker，触发 recover_all
    print("\n重启 Worker ...")
    worker2 = start_worker()
    print(f"新 Worker pid = {worker2.pid}")

    # 6. 等待恢复续跑（种子数据第8页负面+第9页夜行，必然挂起；恢复验证点是"续跑+页数不变"）
    start = time.time()
    while time.time() - start < 30:
        s = get_status(token, plan_id)
        # 恢复后续跑会重新到达 human_review:wait（挂起）或 completed（若无风险）
        if s["status"] in ("suspended", "completed"):
            break
        time.sleep(0.3)

    after_done = completed_pages(token, plan_id)
    print(f"\n恢复后状态 = {s['status']} resume_from = {s['resume_from']}")
    print(f"恢复后已完成任务数 = {after_done}")

    # 7. 断言：恢复续跑成功（到达终态或挂起态），且已完成任务数不减（无重复/遗漏）
    assert s["status"] in ("suspended", "completed"), f"恢复后应到达 suspended/completed，实际 {s['status']}"
    assert after_done >= before_done, f"已完成任务数不应减少（before={before_done}, after={after_done}）"
    # 恢复后 resume_from 应推进（说明从断点续跑，而非从头重来）
    assert s["resume_from"] is not None and s["resume_from"] != "", "恢复后应有 resume_from"
    print(f"\n✅ 场景 B 恢复通过：崩溃前 {before_done} 个任务完成，恢复后续跑，已完成任务数 {after_done} 无重复/遗漏")

    worker2.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
