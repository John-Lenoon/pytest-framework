# -*- coding: utf-8 -*-
"""日志工具:统一格式的 stdout 日志,pytest -s 或 xdist 下均可见。"""
import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


def _ensure_configured() -> None:
    """全局只配置一次根 logger,避免重复 handler。"""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, _DATE_FORMAT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger(统一 INFO 级别、stdout 输出)。"""
    _ensure_configured()
    return logging.getLogger(name)
