# -*- coding: utf-8 -*-
"""YAML 场景引擎与数据库校验 fixture。"""
import pytest

from config.settings import Settings
from engine.runner import ScenarioRunner
from utils.db_client import MysqlClient
from utils.http_client import ApiClient


@pytest.fixture(scope="session")
def optional_db_client(settings: Settings):
    if not settings.database.enabled:
        yield None
        return
    client = MysqlClient(settings.database)
    yield client
    client.close()


@pytest.fixture(scope="function")
def yaml_runner(settings: Settings, gateway_up: bool, optional_db_client):
    """每个 YAML 场景使用独立 Session，避免自动提取的 token 污染匿名客户端。"""
    client = ApiClient(
        settings.gateway.base_url,
        timeout=settings.gateway.timeout,
        retry=settings.gateway.retry,
    )
    yield ScenarioRunner(client, optional_db_client)
    client.close()
