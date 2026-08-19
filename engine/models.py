# -*- coding: utf-8 -*-
"""YAML 场景的数据模型。"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """禁止 YAML 拼写错误被 Pydantic 静默忽略。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RequestSpec(StrictModel):

    method: str
    path: str
    params: dict[str, Any] | None = None
    json_body: Any = Field(default=None, alias="json")
    data: Any = None
    headers: dict[str, Any] | None = None

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if normalized not in allowed:
            raise ValueError(f"不支持的 HTTP 方法: {normalized}")
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("请求 path 必须以 / 开头")
        return value


class AssertionSpec(StrictModel):
    actual: str = "$.code"
    comparator: str = "eq"
    expected: Any = None
    message: str | None = None
    sql: str | None = None
    params: list[Any] | dict[str, Any] | None = None

    @field_validator("comparator")
    @classmethod
    def validate_comparator(cls, value: str) -> str:
        allowed = {
            "eq", "rv", "ne", "contains", "not_contains", "in", "not_in",
            "gt", "ge", "lt", "le", "exists", "not_exists", "regex",
            "length_eq", "type", "db", "db_eq",
        }
        if value not in allowed:
            raise ValueError(f"不支持的断言类型: {value}")
        return value


class StepSpec(StrictModel):
    name: str = Field(min_length=1)
    request: RequestSpec
    extract: dict[str, str] = Field(default_factory=dict)
    assertions: list[AssertionSpec] = Field(default_factory=list)


class CaseSpec(StrictModel):
    name: str = Field(min_length=1)
    description: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepSpec] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class CaseFile(StrictModel):
    cases: list[CaseSpec] = Field(min_length=1)
