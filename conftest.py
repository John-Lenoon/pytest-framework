# -*- coding: utf-8 -*-
"""框架根 conftest:注册 fixture 插件 + 配置测试报告。

目录约定(与 langgraph/design/07-directory-structure.md 同款约定):
- conftest.py 只有框架根这一层,统一提供 session 级 fixture;
- tests/ 等子目录不另建 conftest,避免 fixture 解析歧义;
- fixture 按业务域拆分在 fixtures/ 下,通过 pytest_plugins 在此统一注册。
"""
import pytest

from config.settings import load_settings
from utils.allure_utils import HAS_ALLURE, write_environment
from utils.logger import get_logger

log = get_logger("conftest")

# 统一注册各业务域的 fixture 模块
pytest_plugins = [
    "fixtures.session_fixtures",   # settings / 网关门禁 / 会员与管理员客户端
    "fixtures.member_fixtures",    # 新会员注册链路(faker 数据)
    "fixtures.product_fixtures",   # 分类树 / 搜索 / 详情 / SKU / 品牌
    "fixtures.cart_fixtures",      # 购物车条目(自建自删)
    "fixtures.order_fixtures",     # 确认单 / 订单 / 支付 / 取消
    "fixtures.engine_fixtures",    # YAML 场景执行 / 可选 MySQL 校验
]


@pytest.hookimpl(optionalhook=True)
def pytest_html_report_title(report) -> None:
    """设置 pytest-html 浏览器标题与报告标题。"""
    report.title = "mall-swarm API 自动化测试报告"


@pytest.hookimpl(optionalhook=True)
def pytest_metadata(metadata: dict) -> None:
    """在 HTML 报告 Environment 区域写入非敏感测试环境信息。"""
    try:
        settings = load_settings()
        metadata["Test environment"] = settings.env
        metadata["Gateway"] = settings.gateway.base_url
        metadata["Python framework"] = "pytest"
    except Exception as exc:  # noqa: BLE001 - 配置错误由 settings fixture 正常暴露
        log.warning("写入 HTML 报告环境信息失败: %s", exc)


def pytest_sessionstart(session) -> None:
    """运行开始时把环境信息写入 allure-results/environment.properties。

    配置加载失败只记录警告,不影响用例执行(真正的配置错误会在 settings
    fixture 首次使用时暴露)。
    """
    if not HAS_ALLURE or hasattr(session.config, "workerinput"):
        return
    output_dir = session.config.getoption("--alluredir", default=None)
    if not output_dir:
        return
    try:
        settings = load_settings()
        write_environment({
            "env": settings.env,
            "base_url": settings.gateway.base_url,
            "member_account": settings.accounts.member.username,
            "admin_account": settings.accounts.admin.username,
        }, output_dir=output_dir)
    except Exception as exc:  # noqa: BLE001 —— 环境信息属锦上添花
        log.warning("写入 Allure 环境信息失败: %s", exc)
