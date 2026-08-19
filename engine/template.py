# -*- coding: utf-8 -*-
"""场景变量替换，支持嵌套数据和环境变量。"""
import os
import re
import time
import uuid
from random import randint
from typing import Any

_VARIABLE = re.compile(r"\$\{([^{}]+)}")
_FUNCTION = re.compile(r"^\$\{\{([^{}]+)}}$")


def _resolve(name: str, context: dict[str, Any]) -> Any:
    if name.startswith("ENV:"):
        env_name = name[4:]
        if env_name not in os.environ:
            raise KeyError(f"环境变量未设置: {env_name}")
        return os.environ[env_name]
    if name not in context:
        raise KeyError(f"场景变量不存在: {name}")
    return context[name]


def _call_function(expression: str) -> Any:
    if expression == "uuid":
        return uuid.uuid4().hex
    if expression == "timestamp":
        return int(time.time())
    if expression.startswith("random_int:"):
        lower, upper = expression.removeprefix("random_int:").split(",", 1)
        return randint(int(lower), int(upper))
    raise ValueError(f"不支持的动态函数: {expression}")


def render(value: Any, context: dict[str, Any]) -> Any:
    """递归替换 ${name}；字段值只有一个变量时保留原始类型。"""
    if isinstance(value, dict):
        return {key: render(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(render(item, context) for item in value)
    if not isinstance(value, str):
        return value

    function = _FUNCTION.fullmatch(value)
    if function:
        return _call_function(function.group(1))

    exact = _VARIABLE.fullmatch(value)
    if exact:
        return _resolve(exact.group(1), context)
    return _VARIABLE.sub(lambda match: str(_resolve(match.group(1), context)), value)
