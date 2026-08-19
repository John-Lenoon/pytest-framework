# -*- coding: utf-8 -*-
"""真实 mall API 的 YAML 数据驱动示例。"""
from pathlib import Path

import pytest

from config.settings import Settings
from engine import load_cases

ROOT = Path(__file__).resolve().parents[1]
LOGIN_CASES = load_cases(ROOT / "cases" / "mall" / "login.yaml")
DB_CASE = load_cases(ROOT / "cases" / "mall" / "member_db_validation.yaml")[0]

pytestmark = pytest.mark.login


def _account_variables(settings: Settings) -> dict:
    return {
        "member_username": settings.accounts.member.username,
        "member_password": settings.accounts.member.password,
    }


@pytest.mark.parametrize("case", LOGIN_CASES, ids=lambda case: case.name)
def test_yaml_login_scenarios(yaml_runner, settings: Settings, case):
    yaml_runner.run(case, _account_variables(settings))


@pytest.mark.database
def test_yaml_member_info_matches_mysql(yaml_runner, settings: Settings):
    if not settings.database.enabled:
        pytest.skip("设置 PYTEST_DB_ENABLED=true 后执行 MySQL 双重校验")
    yaml_runner.run(DB_CASE, _account_variables(settings))
