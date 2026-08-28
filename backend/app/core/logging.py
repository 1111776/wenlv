"""统一日志配置。

结构化 JSON 日志便于在容器环境（docker logs / Grafana Loki）里检索。
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """初始化根日志器，输出到 stdout（容器最佳实践）。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler（热重载场景）
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """获取具名 logger。"""
    return logging.getLogger(name)
