# -*- coding: utf-8 -*-
"""Faker 数据生成工具:随机但合法的测试数据(中文环境)。

用途:
- 注册新会员(用户名/密码/手机号)
- 生成收货地址 payload(省份/城市/区/街道/邮编/姓名)
- 所有生成值均满足接口 DTO 约束:
    username 长度 <= 64;telephone 11 位数字(ums_member.phone 有唯一索引);
    中文姓名/地址来自 Faker zh_CN 词库。
"""
import random
import string

from faker import Faker

_FAKER = Faker("zh_CN")


def faker() -> Faker:
    """全局共享的 Faker 实例(zh_CN)。"""
    return _FAKER


def gen_username(prefix: str = "uitest") -> str:
    """生成唯一用户名:前缀 + 8 位随机数字(长度远小于 64)。"""
    digits = "".join(random.choices(string.digits, k=8))
    return f"{prefix}_{digits}"


def gen_password() -> str:
    """生成固定规则密码:字母开头 + 数字,满足多数密码强度要求。"""
    letters = "".join(random.choices(string.ascii_letters, k=8))
    digits = "".join(random.choices(string.digits, k=4))
    return f"{letters}{digits}"


def gen_telephone() -> str:
    """生成 11 位手机号(1 开头),避免 Faker 号码带空格/分隔符导致校验失败。"""
    return "1" + "".join(random.choices(string.digits, k=10))


def gen_name() -> str:
    """生成中文姓名。"""
    return _FAKER.name()


def gen_address_payload(**overrides) -> dict:
    """生成收货地址 payload,字段与 UmsMemberReceiveAddress 对齐。

    defaultStatus 默认 0(非默认地址),可传 overrides 覆盖任意字段。
    """
    payload = {
        "name": gen_name(),
        "phoneNumber": gen_telephone(),
        "defaultStatus": 0,
        "postCode": _FAKER.postcode(),
        "province": _FAKER.province(),
        "city": _FAKER.city(),
        "region": _FAKER.district(),
        "detailAddress": _FAKER.street_address(),
    }
    payload.update(overrides)
    return payload


def gen_member_data(prefix: str = "uitest") -> dict:
    """一次生成注册新会员所需的全部数据。"""
    return {
        "username": gen_username(prefix),
        "password": gen_password(),
        "telephone": gen_telephone(),
    }
