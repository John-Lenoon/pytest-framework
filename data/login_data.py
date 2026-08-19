# -*- coding: utf-8 -*-
"""登录模块参数化数据。

约定:
- 成功类数据用 settings.accounts 的账号(见 config/settings.yaml),
  这里放失败/边界/多客户端数据。
- ids 由 pytest 自动生成(desc 字段)。
- 测试点依据 back-test/test_rules.yaml 中 postSsoLogin / postAdminLogin / postAuthLogin:
    normal.valid_request / validation.null_parameter / validation.invalid_type /
    validation.invalid_format / boundary.min_value / boundary.max_value / data.missing_data
"""

# 会员登录失败场景:用户名不存在 / 密码错误 / 空用户名 / 空密码(预期 code != 200)
MEMBER_LOGIN_FAIL = [
    {"username": "no_such_user_xyz", "password": "123456", "desc": "用户名不存在"},
    {"username": "test", "password": "WrongPass123", "desc": "密码错误"},
    {"username": "", "password": "123456", "desc": "用户名为空"},
    {"username": "test", "password": "", "desc": "密码为空"},
]

# 会员登录边界:64 字符超长用户名/密码(受 varchar(64) 字段长度限制,不抛异常)
MEMBER_LOGIN_BOUNDARY = [
    {"username": "a" * 64, "password": "123456", "desc": "用户名 64 字符"},
    {"username": "test", "password": "a" * 64, "desc": "密码 64 字符"},
]

# 管理员登录失败场景
ADMIN_LOGIN_FAIL = [
    {"username": "no_such_admin_xyz", "password": "macro123", "desc": "管理员不存在"},
    {"username": "admin", "password": "WrongPass123", "desc": "密码错误"},
]

# mall-auth 统一认证入口的客户端(clientId=portal-app 会员 / admin-app 后台,
# oauth_client_details 种子数据中的真实 client_id,与 mall-admin-web 前端一致)
AUTH_LOGIN_CLIENTS = [
    {"clientId": "portal-app", "username": "test", "password": "123456", "desc": "portal-app 客户端"},
    {"clientId": "admin-app", "username": "admin", "password": "macro123", "desc": "admin-app 客户端"},
]

# 鉴权用例:无 token / 非法 token(网关 Sa-Token 应返回 401)
AUTH_HEADER_CASES = [
    {"headers": None, "desc": "不携带 Authorization 头"},
    {"headers": {"Authorization": "Bearer invalid-token-xyz"}, "desc": "非法 token"},
    {"headers": {"Authorization": "Bearer "}, "desc": "空 token"},
]
