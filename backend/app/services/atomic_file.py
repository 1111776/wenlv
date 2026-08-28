"""状态文件原子写入（说明书 13.1 / S2）。

"临时写入-校验-原子替换" 的完整实现：
1. 同目录 ``mkstemp`` 写全量内容；
2. ``flush`` + ``os.fsync`` 文件；
3. ``os.replace``（**禁止 ``os.rename`` 覆盖**，Windows 不兼容）；
4. 目录 fd ``fsync``（不支持则记录 warning）；
5. 写前把当前正式文件 copy 到 ``snapshots/v{n}.md``（最多 N 份）；
6. ``.tmp`` 不是备份——启动时清理孤儿临时文件。

保证：任何时刻崩溃，正式文件要么是旧版完整内容、要么是新版完整内容，
不存在「写了一半」的正式文件。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def sha256(text: str) -> str:
    """返回字符串的 SHA256 十六进制摘要。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write(path: str | Path, content: str) -> None:
    """原子写入：临时文件 + fsync + replace + 目录 fsync。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    directory = str(path.parent)

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".md")
    try:
        # ① 写入 + fsync 文件内容落盘
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # ② 原子替换（Windows 上 os.replace 才能覆盖已存在文件）
        os.replace(tmp_path, path)

        # ③ 目录 fsync，保证 rename 本身持久化（POSIX）
        try:
            dfd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            logger.warning("目录 fsync 不支持（%s），可容忍", directory)
    except Exception:
        # 失败时清理临时文件，避免残留
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def snapshot_before_write(path: str | Path, version: int) -> None:
    """写前把当前正式文件复制到 snapshots/v{version}.md（保留最近 N 份）。"""
    path = Path(path)
    if not path.exists():
        return  # 首次写入无旧版可快照

    snap_dir = path.parent / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, snap_dir / f"v{version}.md")

    # 只保留最近 settings.snapshot_max 份（按版本号倒序裁剪）
    snaps = sorted(snap_dir.glob("v*.md"), key=lambda p: _version_key(p.name))
    for old in snaps[: -settings.snapshot_max]:
        try:
            old.unlink()
        except OSError:
            pass


def _version_key(name: str) -> int:
    """从 ``v12.md`` 提取版本号 12。"""
    try:
        return int(name.removeprefix("v").removesuffix(".md"))
    except ValueError:
        return 0


def load_snapshot(path: str | Path) -> str | None:
    """读取最近一份合法快照内容；无快照返回 None。"""
    path = Path(path)
    snap_dir = path.parent / "snapshots"
    if not snap_dir.exists():
        return None
    snaps = sorted(snap_dir.glob("v*.md"), key=lambda p: _version_key(p.name), reverse=True)
    for s in snaps:
        try:
            return s.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def cleanup_orphan_tmp(root: str | Path) -> int:
    """清理 workspace 下所有孤儿 ``.tmp_*``（崩溃残留），返回清理数量。"""
    root = Path(root)
    removed = 0
    if not root.exists():
        return 0
    for tmp in root.rglob(".tmp_*"):
        try:
            tmp.unlink()
            removed += 1
        except OSError:
            pass
    return removed
