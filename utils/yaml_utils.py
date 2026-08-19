# -*- coding: utf-8 -*-
"""YAML 加载工具:统一 safe_load 与错误提示。"""
from pathlib import Path

import yaml


def load_yaml(path: Path | str) -> dict:
    """加载 YAML 文件为 dict。

    失败时抛出带文件路径的明确错误,避免用户面对裸的 FileNotFoundError 摸不着头脑。
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {file_path.resolve()}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 解析失败: {file_path.resolve()}\n{exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是 mapping: {file_path.resolve()}")
    return data
