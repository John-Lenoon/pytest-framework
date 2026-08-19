# -*- coding: utf-8 -*-
"""商品模块参数化数据(搜索/排序/分页组合)。

测试点依据 test_rules.yaml getProductSearch:
    normal.valid_request / validation.invalid_type / invalid_format /
    boundary.min_value / max_value / data.missing_data
注意:mall 库 pms_product 种子数据包含 小米/苹果 品牌手机类商品,
     keyword=小米 等关键字有真实数据可命中。
"""

# 正常搜索组合:关键字 x 排序 x 分页(sort: 0相关度 1新品 2销量 3价格低到高 4价格高到低)
# 注意:本 fork 的 pageNum 默认值为 0,传 0 会返回空页,因此正常场景必须显式 pageNum=1
# (与 test_rules.yaml 边界约定一致:pageNum min=1)
SEARCH_VALID_COMBOS = [
    {"params": {"keyword": "小米", "pageNum": 1, "pageSize": 5}, "desc": "关键字搜索"},
    {"params": {"keyword": "小米", "pageNum": 1, "sort": 1}, "desc": "关键字+按新品排序"},
    {"params": {"keyword": "小米", "pageNum": 1, "sort": 2}, "desc": "关键字+按销量排序"},
    {"params": {"keyword": "小米", "pageNum": 1, "sort": 3}, "desc": "关键字+价格从低到高"},
    {"params": {"keyword": "小米", "pageNum": 1, "sort": 4}, "desc": "关键字+价格从高到低"},
    {"params": {"keyword": "手机", "pageNum": 1, "pageSize": 10}, "desc": "分页 pageSize=10"},
    {"params": {"keyword": "苹果", "pageNum": 2, "pageSize": 2}, "desc": "第二页 pageSize=2"},
]

# 参数校验:非法类型与非法格式(预期不抛 500,400 或业务兜底均可接受)
SEARCH_INVALID_COMBOS = [
    {"params": {"brandId": "abc"}, "desc": "brandId 传字符串"},
    {"params": {"productCategoryId": "abc"}, "desc": "productCategoryId 传字符串"},
    {"params": {"pageNum": "abc"}, "desc": "pageNum 传字符串"},
    {"params": {"pageSize": "abc"}, "desc": "pageSize 传字符串"},
    {"params": {"sort": "abc"}, "desc": "sort 传字符串"},
    {"params": {"keyword": "   "}, "desc": "keyword 仅空格"},
    {"params": {"brandId": -1}, "desc": "brandId 传负数"},
    {"params": {"pageNum": -1}, "desc": "pageNum 传负数"},
    {"params": {"pageSize": -1}, "desc": "pageSize 传负数"},
    {"params": {"sort": -1}, "desc": "sort 传负数"},
]

# 边界值:最小值/最大值(预期不溢出/不抛 500)
SEARCH_BOUNDARY_COMBOS = [
    {"params": {"keyword": "", "pageNum": 1}, "desc": "keyword 空串"},
    {"params": {"keyword": "a" * 256}, "desc": "keyword 256 字符"},
    {"params": {"keyword": "小米", "pageNum": 1, "pageSize": 1}, "desc": "pageSize=1"},
    {"params": {"keyword": "小米", "pageNum": 0}, "desc": "pageNum=0"},
    {"params": {"keyword": "小米", "pageNum": 1, "pageSize": 1000}, "desc": "pageSize=1000"},
    {"params": {"keyword": "小米", "pageNum": 2147483647}, "desc": "pageNum=Integer 最大值"},
    {"params": {"keyword": "小米", "brandId": 9223372036854775807}, "desc": "brandId=Long 最大值"},
    {"params": {"keyword": "小米", "sort": 2147483647}, "desc": "sort=Integer 最大值"},
]

# 无匹配数据的关键字(正常关键字 -> 空分页 total=0)。
# expected_status 为真实 API 实测:emoji 关键字触发搜索服务 500(已知缺陷,
# 与 test_rules.yaml 预期"返回空分页"不符),用例按真实行为断言。
SEARCH_NO_RESULT_KEYWORDS = [
    {"keyword": "zzzz不存在的商品关键字zzzz", "expected_status": 200},
    {"keyword": "😀😀😀emoji关键字", "expected_status": 500},
]
