# -*- coding: utf-8 -*-
"""真实 API 的 HTTP 客户端封装(requests.Session)。

设计约定:
- 所有请求统一走网关 {base_url}/mall-{service}/...  (StripPrefix=1),
  因为 401/403 是网关 Sa-Token 鉴权产生的,直连服务端口会绕过鉴权,
  权限类测试点会失真(business_flow.yaml / langgraph 设计同款约定)。
- 禁止 Mock:本客户端只做真实的网络请求。GET/HEAD 等幂等请求在连接失败或
  超时时按 retry 次数重试;POST 等写请求不自动重试,避免重复下单/支付。
- HTTP 4xx/5xx 不重试(业务错误重试无意义),原样返回交给断言助手判断。
- 每个请求/响应自动附加进 Allure 报告(未安装 allure 时静默跳过)。
"""
import logging
import time
from typing import Any, Optional

import requests

from utils.allure_utils import attach_request_response
from utils.logger import get_logger

# 可重试的异常:环境抖动类;业务错误(HTTP 4xx/5xx)不重试
_RETRYABLE_EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)

_HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


class ApiClient:
    """基于 requests.Session 的 HTTP 客户端。

    :param base_url: 网关地址,如 http://localhost:8201
    :param timeout: 单次请求超时(秒)
    :param retry: 连接错误/超时重试次数(不含首次,retry=1 表示最多请求 2 次)
    :param token: 鉴权 token;设置后每个请求自动携带 Authorization
    :param token_head: token 前缀,默认 Bearer,优先使用登录响应中的 tokenHead
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 15,
        retry: int = 1,
        token: Optional[str] = None,
        token_head: str = "Bearer",
        logger: Optional[logging.Logger] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry = max(int(retry), 0)
        self._token = token
        self._token_head = token_head.strip() or "Bearer"
        self.logger = logger or get_logger("ApiClient")
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # token 管理
    # ------------------------------------------------------------------
    @property
    def token(self) -> Optional[str]:
        return self._token

    def set_token(self, token: Optional[str], token_head: Optional[str] = None) -> "ApiClient":
        """设置/清除鉴权 token,返回自身便于链式调用。"""
        self._token = token
        if token_head:
            self._token_head = token_head.strip()
        return self

    # ------------------------------------------------------------------
    # 核心请求
    # ------------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Any = None,
        data: Any = None,
        headers: Optional[dict] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """发起一次带重试的真实 HTTP 请求。

        :param path: 以 / 开头的网关路径,如 /mall-portal/sso/login
        :return: requests.Response(不做任何业务断言,判断交给 utils.assertions)
        """
        method = method.upper()
        if method not in _HTTP_METHODS:
            raise ValueError(f"不支持的 HTTP 方法: {method}")
        url = f"{self.base_url}{path}"
        merged_headers = {"Accept": "application/json"}
        if self._token:
            merged_headers["Authorization"] = f"{self._token_head} {self._token}"
        if headers:
            merged_headers.update(headers)

        # 写请求可能已被服务端处理但客户端读取超时,自动重试会造成重复下单/支付。
        retryable_method = method in {"GET", "HEAD", "OPTIONS"}
        attempts = self.retry + 1 if retryable_method else 1
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=merged_headers,
                    timeout=self.timeout,
                    **kwargs,
                )
                self.logger.info("%s %s -> %s (%.2fs)", method, url, resp.status_code,
                                 resp.elapsed.total_seconds())
                attach_request_response(resp)
                return resp
            except _RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                if attempt < attempts:
                    self.logger.warning(
                        "%s %s 第 %d 次请求失败(%s),%.1fs 后重试",
                        method, url, attempt, exc.__class__.__name__, 0.5 * attempt,
                    )
                    time.sleep(0.5 * attempt)
        # 重试耗尽仍失败:原样抛出,测试会得到明确的失败而不是静默通过
        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------
    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        """关闭底层连接池。"""
        self.session.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
