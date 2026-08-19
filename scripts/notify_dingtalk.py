# -*- coding: utf-8 -*-
"""CI 测试结果钉钉通知，兼容 Jenkins 与 GitHub Actions。"""
import argparse
import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote_plus

import requests


def signed_webhook(webhook: str, secret: str | None) -> str:
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}\n{secret}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = quote_plus(base64.b64encode(digest))
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True)
    parser.add_argument("--suite", default="pytest-framework")
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()

    webhook = os.environ.get("DINGTALK_WEBHOOK")
    if not webhook:
        print("DINGTALK_WEBHOOK 未配置，跳过通知")
        return 0

    status_text = "通过" if args.status.lower() == "success" else "失败"
    text = f"### {args.suite} 测试{status_text}\n\n状态: **{args.status}**"
    if args.run_url:
        text += f"\n\n[查看 CI 运行详情]({args.run_url})"
    response = requests.post(
        signed_webhook(webhook, os.environ.get("DINGTALK_SECRET")),
        json={"msgtype": "markdown", "markdown": {"title": f"测试{status_text}", "text": text}},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errcode") != 0:
        raise RuntimeError(f"钉钉通知失败: {payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
