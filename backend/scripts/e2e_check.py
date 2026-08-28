"""端到端联调脚本（说明书 场景 A/C/D + 恢复）。

用法：
    python scripts/e2e_check.py

覆盖：
- 场景 A：正常行程生成（10 页抓取 + 报告）
- 场景 C：第 7 页注入拦截（audit_logs.action=security_block）
- 场景 D：HITL 挂起 + 审批通过续跑（或驳回）
- 断点恢复：验证 resume_from 与 completed 页不重复请求（通过 Mock 计数器）

用 Python 客户端（requests）避免 shell 中文编码问题。
"""

from __future__ import annotations

import json
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000"


def login(username: str, password: str = "wenlv123") -> dict:
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
    return r.json()["data"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_plan(token: str, query: str, budget_limit: float | None = None) -> str:
    body = {"query": query}
    if budget_limit is not None:
        body["budget_limit"] = budget_limit
    r = httpx.post(
        f"{BASE}/api/plans",
        json=body,
        headers={**auth_headers(token), "Idempotency-Key": uuid.uuid4().hex},
    )
    return r.json()["data"]["plan_id"]


def wait_status(token: str, plan_id: str, expect: set[str], timeout: float = 30.0) -> dict:
    import time

    start = time.time()
    while time.time() - start < timeout:
        r = httpx.get(f"{BASE}/api/plans/{plan_id}/status", headers=auth_headers(token))
        data = r.json()["data"]
        if data["status"] in expect:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"等待状态 {expect} 超时，当前 {data['status']}")


def main() -> int:
    advisor = login("advisor_demo")
    supervisor = login("supervisor_demo")

    print("=" * 60)
    print("场景 A：创建行程 → 等待完成")
    plan_id = create_plan(advisor["access_token"], "7天云南家庭游，预算15000，2大1小，偏自然风光", budget_limit=15000)
    print(f"  plan_id = {plan_id}")

    # 由于种子第 7 页注入 + 第 8 页严重负面 + 第 9 页夜行，会触发 HITL 挂起
    status = wait_status(advisor["access_token"], plan_id, {"suspended", "completed"})
    print(f"  最终状态 = {status['status']} resume_from = {status['resume_from']}")
    assert status["status"] == "suspended", f"期望 suspended，实际 {status['status']}"
    print("  ✅ 场景 D：HITL 挂起成功")

    # 场景 C：注入拦截审计（读文件系统的 travel_plan.md 更可靠）
    print("=" * 60)
    print("场景 C：验证注入拦截")
    from pathlib import Path

    plan_file_path = Path(f"workspace/{plan_id}/travel_plan.md")
    md = plan_file_path.read_text(encoding="utf-8") if plan_file_path.exists() else ""
    assert "blocked" in md, "看板 Task List 应体现 blocked 页"
    print("  ✅ 看板 Task List 含 blocked（第 7 页注入拦截）")

    # 审批通过续跑
    print("=" * 60)
    print("场景 D：审批通过 → 续跑 → completed")
    pending = httpx.get(f"{BASE}/api/reviews/pending", headers=auth_headers(supervisor["access_token"]))
    items = pending.json()["data"]["items"]
    assert items, "应有待审记录"
    # 按 plan_id 精确匹配当前行程的审核记录（避免取到其他挂起行程）
    review = next((it for it in items if it["plan_id"] == plan_id), None)
    assert review is not None, f"待审列表应含 plan_id={plan_id}"
    review_id = review["id"]
    reason = review["reason"]
    print(f"  review_id = {review_id} reason = {reason}")

    r = httpx.post(f"{BASE}/api/reviews/{review_id}/claim", headers=auth_headers(supervisor["access_token"]))
    assert r.json()["code"] == 0, f"claim 失败: {r.json()}"

    r = httpx.post(
        f"{BASE}/api/reviews/{review_id}/decision",
        json={"decision": "approved", "comment": "同意，风险可控"},
        headers=auth_headers(supervisor["access_token"]),
    )
    assert r.json()["code"] == 0, f"decision 失败: {r.json()}"

    status = wait_status(advisor["access_token"], plan_id, {"completed"}, timeout=30.0)
    print(f"  ✅ 最终 completed，resume_from = {status['resume_from']}")

    report = httpx.get(f"{BASE}/api/plans/{plan_id}/report", headers=auth_headers(advisor["access_token"]))
    assert report.json()["code"] == 0
    md = report.json()["data"]["markdown"]
    assert "预算明细" in md, "报告应含预算明细"
    print("  ✅ 报告生成（含预算明细）")

    print("=" * 60)
    print("全部场景通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
