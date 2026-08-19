# -*- coding: utf-8 -*-
"""断言助手:统一对 CommonResult 响应结构做断言。

mall-swarm 所有接口的响应包装:
    HTTP 层: 200 正常;401/403 由网关 Sa-Token 产生;400 参数错误;500 服务异常
    业务层: {"code": 200, "message": "...", "data": ...}
           code=200 成功;非 200 失败(如 500 用户名或密码错误)

断言失败时自动把响应体附加进 Allure 报告,并给出含请求地址/状态码/响应体的
AssertionError,便于失败定位。
"""
from typing import Any

from utils.allure_utils import attach_response

_MAX_BODY_IN_ERROR = 2000  # 失败信息中截取的响应体长度


def resp_json(resp: Any) -> dict:
    """把响应体解析为 dict;解析失败(非 JSON/空体)时返回空 dict。"""
    try:
        payload = resp.json()
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        return {}


def _fail(resp: Any, reason: str, expected: Any = None) -> None:
    """构造断言失败:附带请求信息与响应体,并写入 Allure。"""
    attach_response(resp)
    body = (resp.text or "")[: _MAX_BODY_IN_ERROR]
    expected_part = f", 期望={expected}" if expected is not None else ""
    raise AssertionError(
        f"{reason}{expected_part}\n"
        f"  请求: {resp.request.method} {resp.request.url}\n"
        f"  响应: status={resp.status_code}\n"
        f"  body: {body}"
    )


def assert_http_ok(resp: Any, expected: int = 200) -> None:
    """断言 HTTP 状态码。"""
    if resp.status_code != expected:
        _fail(resp, f"HTTP 状态码为 {resp.status_code}", expected=expected)


def assert_code(resp: Any, code: int = 200) -> None:
    """断言业务返回码 CommonResult.code。"""
    payload = resp_json(resp)
    actual = payload.get("code")
    if actual != code:
        _fail(
            resp,
            f"CommonResult.code={actual}(message={payload.get('message')})",
            expected=code,
        )


def assert_success(resp: Any) -> dict:
    """断言 HTTP 200 且 code=200,返回完整响应 JSON。"""
    assert_http_ok(resp, 200)
    assert_code(resp, 200)
    return resp_json(resp)


def assert_failed(resp: Any) -> dict:
    """断言业务失败:HTTP 200 但 code != 200(如登录密码错误),返回完整 JSON。"""
    assert_http_ok(resp, 200)
    payload = resp_json(resp)
    if "code" not in payload:
        _fail(resp, "预期 CommonResult 业务失败,但响应不是有效 JSON 或缺少 code")
    if payload.get("code") == 200:
        _fail(resp, "预期业务失败,但 CommonResult.code=200")
    return payload


def assert_gateway_unauthorized(resp: Any) -> None:
    """断言网关鉴权失败(暂未登录或 token 已过期)。

    实测本 fork 的网关对未登录请求返回 HTTP 200 + body code=401
    (而非标准 HTTP 401),两种形态都接受,以真实网关行为为准。
    """
    payload = resp_json(resp)
    if resp.status_code == 200 and payload.get("code") == 401:
        return
    if resp.status_code == 401:
        return
    _fail(
        resp,
        f"预期网关鉴权失败(HTTP 401 或 HTTP 200+code=401),实际 status={resp.status_code}, code={payload.get('code')}",
    )


def assert_msg_contains(resp: Any, *keywords: str) -> None:
    """断言响应体中包含指定关键字(用于错误提示文案)。"""
    text = resp.text or ""
    missing = [k for k in keywords if k not in text]
    if missing:
        _fail(resp, f"响应体中未找到关键字 {missing}")


def get_data(payload: dict) -> Any:
    """取出 CommonResult.data(调用前应已 assert_success)。"""
    return payload.get("data")


def assert_common_page(data: Any) -> dict:
    """断言分页结构 CommonPage:pageNum/pageSize/totalPage/total/list。"""
    if not isinstance(data, dict):
        raise AssertionError(f"预期 CommonPage 为 dict,实际 {type(data).__name__}: {data}")
    for key in ("pageNum", "pageSize", "totalPage", "total", "list"):
        if key not in data:
            raise AssertionError(f"CommonPage 缺少字段 {key},实际 keys={list(data.keys())}")
    if not isinstance(data["list"], list):
        raise AssertionError(f"CommonPage.list 应为 list,实际 {type(data['list']).__name__}")
    return data
