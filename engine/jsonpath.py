# -*- coding: utf-8 -*-
"""基于 jsonpath-ng 的响应字段提取。"""
from typing import Any

from jsonpath_ng.ext import parse


def find_all(payload: Any, expression: str) -> list[Any]:
    return [match.value for match in parse(expression).find(payload)]


def find_one(payload: Any, expression: str, *, required: bool = True) -> Any:
    values = find_all(payload, expression)
    if not values:
        if required:
            raise AssertionError(f"JSONPath 未匹配到数据: {expression}")
        return None
    return values[0] if len(values) == 1 else values
