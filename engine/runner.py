# -*- coding: utf-8 -*-
"""配置读取 -> 参数替换 -> 请求发送 -> 数据提取 -> 断言验证。"""
from dataclasses import dataclass, field
from typing import Any

from engine.assertions import AssertionEngine
from engine.jsonpath import find_one
from engine.models import CaseSpec
from engine.template import render
from utils.allure_utils import attach, step
from utils.http_client import ApiClient


@dataclass
class ScenarioResult:
    case_name: str
    context: dict[str, Any]
    responses: list[Any] = field(default_factory=list)


class ScenarioRunner:
    def __init__(self, client: ApiClient, db_client: Any = None):
        self.client = client
        self.assertions = AssertionEngine(db_client)

    def run(self, case: CaseSpec, variables: dict[str, Any] | None = None) -> ScenarioResult:
        context = {**case.variables, **(variables or {})}
        responses = []

        for current_step in case.steps:
            with step(current_step.name):
                request = current_step.request
                response = self.client.request(
                    request.method,
                    render(request.path, context),
                    params=render(request.params, context),
                    json=render(request.json_body, context),
                    data=render(request.data, context),
                    headers=render(request.headers, context),
                )
                responses.append(response)
                try:
                    payload = response.json()
                except ValueError:
                    payload = None

                for name, expression in current_step.extract.items():
                    context[name] = find_one(payload, expression)

                if "token" in current_step.extract:
                    token_head = context.get("tokenHead") or context.get("token_head") or "Bearer"
                    self.client.set_token(context["token"], token_head=str(token_head))

                for assertion in current_step.assertions:
                    self.assertions.assert_spec(assertion, response, payload, context)

                attach("Extracted variables", sorted(current_step.extract))

        return ScenarioResult(case_name=case.name, context=context, responses=responses)
