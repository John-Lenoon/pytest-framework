# -*- coding: utf-8 -*-
"""登录认证模块用例(真实 API,无 Mock)。

覆盖接口(business_flow.yaml flow-01 登录认证链路):
    POST /mall-portal/sso/login      前台会员登录(Feign -> mall-auth)
    POST /mall-portal/sso/info       会员信息(鉴权)
    POST /mall-portal/sso/logout     会员登出(清除 Redis 会话)
    POST /mall-admin/admin/login     后台管理员登录(Feign -> mall-auth)
    GET  /mall-admin/admin/info      管理员信息(鉴权)
    POST /mall-auth/auth/login       统一认证核心入口(clientId 区分客户端)

测试点依据 test_rules.yaml postSsoLogin / postAdminLogin / postAuthLogin /
    getAdminInfo / getSsoInfo,以及网关 Sa-Token 401 预期:
    401=暂未登录或token已经过期。

重要约定:共享的 session 级 token(member_token/admin_token)不可被登出用例使用;
登出类用例内部自行登录一次性 token 验证。
"""
import pytest

from config.settings import Settings
from data.login_data import (
    ADMIN_LOGIN_FAIL,
    AUTH_HEADER_CASES,
    AUTH_LOGIN_CLIENTS,
    MEMBER_LOGIN_BOUNDARY,
    MEMBER_LOGIN_FAIL,
)
from utils.allure_utils import step
from utils.assertions import (
    assert_failed,
    assert_gateway_unauthorized,
    assert_msg_contains,
    assert_success,
    get_data,
)
from utils.http_client import ApiClient

pytestmark = pytest.mark.login


def _assert_login_failed(resp) -> None:
    """登录失败断言:HTTP 400(缺参/校验)或 HTTP 200 + code != 200(业务失败)。"""
    assert resp.status_code in (200, 400), f"登录失败场景出现异常状态码 {resp.status_code}: {resp.text[:500]}"
    if resp.status_code == 200:
        assert_failed(resp)


class TestMemberLogin:
    """前台会员登录(POST /mall-portal/sso/login)。"""

    @pytest.mark.smoke
    def test_member_login_success(self, settings: Settings, anon_client: ApiClient):
        """正常登录:返回 token 与 tokenHead(business_flow flow-01 登录步骤)。"""
        account = settings.accounts.member
        with step("会员登录"):
            resp = anon_client.post(
                settings.portal("/sso/login"),
                params={"username": account.username, "password": account.password},
            )
        payload = assert_success(resp)
        token_map = payload.get("data") or {}
        assert token_map.get("token"), f"登录响应缺少 token: {payload}"
        assert "tokenHead" in token_map, f"登录响应缺少 tokenHead: {payload}"

    @pytest.mark.parametrize("case", MEMBER_LOGIN_FAIL, ids=[c["desc"] for c in MEMBER_LOGIN_FAIL])
    def test_member_login_fail(self, settings: Settings, anon_client: ApiClient, case: dict):
        """失败登录:用户名不存在/密码错误/空用户名/空密码 -> 不生成 token。"""
        resp = anon_client.post(
            settings.portal("/sso/login"),
            params={"username": case["username"], "password": case["password"]},
        )
        _assert_login_failed(resp)

    @pytest.mark.boundary
    @pytest.mark.parametrize("case", MEMBER_LOGIN_BOUNDARY, ids=[c["desc"] for c in MEMBER_LOGIN_BOUNDARY])
    def test_member_login_boundary(self, settings: Settings, anon_client: ApiClient, case: dict):
        """64 字符超长用户名/密码:不抛 500、不产生脏写。"""
        resp = anon_client.post(
            settings.portal("/sso/login"),
            params={"username": case["username"], "password": case["password"]},
        )
        assert resp.status_code != 500, f"超长入参导致 500: {resp.text[:500]}"

    def test_member_info_with_token(self, settings: Settings, member_client: ApiClient):
        """登录后查询会员信息:token -> memberId -> UmsMember。"""
        resp = member_client.get(settings.portal("/sso/info"))
        payload = assert_success(resp)
        member = payload.get("data") or {}
        assert member.get("username") == settings.accounts.member.username, (
            f"会员信息不匹配: {member}"
        )

    def test_member_logout_clears_session(self, settings: Settings, anon_client: ApiClient):
        """登出后原 token 立即失效(Redis 会话被清除),再次访问应 401。

        自行登录一次性 token,避免污染共享的 session 级 member_token。
        """
        account = settings.accounts.member
        login_resp = anon_client.post(
            settings.portal("/sso/login"),
            params={"username": account.username, "password": account.password},
        )
        token = get_data(assert_success(login_resp))["token"]

        with step("携带一次性 token 登出"):
            logout_resp = anon_client.post(
                settings.portal("/sso/logout"), headers={"Authorization": f"Bearer {token}"}
            )
            assert_success(logout_resp)

        with step("登出后原 token 访问应 401"):
            info_resp = anon_client.get(
                settings.portal("/sso/info"), headers={"Authorization": f"Bearer {token}"}
            )
            assert_gateway_unauthorized(info_resp)


