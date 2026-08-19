# -*- coding: utf-8 -*-
"""Allure 报告工具:请求/响应附件、step 上下文、环境信息。

allure-pytest 未安装时全部操作降级为 no-op,不影响用例执行;
安装后每个请求的入参与响应体会自动进入 Allure 报告。
"""
import json
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import allure  # type: ignore

    HAS_ALLURE = True
except ImportError:  # 未安装 allure-pytest 时降级
    allure = None
    HAS_ALLURE = False

MAX_BODY_LENGTH = 4000  # 附件截断长度,防止超大响应撑爆报告
_SENSITIVE_KEYS = {
    "authorization", "password", "passwd", "token", "tokenhead",
    "access_token", "refresh_token", "authcode", "phonenumber", "telephone",
}
_SENSITIVE_PATTERN = re.compile(
    r'(?i)("?(?:password|passwd|token|tokenHead|access_token|refresh_token|authCode|telephone)"?\s*[:=]\s*)'
    r'("?)[^",\s}&]+\2'
)


def _is_sensitive(key: str) -> bool:
    return key.lower().replace("-", "_") in _SENSITIVE_KEYS


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, "***" if _is_sensitive(key) else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def redact(value: Any) -> Any:
    """递归脱敏常见认证字段，无法解析的文本使用保守正则处理。"""
    if isinstance(value, dict):
        return {key: "***" if _is_sensitive(str(key)) else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return _SENSITIVE_PATTERN.sub(r'\1"***"', value)
        return json.dumps(redact(parsed), ensure_ascii=False)
    return value


def attach(name: str, body: Any) -> None:
    """向 Allure 报告附加文本附件。"""
    if not HAS_ALLURE:
        return
    text = str(body)
    if len(text) > MAX_BODY_LENGTH:
        text = text[:MAX_BODY_LENGTH] + f"\n... (截断,原始长度 {len(body)})"
    allure.attach(text, name=name, attachment_type=allure.attachment_type.TEXT)


def attach_request(resp: Any) -> None:
    """附加请求信息(method/url/params/body)。"""
    if not HAS_ALLURE:
        return
    request = resp.request
    detail = f"{request.method} {redact_url(request.url)}"
    if request.body:
        detail += f"\nbody: {redact(request.body)}"
    attach("Request", detail)


def attach_response(resp: Any) -> None:
    """附加响应信息(status/headers 摘要/body)。"""
    if not HAS_ALLURE:
        return
    detail = f"status_code: {resp.status_code}\nelapsed: {resp.elapsed.total_seconds():.2f}s"
    body = redact(resp.text) if resp.text else "(空响应体)"
    detail += f"\nbody: {body}"
    attach("Response", detail)


def attach_request_response(resp: Any) -> None:
    """同时附加请求与响应(每个 HTTP 调用默认调用一次)。"""
    attach_request(resp)
    attach_response(resp)


def step(title: str):
    """Allure step 上下文;无 allure 时退化为 nullcontext。"""
    if HAS_ALLURE:
        return allure.step(title)
    return nullcontext()


def write_environment(properties: dict, output_dir: Path | str = "allure-results") -> None:
    """把环境信息写入 allure-results/environment.properties(供 allure generate 展示)。"""
    if not HAS_ALLURE:
        return
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    target = out_dir / "environment.properties"
    existing = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                existing[key] = value
    existing.update({str(k): str(v) for k, v in properties.items()})
    target.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
