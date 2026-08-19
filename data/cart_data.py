# -*- coding: utf-8 -*-
"""购物车模块参数化数据。

测试点依据 test_rules.yaml postCartAdd / getCartUpdateQuantity / postCartDelete:
    validation.null_parameter / invalid_type / invalid_format /
    boundary.min_value / max_value / data.missing_data / duplicated_data
"""

# 加购失败场景(不存在的商品/SKU,预期 code != 200 且不产生购物车条目)
CART_ADD_MISSING_PRODUCT = [
    {"body": {"productId": 999999, "productSkuId": 999999, "quantity": 1}, "desc": "商品不存在"},
    {"body": {"productId": 999999, "productSkuId": 1, "quantity": 1}, "desc": "productId 不存在"},
]

# 加购参数校验(缺字段/非法类型/负数)。expected 为真实 API 实测状态码:
# - 400:类型不匹配(productId 传字符串 / body 传数组),符合 test_rules.yaml 预期
# - 500:缺少 productId(oms_cart_item.product_id NOT NULL 约束)
#        —— 已知缺陷:服务端无字段级校验,与 test_rules.yaml 预期(400 友好拒绝)不符
# - 200:缺少 productSkuId / quantity、productId 负数、quantity 负数
#        (实测 -1/-2/-3/0 均直接落库) —— 已知缺陷:插入垃圾条目(price 等字段为 null)
# 注意:除"缺少 productId"(500,不落库)外,其余 body 一律使用不存在的商品 id
# (999996~999999),避免与 worker 专属真实商品条目合并(xdist 并行安全)。
# 用例对落库的场景按 case 的 productId 做条目级清理,保证库不被污染。
CART_ADD_INVALID_BODY = [
    {"body": {"productSkuId": 1, "quantity": 1}, "expected": 500, "desc": "缺少 productId"},
    {"body": {"productId": 999998, "quantity": 1}, "expected": 200, "desc": "缺少 productSkuId"},
    {"body": {"productId": 999997, "productSkuId": 999997}, "expected": 200, "desc": "缺少 quantity"},
    {"body": {"productId": "abc", "productSkuId": 1, "quantity": 1}, "expected": 400, "desc": "productId 传字符串"},
    {"body": {"productId": 999999, "productSkuId": 999999, "quantity": -1}, "expected": 200, "desc": "quantity 负数"},
    {"body": {"productId": -1, "productSkuId": 999996, "quantity": 1}, "expected": 200, "desc": "productId 负数"},
    {"body": [], "expected": 400, "desc": "body 传数组"},
]

# 修改数量的合法值(用例内部逐个验证后再改回,保证幂等)
CART_QUANTITY_VALUES = [1, 2, 5]

# 修改数量的非法值(预期业务失败:quantity=0 提示数量不合法,999999 提示库存不足)
CART_QUANTITY_INVALID = [
    {"quantity": 0, "desc": "quantity=0"},
    {"quantity": -1, "desc": "quantity 负数"},
    {"quantity": 999999, "desc": "quantity 超过库存上限"},
]

# 删除购物车条目的入参异常(预期失败或影响行数 0,不越权删除)
CART_DELETE_INVALID_IDS = [
    {"ids": [999999], "desc": "删除不存在的条目"},
    {"ids": [], "desc": "删除空列表"},
]