class TestAdminLogin:
    """后台管理员登录(POST /mall-admin/admin/login)。"""

    def test_admin_login_success(self, settings: Settings, anon_client: ApiClient):
        """正常登录:返回 token 与 tokenHead。"""
        account = settings.accounts.admin
        resp = anon_client.post(
            settings.admin("/admin/login"),
            json={"username": account.username, "password": account.password},
        )
        payload = assert_success(resp)
        token_map = payload.get("data") or {}
        assert token_map.get("token"), f"登录响应缺少 token: {payload}"

    @pytest.mark.parametrize("case", ADMIN_LOGIN_FAIL, ids=[c["desc"] for c in ADMIN_LOGIN_FAIL])
    def test_admin_login_fail(self, settings: Settings, anon_client: ApiClient, case: dict):
        """失败登录:管理员不存在/密码错误 -> 不生成 token。"""
        resp = anon_client.post(
            settings.admin("/admin/login"),
            json={"username": case["username"], "password": case["password"]},
        )
        _assert_login_failed(resp)

    def test_admin_info_with_token(self, settings: Settings, admin_client: ApiClient):
        """登录后获取管理员信息:data 含 username。"""
        resp = admin_client.get(settings.admin("/admin/info"))
        payload = assert_success(resp)
        info = payload.get("data") or {}
        assert info.get("username") == settings.accounts.admin.username, f"管理员信息不匹配: {info}"


class TestAuthLogin:
    """统一认证入口(POST /mall-auth/auth/login,clientId 区分客户端)。"""

    @pytest.mark.parametrize("case", AUTH_LOGIN_CLIENTS, ids=[c["desc"] for c in AUTH_LOGIN_CLIENTS])
    def test_auth_login(self, settings: Settings, anon_client: ApiClient, case: dict):
        """portal-app / admin-web 两个客户端经统一认证登录。"""
        resp = anon_client.post(
            settings.auth("/auth/login"),
            params={
                "clientId": case["clientId"],
                "username": case["username"],
                "password": case["password"],
            },
        )
        payload = assert_success(resp)
        token_map = payload.get("data") or {}
        assert token_map.get("token"), f"认证登录响应缺少 token: {payload}"

    def test_auth_login_wrong_password(self, settings: Settings, anon_client: ApiClient):
        """统一认证密码错误:失败且不返回 token。"""
        resp = anon_client.post(
            settings.auth("/auth/login"),
            params={"clientId": "portal-app", "username": "test", "password": "WrongPass123"},
        )
        _assert_login_failed(resp)


class TestPermission:
    """鉴权用例:网关 Sa-Token 401 预期(business_flow 跨链路:登录 token 是所有 auth 接口前提)。"""

    @pytest.mark.permission
    @pytest.mark.parametrize("case", AUTH_HEADER_CASES, ids=[c["desc"] for c in AUTH_HEADER_CASES])
    def test_cart_list_without_valid_token(self, settings: Settings, anon_client: ApiClient, case: dict):
        """无 token / 非法 token / 空 token 访问需登录接口 -> 网关 401。"""
        if case["headers"] is None:
            resp = anon_client.get(settings.portal("/cart/list"))
        else:
            resp = anon_client.get(settings.portal("/cart/list"), headers=case["headers"])
        assert_gateway_unauthorized(resp)
        assert_msg_contains(resp, "登录", "token")

    @pytest.mark.permission
    def test_admin_info_without_token(self, settings: Settings, anon_client: ApiClient):
        """无 token 访问后台接口 -> 网关 401。"""
        resp = anon_client.get(settings.admin("/admin/info"))
        assert_gateway_unauthorized(resp)
