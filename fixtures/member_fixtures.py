# -*- coding: utf-8 -*-
"""新会员 fixture:走真实注册链路(获取验证码 -> 注册 -> 登录)。

用途:
- 需要独立账号的用例(如清空购物车、会员隔离验证),避免污染内置 test 用户的数据。
- 完整链路本身也是对 getAuthCode / register / login 三个真实接口的验证。

注意:注册的新会员不做删除(真实 API 测试,保留数据便于排查);
Faker 生成的 username/telephone 具有随机性,xdist 多进程下也不会撞唯一索引。
"""
import pytest

from config.settings import Settings
from utils.allure_utils import step
from utils.assertions import assert_success
from utils.faker_utils import gen_member_data
from utils.http_client import ApiClient
from utils.logger import get_logger

log = get_logger("fixtures.member")


@pytest.fixture(scope="session")
def fresh_member(settings: Settings, anon_client: ApiClient) -> dict:
    """注册并登录一个新会员,返回 {username, password, telephone, token, tokenHead}。

    全链路真实接口:
      1. GET  /mall-portal/sso/getAuthCode?telephone=xxx  获取验证码
      2. POST /mall-portal/sso/register                   注册
      3. POST /mall-portal/sso/login                      登录拿 token
    """
    portal = settings.portal
    data = gen_member_data(prefix="uitest")
    log.info("注册新会员: username=%s", data["username"])

    with step("注册新会员"):
        auth_resp = anon_client.get(
            portal("/sso/getAuthCode"), params={"telephone": data["telephone"]}
        )
        auth_payload = assert_success(auth_resp)
        auth_code = auth_payload.get("data")
        assert auth_code, f"获取验证码失败: {auth_payload}"

        reg_resp = anon_client.post(
            portal("/sso/register"),
            params={
                "username": data["username"],
                "password": data["password"],
                "telephone": data["telephone"],
                "authCode": auth_code,
            },
        )
        assert_success(reg_resp)

        login_resp = anon_client.post(
            portal("/sso/login"),
            params={"username": data["username"], "password": data["password"]},
        )
        login_payload = assert_success(login_resp)
        token_map = login_payload.get("data") or {}
        assert token_map.get("token"), f"新会员登录响应缺少 token: {login_payload}"

    data.update(token_map)
    return data


@pytest.fixture(scope="session")
def fresh_member_client(settings: Settings, anon_client: ApiClient, fresh_member: dict) -> ApiClient:
    """携带新会员 token 的客户端(独立账号操作用)。"""
    client = ApiClient(
        base_url=settings.gateway.base_url,
        timeout=settings.gateway.timeout,
        retry=settings.gateway.retry,
        token=fresh_member["token"],
        token_head=fresh_member.get("tokenHead") or "Bearer",
        logger=log,
    )
    yield client
    client.close()
