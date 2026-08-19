# -*- coding: utf-8 -*-
"""订单模块参数化数据。

测试点依据 test_rules.yaml postOrderGenerateConfirmOrder / postOrderGenerateOrder /
    postOrderPaySuccess / postOrderCancelUserOrder / getOrderList / getOrderDetailByOrderId:
    validation.null_parameter / invalid_type / invalid_format /
    boundary.min_value / max_value / data.missing_data / duplicated_data

订单状态枚举(前端约定):-1 全部 / 0 待付款 / 1 待发货 / 2 已发货 / 3 已完成 / 4 已关闭
"""

# 生成确认单的非法入参(预期业务失败或反序列化失败,不生成确认单)
CONFIRM_ORDER_INVALID_BODIES = [
    {"body": [], "desc": "cartIds 空列表"},
    {"body": [999999], "desc": "cartIds 不存在"},
    {"body": [999999, -1], "desc": "cartIds 含负数"},
]

# 生成订单的非法入参(缺地址 / 地址不存在,预期业务失败并回滚)
GENERATE_ORDER_MISSING_ADDRESS = [
    {"payload": {"memberReceiveAddressId": None, "useIntegration": 0, "payType": 1},
     "desc": "缺少收货地址(必填)"},
    {"payload": {"memberReceiveAddressId": 999999, "useIntegration": 0, "payType": 1},
     "desc": "收货地址不存在"},
]

# 支付回调参数校验(缺参/非法类型,预期 400 或业务失败)
PAY_SUCCESS_INVALID_PARAMS = [
    {"params": {"payType": 1}, "desc": "缺少 orderId"},
    {"params": {"orderId": 1}, "desc": "缺少 payType"},
    {"params": {"orderId": "abc", "payType": 1}, "desc": "orderId 传字符串"},
    {"params": {"orderId": 1, "payType": "abc"}, "desc": "payType 传字符串"},
]

# 支付方式枚举(1 支付宝 2 微信,paySuccess 的 payType 入参)
PAY_TYPES = [1, 2]

# 订单列表按状态查询(status 覆盖全部枚举)
ORDER_LIST_STATUSES = [
    {"status": -1, "desc": "全部订单"},
    {"status": 0, "desc": "待付款"},
    {"status": 1, "desc": "待发货"},
    {"status": 2, "desc": "已发货"},
    {"status": 3, "desc": "已完成"},
    {"status": 4, "desc": "已关闭"},
]

# 订单详情/操作的非法 id(预期失败或不影响数据,不抛 500)
ORDER_INVALID_IDS = [
    {"order_id": 0, "desc": "orderId=0"},
    {"order_id": 999999, "desc": "orderId 不存在"},
    {"order_id": 9223372036854775807, "desc": "orderId=Long 最大值"},
]
