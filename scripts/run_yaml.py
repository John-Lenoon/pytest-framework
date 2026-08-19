# -*- coding: utf-8 -*-
"""从命令行执行 YAML 场景。"""
import argparse
import json
import sys
from pathlib import Path

# 兼容 `python scripts/run_yaml.py ...`：脚本目录默认是 sys.path[0]，
# 需显式加入仓库根目录才能导入 config/engine/utils。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import load_settings
from engine import ScenarioRunner, load_cases
from utils.allure_utils import redact
from utils.db_client import MysqlClient
from utils.http_client import ApiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="执行 YAML 接口测试场景")
    parser.add_argument("case_file", help="YAML 用例文件")
    parser.add_argument("--case", help="只运行指定名称的场景")
    parser.add_argument("--base-url", help="覆盖 settings.yaml 网关地址")
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="覆盖场景变量，可重复传入；数字会自动转换为 int/float",
    )
    args = parser.parse_args()

    settings = load_settings()
    base_url = args.base_url or settings.gateway.base_url
    selected = [case for case in load_cases(args.case_file)
                if not args.case or case.name == args.case]
    if not selected:
        parser.error("没有找到匹配的场景")

    variables = {
        "member_username": settings.accounts.member.username,
        "member_password": settings.accounts.member.password,
        "admin_username": settings.accounts.admin.username,
        "admin_password": settings.accounts.admin.password,
    }
    for item in args.var:
        if "=" not in item:
            parser.error(f"--var 必须使用 NAME=VALUE 格式: {item}")
        name, value = item.split("=", 1)
        if not name:
            parser.error(f"--var 变量名不能为空: {item}")
        variables[name] = _parse_value(value)

    database = MysqlClient(settings.database) if settings.database.enabled else None
    try:
        with ApiClient(base_url, settings.gateway.timeout, settings.gateway.retry) as client:
            runner = ScenarioRunner(client, database)
            for case in selected:
                result = runner.run(case, variables)
                print(json.dumps({
                    "case": result.case_name,
                    "context": redact(result.context),
                    "steps": len(result.responses),
                }, ensure_ascii=False))
    finally:
        if database:
            database.close()
    return 0


def _parse_value(value: str):
    """命令行变量尽量保留数字类型，其他值按字符串处理。"""
    for converter in (int, float):
        try:
            return converter(value)
        except ValueError:
            pass
    return value


if __name__ == "__main__":
    raise SystemExit(main())
