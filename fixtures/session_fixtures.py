# -*- coding: utf-8 -*-
"""会话级 fixture:全局配置、网关健康门禁、鉴权客户端(会员/管理员)。

fixture 说明:
- settings         Pydantic 全局配置(session)
- gateway_up       网关健康门禁:网关不可达时 pytest.exit 并给出启动指引(session)
- anon_client      无 token 的 HTTP 客户端(session)
- member_token     会员登录 token(test/123456,来自真实 /sso/login)(session)
- member_client    携带会员 token 的客户端(session)
- admin_token      管理员登录 token(admin/macro123,来自真实 /admin/login)(session)
- admin_client     携带管理员 token 的客户端(session)

注意:session 级 token 被多个用例共享,任何用例不得对共享账号做登出/改密操作;
需要登出验证的用例应自行登录一次性 token(见 tests/test_login.py 的登出用例)。
"""
import pytest

from config.settings import Settings, load_settings
from utils.http_client import ApiClient
from utils.logger import get_logger

log = get_logger("fixtures.session")


@pytest.fixture(scope="session")
def settings() -> Settings:
    """全局配置(Pydantic 模型,启动时完成类型校验)。"""
    return load_settings()


@pytest.fixture(scope="session")
def gateway_up(settings: Settings) -> bool:
    """网关健康门禁:运行前探测网关可达性,不可达则终止并给出指引。

    这不是 Mock:只是环境自检。真实 API 测试的前提就是服务已启动,
    与其让几十个用例齐刷刷报 ConnectionError,不如一条清晰的退出信息。
    探测接口选用无需鉴权的 GET /mall-portal/product/categoryTreeList,
    网关在线时任何 HTTP 状态码(含 404/500)都视为可达。
    """
    import requests

    url = f"{settings.gateway.base_url}{settings.portal('/product/categoryTreeList')}"
    try:
        requests.get(url, timeout=5)
    except requests.exceptions.ConnectionError as exc:
        pytest.exit(
            f"\n网关不可达: {url}\n"
            f"真实 API 测试需要 mall-swarm 服务已启动,请检查:\n"
            f"  1) 网关 java -jar mall-gateway/target/*.jar(端口 8201)\n"
            f"  2) 相关服务 mall-auth(8401) / mall-portal(8085) / mall-search(8081) / mall-admin(8080)\n"
            f"  3) Nacos/Redis/MySQL 等中间件(详见 README.md 前置条件)\n"
            f"原始错误: {exc}"
        )
    except requests.exceptions.Timeout as exc:
        pytest.exit(f"\n网关响应超时: {url}\n原始错误: {exc}")
    log.info("网关可达: %s", settings.gateway.base_url)
    return True


@pytest.fixture(scope="session")
def anon_client(settings: Settings, gateway_up: bool) -> ApiClient:
    """无鉴权的 HTTP 客户端(公共接口、登录接口用)。"""
    client = ApiClient(
        base_url=settings.gateway.base_url,
        timeout=settings.gateway.timeout,
        retry=settings.gateway.retry,
        logger=log,
    )
    yield client
    client.close()


def _login_and_extract(client: ApiClient, path: str, params=None, json=None) -> dict:
    """执行登录并校验成功,返回 data 中的 token/tokenHead 字典。"""
    resp = client.post(path, params=params, json=json)
    payload = resp.json() if resp.headers.get("content-type", "").find("json") >= 0 else {}
    if resp.status_code != 200 or payload.get("code") != 200:
        raise AssertionError(
            f"登录失败: POST {path}\nstatus={resp.status_code}\nbody={resp.text[:2000]}"
        )
    data = payload.get("data") or {}
    if not data.get("token"):
        raise AssertionError(f"登录响应缺少 token: {payload}")
    return data


@pytest.fixture(scope="session")
def member_token(settings: Settings, anon_client: ApiClient) -> dict:
    """前台会员登录(真实 POST /mall-portal/sso/login),返回 {token, tokenHead}。"""
    account = settings.accounts.member
    return _login_and_extract(
        anon_client,
        settings.portal("/sso/login"),
        params={"username": account.username, "password": account.password},
    )


@pytest.fixture(scope="session")
def member_client(settings: Settings, anon_client: ApiClient, member_token: dict) -> ApiClient:
    """携带会员 token 的客户端(购物车/订单/会员接口用)。"""
    client = ApiClient(
        base_url=settings.gateway.base_url,
        timeout=settings.gateway.timeout,
        retry=settings.gateway.retry,
        token=member_token["token"],
        token_head=member_token.get("tokenHead") or "Bearer",
        logger=log,
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def admin_token(settings: Settings, anon_client: ApiClient) -> dict:
    """后台管理员登录(真实 POST /mall-admin/admin/login,JSON body)。"""
    account = settings.accounts.admin
    return _login_and_extract(
        anon_client,
        settings.admin("/admin/login"),
        json={"username": account.username, "password": account.password},
    )


@pytest.fixture(scope="session")
def admin_client(settings: Settings, anon_client: ApiClient, admin_token: dict) -> ApiClient:
    """携带管理员 token 的客户端(后台接口用)。"""
    client = ApiClient(
        base_url=settings.gateway.base_url,
        timeout=settings.gateway.timeout,
        retry=settings.gateway.retry,
        token=admin_token["token"],
        token_head=admin_token.get("tokenHead") or "Bearer",
        logger=log,
    )
    yield client
    client.close()
