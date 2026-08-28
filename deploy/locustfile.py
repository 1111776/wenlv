"""Locust 压测脚本（说明书 §3.1 口径）。

口径：80% status 查询 + 15% 列表/详情 + 5% 创建。
先登录拿 token，再用 token 打 status 查询（压测主接口）。
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task

API_BASE = os.getenv("WENLV_API_BASE", "http://localhost:8000")
ADVISOR_USER = os.getenv("WENLV_ADVISOR_USER", "advisor_demo")
ADVISOR_PASS = os.getenv("WENLV_ADVISOR_PASS", "wenlv123")


class TravelPlanUser(HttpUser):
    """模拟顾问压测。"""

    wait_time = between(0.01, 0.05)  # 高并发

    def on_start(self):
        """登录获取 token，并创建一个 plan 作为压测目标。"""
        resp = self.client.post(
            "/api/auth/login",
            json={"username": ADVISOR_USER, "password": ADVISOR_PASS},
        )
        data = resp.json()["data"]
        self.token = data["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # 创建一个 plan 用于 status 查询
        resp = self.client.post(
            "/api/plans",
            json={"query": "7天云南家庭游，预算15000"},
            headers={**self.headers, "Idempotency-Key": uuid.uuid4().hex},
        )
        self.plan_id = resp.json()["data"]["plan_id"]

    @task(80)
    def status_query(self):
        """压测主接口：status 查询。"""
        self.client.get(f"/api/plans/{self.plan_id}/status", headers=self.headers)

    @task(10)
    def list_plans(self):
        self.client.get("/api/plans", headers=self.headers)

    @task(5)
    def plan_detail(self):
        self.client.get(f"/api/plans/{self.plan_id}", headers=self.headers)

    @task(5)
    def create_plan(self):
        self.client.post(
            "/api/plans",
            json={"query": "5天海南游"},
            headers={**self.headers, "Idempotency-Key": uuid.uuid4().hex},
        )
