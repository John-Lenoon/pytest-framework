# -*- coding: utf-8 -*-
"""搜索模块参数化数据(portal MySQL 搜索 + mall-search ES 搜索)。

ES 搜索接口(mall-search 服务,经网关 /mall-search/esProduct/...):
    /esProduct/search/simple   简单搜索(keyword, pageNum, pageSize)
    /esProduct/search          综合搜索(keyword, brandId, productCategoryId, pageNum, pageSize, sort)
    /esProduct/search/relate   搜索相关品牌/分类/筛选属性(keyword)
    /esProduct/recommend/{id}  详情页相似推荐
测试点依据 test_rules.yaml getEsProductSearch / getEsProductSearchSimple /
    getEsProductSearchRelate / getEsProductRecommendById。
"""

# ES 简单搜索关键字(seed 数据中含 小米/苹果 品牌)
ES_SIMPLE_KEYWORDS = [
    {"keyword": "小米", "desc": "关键字 小米"},
    {"keyword": "手机", "desc": "关键字 手机"},
    {"keyword": "苹果", "desc": "关键字 苹果"},
    {"keyword": "", "desc": "空关键字(全量)"},
]

# ES 综合搜索排序组合(sort: 0相关度 1新品 2销量 3价格低到高 4价格高到低)
ES_SEARCH_SORTS = [
    {"sort": 0, "desc": "按相关度"},
    {"sort": 1, "desc": "按新品"},
    {"sort": 3, "desc": "价格从低到高"},
    {"sort": 4, "desc": "价格从高到低"},
]

# ES 搜索关联信息关键字
ES_RELATE_KEYWORDS = [
    {"keyword": "小米", "desc": "关键字 小米"},
    {"keyword": "手机", "desc": "关键字 手机"},
]

# ES 简单搜索边界(pageNum=0 为默认值,pageSize=1 最小合法值)
ES_BOUNDARY_COMBOS = [
    {"params": {"keyword": "小米", "pageNum": 1, "pageSize": 1}, "desc": "pageSize=1"},
    {"params": {"keyword": "小米", "pageNum": 0}, "desc": "pageNum=0(默认值)"},
    {"params": {"keyword": "小米", "pageNum": 1, "pageSize": 100}, "desc": "pageSize=100"},
]
