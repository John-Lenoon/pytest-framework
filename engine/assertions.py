# -*- coding: utf-8 -*-
"""YAML 场景的通用断言与数据库双重校验。"""
import re
from typing import Any

from engine.jsonpath import find_one
from engine.models import AssertionSpec
from engine.template import render


def response_value(response: Any, payload: Any, expression: str) -> Any:
    if expression == "status_code":
        return response.status_code
    if expression == "text":
        return response.text
    if expression.startswith("headers."):
        return response.headers.get(expression.removeprefix("headers."))
    if expression.startswith("$"):
        return find_one(payload, expression, required=False)
    raise ValueError(f"不支持的实际值表达式: {expression}")


def _compare(actual: Any, comparator: str, expected: Any) -> bool:
    comparators = {
        "eq": lambda: actual == expected,
        "rv": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "contains": lambda: expected in actual,
        "not_contains": lambda: expected not in actual,
        "in": lambda: actual in expected,
        "not_in": lambda: actual not in expected,
        "gt": lambda: actual > expected,
        "ge": lambda: actual >= expected,
        "lt": lambda: actual < expected,
        "le": lambda: actual <= expected,
        "exists": lambda: actual is not None,
        "not_exists": lambda: actual is None,
        "regex": lambda: re.search(str(expected), str(actual)) is not None,
        "length_eq": lambda: len(actual) == expected,
        "type": lambda: type(actual).__name__ == str(expected),
    }
    if comparator not in comparators:
        raise ValueError(f"不支持的断言类型: {comparator}")
    try:
        return comparators[comparator]()
    except (TypeError, AttributeError) as exc:
        raise AssertionError(
            f"断言类型不适用于实际值: comparator={comparator}, actual={actual!r}, "
            f"expected={expected!r}"
        ) from exc


class AssertionEngine:
    def __init__(self, db_client: Any = None):
        self.db_client = db_client

    def assert_spec(
        self,
        spec: AssertionSpec,
        response: Any,
        payload: Any,
        context: dict[str, Any],
    ) -> None:
        expected = render(spec.expected, context)
        actual = response_value(response, payload, spec.actual)

        if spec.comparator in {"db", "db_eq"}:
            if self.db_client is None:
                raise AssertionError("用例包含数据库断言，但 database.enabled=false")
            if not spec.sql:
                raise ValueError("db_eq 断言必须配置 sql")
            params = render(spec.params or [], context)
            expected = self.db_client.scalar(render(spec.sql, context), params)
            passed = actual == expected
        else:
            passed = _compare(actual, spec.comparator, expected)

        if not passed:
            message = spec.message or "场景断言失败"
            raise AssertionError(
                f"{message}: actual={actual!r}, comparator={spec.comparator}, expected={expected!r}"
            )
