"""Workspace 状态文件管理（travel_plan.md，说明书 §2.5 / 附录 A）。

travel_plan.md 结构：
    ---
    version: 12
    checksum: <body 的 SHA256>
    status: running
    resume_from: web_research:page_6
    plan_id: <uuid>
    updated_at: <ISO-8601>
    ---
    <body: 需求摘要 / Task List / 日志 / HITL 摘要>

断点恢复驱动源 = 此文件 YAML 头的 resume_from（S2/S24）。
checksum 只校验 body（YAML 头本身不参与），失败回退快照（13.4）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.core.config import settings
from app.core.logging import get_logger
from app.services.atomic_file import atomic_write, sha256, snapshot_before_write

logger = get_logger(__name__)

HEADER_SEP = "---\n"


class WorkspaceError(Exception):
    """状态文件损坏且无法回退时抛出。"""


class PlanFileManager:
    """管理单个行程的 travel_plan.md 文件。"""

    def __init__(self, plan_id: uuid.UUID | str):
        self.plan_id = str(plan_id)
        self.dir = Path(settings.workspace_root) / self.plan_id
        self.path = self.dir / "travel_plan.md"

    # ------------------------------------------------------------------ #
    # 读取
    # ------------------------------------------------------------------ #
    def load(self) -> tuple[dict, str]:
        """读取并校验，返回 (header_dict, body_str)。

        校验失败时依次回退：快照 → 抛 WorkspaceError（调用方再走 Checkpointer）。
        """
        if not self.path.exists():
            raise WorkspaceError(f"travel_plan.md 不存在: {self.path}")
        raw = self.path.read_text(encoding="utf-8")
        header, body = self._split(raw)
        if header.get("checksum") != sha256(body):
            logger.warning("checksum 校验失败，尝试回退快照 plan=%s", self.plan_id)
            snap = self._try_snapshot()
            if snap is None:
                raise WorkspaceError(f"travel_plan.md 损坏且无快照: {self.path}")
            return snap
        return header, body

    def load_resume_from(self) -> str | None:
        """仅读取 YAML 头的 resume_from（恢复热路径，轻量）。"""
        try:
            header, _ = self.load()
            return header.get("resume_from")
        except WorkspaceError:
            return None

    def _try_snapshot(self) -> tuple[dict, str] | None:
        from app.services.atomic_file import load_snapshot

        raw = load_snapshot(self.path)
        if raw is None:
            return None
        header, body = self._split(raw)
        if header.get("checksum") == sha256(body):
            return header, body
        return None

    @staticmethod
    def _split(raw: str) -> tuple[dict, str]:
        """把整文件拆成 (YAML header dict, body)。"""
        if not raw.startswith(HEADER_SEP):
            raise WorkspaceError("缺少 YAML 头")
        end = raw.find(HEADER_SEP, len(HEADER_SEP))
        if end == -1:
            raise WorkspaceError("YAML 头未闭合")
        header_raw = raw[len(HEADER_SEP):end]
        body = raw[end + len(HEADER_SEP):]
        header = yaml.safe_load(header_raw) or {}
        return header, body

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    def write(
        self,
        body: str,
        *,
        status: str,
        resume_from: str | None,
        version: int,
        plan_id: uuid.UUID | str,
    ) -> None:
        """原子写整个文件（自动计算 checksum，写前快照旧版）。"""
        # 写前快照旧版（若存在）
        snapshot_before_write(self.path, version)

        header_lines = [
            f"version: {version}",
            f"checksum: {sha256(body)}",
            f"status: {status}",
            f"resume_from: {resume_from or 'null'}",
            f"plan_id: {plan_id}",
            f"updated_at: {datetime.now(timezone.utc).isoformat()}",
        ]
        full = HEADER_SEP + "\n".join(header_lines) + "\n" + HEADER_SEP + "\n" + body
        atomic_write(self.path, full)

    def build_body(
        self,
        *,
        query: str,
        preferences: dict | None,
        tasks: list[dict],
        logs: list[str],
        hitl: dict | None = None,
    ) -> str:
        """生成正文（需求摘要 + Task List + 日志 + HITL 摘要）。"""
        lines: list[str] = ["# Travel Plan", ""]

        lines.append("## 需求摘要")
        lines.append(f"- 原始需求：{query}")
        if preferences:
            lines.append(f"- 解析偏好：{_compact(preferences)}")
        lines.append("")

        lines.append("## Task List")
        lines.append("| order | agent | title | status | page_no |")
        lines.append("| --- | --- | --- | --- | --- |")
        for t in sorted(tasks, key=lambda x: x.get("order_index", 0)):
            lines.append(
                f"| {t.get('order_index', '-')} | {t.get('agent_type', '-')} | "
                f"{t.get('title', '-')} | {t.get('status', '-')} | {t.get('page_no', '-')} |"
            )
        lines.append("")

        lines.append("## 日志")
        if logs:
            for log in logs[-20:]:  # 最多保留最近 20 条
                lines.append(f"- {log}")
        else:
            lines.append("- （暂无）")
        lines.append("")

        if hitl:
            lines.append("## HITL 风险摘要")
            lines.append(f"- 触发原因：{hitl.get('reason', '-')}")
            lines.append(f"- 明细：{_compact(hitl.get('detail', {}))}")
            lines.append("")

        return "\n".join(lines)


def _compact(obj: object) -> str:
    """紧凑打印 dict/list，避免多行污染 markdown 表格。"""
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)
