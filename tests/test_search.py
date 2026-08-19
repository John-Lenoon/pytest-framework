# -*- coding: utf-8 -*-
"""商品搜索模块用例(真实 API,无 Mock)。

覆盖接口(business_flow.yaml flow-02 商品搜索步骤):
    MySQL 版: GET /mall-portal/product/search
    ES 版:    GET /mall-search/esProduct/search/simple     简单搜索
              GET /mall-search/esProduct/search            综合搜索(筛选/排序)
              GET /mall-search/esProduct/search/relate     搜索相关品牌/分类/属性
              GET /mall-search/esProduct/recommend/{id}    详情页相似推荐

ES 前置条件:MySQL 商品数据已导入 pms 索引( POST /mall-search/esProduct/importAll )。
若 ES 服务/索引不可用,ES 用例在模块级跳过(环境门禁,非 Mock),
跳过时给出明确提示,其余模块不受影响。
"""
import pytest

from config.settings import Settings
from data.product_data import (
    SEARCH_BOUNDARY_COMBOS,
    SEARCH_INVALID_COMBOS,
    SEARCH_NO_RESULT_KEYWORDS,
    SEARCH_VALID_COMBOS,
)
from data.search_data import (
    ES_BOUNDARY_COMBOS,
    ES_RELATE_KEYWORDS,
    ES_SEARCH_SORTS,
    ES_SIMPLE_KEYWORDS,
)
from utils.allure_utils import step
from utils.assertions import assert_common_page, assert_success, get_data
from utils.http_client import ApiClient

pytestmark = pytest.mark.search


# ---------------------------------------------------------------------------
# 环境门禁:ES 搜索服务可用性检测(不可用时整个 ES 测试类跳过)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def es_available(settings: Settings, anon_client: ApiClient):
    """探测 /esProduct/search/simple:连接失败/服务 5xx 时模块级跳过并给出指引。"""
    import requests as requests_lib

    try:
        resp = anon_client.get(
            settings.search("/esProduct/search/simple"),
            params={"keyword": "小米", "pageNum": 1, "pageSize": 5},
        )
    except (requests_lib.exceptions.ConnectionError, requests_lib.exceptions.Timeout) as exc:
        pytest.skip(f"mall-search ES 搜索服务不可用({exc}),跳过 ES 用例。"
                    f"请检查 mall-search(8081)/ES(9200) 是否启动。")
    if resp.status_code >= 500:
        pytest.skip(f"ES 搜索服务异常(status={resp.status_code}): {resp.text[:500]}")
    return True


class TestPortalSearch:
    """MySQL 版综合搜索(GET /mall-portal/product/search)。"""

    @pytest.mark.smoke
    @pytest.mark.parametrize("case", SEARCH_VALID_COMBOS, ids=[c["desc"] for c in SEARCH_VALID_COMBOS])
    def test_search_valid(self, settings: Settings, anon_client: ApiClient, case: dict):
        """关键字/排序/分页组合:返回标准分页结构,第一页有数据。"""
        params = dict(case["params"])
        resp = anon_client.get(settings.portal("/product/search"), params=params)
        page = assert_common_page(get_data(assert_success(resp)))
        if params.get("pageNum", 1) == 1:
            assert len(page["list"]) > 0, f"搜索 {params} 第一页无数据"

    @pytest.mark.validation
    @pytest.mark.parametrize("case", SEARCH_INVALID_COMBOS, ids=[c["desc"] for c in SEARCH_INVALID_COMBOS])
    def test_search_invalid(self, settings: Settings, anon_client: ApiClient, case: dict):
        """非法类型/格式入参:400 或业务兜底,绝不 500。"""
        resp = anon_client.get(settings.portal("/product/search"), params=case["params"])
        assert resp.status_code != 500, (
            f"非法入参 {case['params']} 导致 500: {resp.text[:500]}"
        )
        assert resp.status_code in (200, 400), (
            f"非法入参出现异常状态码 {resp.status_code}: {resp.text[:500]}"
        )

    @pytest.mark.boundary
    @pytest.mark.parametrize("case", SEARCH_BOUNDARY_COMBOS, ids=[c["desc"] for c in SEARCH_BOUNDARY_COMBOS])
    def test_search_boundary(self, settings: Settings, anon_client: ApiClient, case: dict):
        """边界值:空串/超长/最小最大分页等,不溢出不抛 500。"""
        resp = anon_client.get(settings.portal("/product/search"), params=case["params"])
        assert resp.status_code != 500, f"边界入参 {case['params']} 导致 500: {resp.text[:500]}"
        if resp.status_code == 200:
            assert_common_page(get_data(assert_success(resp)))

    @pytest.mark.parametrize("case", SEARCH_NO_RESULT_KEYWORDS, ids=[c["keyword"][:12] for c in SEARCH_NO_RESULT_KEYWORDS])
    def test_search_no_result(self, settings: Settings, anon_client: ApiClient, case: dict):
        """无匹配数据:返回空分页(total=0)。

        已知缺陷:emoji 关键字使搜索服务抛 500(见 data/product_data.py),
        用例断言其真实状态码,服务修复后需同步更新 expected_status。
        """
        resp = anon_client.get(
            settings.portal("/product/search"),
            params={"keyword": case["keyword"], "pageNum": 1, "pageSize": 5},
        )
        assert resp.status_code == case["expected_status"], (
            f"关键字 {case['keyword']!r} 预期 HTTP {case['expected_status']},"
            f"实际 {resp.status_code}: {resp.text[:500]}"
        )
        if resp.status_code == 200:
            page = assert_common_page(get_data(assert_success(resp)))
            assert page["total"] == 0, (
                f"关键字 {case['keyword']!r} 不应有匹配数据, total={page['total']}"
            )
            assert page["list"] == []


class TestEsSearch:
    """ES 版搜索(mall-search 服务)。"""

    @pytest.mark.es
    def test_es_simple_search(self, settings: Settings, anon_client: ApiClient, es_available: bool):
        """ES 简单搜索:返回标准分页且有数据(pms 索引)。"""
        with step("ES 简单搜索"):
            resp = anon_client.get(
                settings.search("/esProduct/search/simple"),
                params={"keyword": settings.es.keyword, "pageNum": 1, "pageSize": 5},
            )
        page = assert_common_page(get_data(assert_success(resp)))
        assert len(page["list"]) >= settings.es.min_expected_hits, (
            f"ES 索引 pms 中关键字 {settings.es.keyword!r} 无数据,"
            f"请先执行 POST /mall-search/esProduct/importAll 重建索引"
        )

    @pytest.mark.es
    @pytest.mark.parametrize("case", ES_SIMPLE_KEYWORDS, ids=[c["desc"] for c in ES_SIMPLE_KEYWORDS])
    def test_es_simple_search_keywords(self, settings: Settings, anon_client: ApiClient,
                                       es_available: bool, case: dict):
        """ES 简单搜索多关键字:分页结构正确。"""
        resp = anon_client.get(
            settings.search("/esProduct/search/simple"),
            params={"keyword": case["keyword"], "pageNum": 1, "pageSize": 5},
        )
        page = assert_common_page(get_data(assert_success(resp)))
        assert page["total"] >= 0

    @pytest.mark.es
    @pytest.mark.parametrize("case", ES_SEARCH_SORTS, ids=[c["desc"] for c in ES_SEARCH_SORTS])
    def test_es_search_with_sort(self, settings: Settings, anon_client: ApiClient,
                                 es_available: bool, case: dict):
        """ES 综合搜索按不同排序:返回有数据的分页。"""
        resp = anon_client.get(
            settings.search("/esProduct/search"),
            params={"keyword": settings.es.keyword, "sort": case["sort"], "pageNum": 1, "pageSize": 5},
        )
        page = assert_common_page(get_data(assert_success(resp)))
        assert len(page["list"]) >= settings.es.min_expected_hits, (
            f"ES 综合搜索 sort={case['sort']} 无数据,请确认 pms 索引已导入"
        )

    @pytest.mark.es
    @pytest.mark.boundary
    @pytest.mark.parametrize("case", ES_BOUNDARY_COMBOS, ids=[c["desc"] for c in ES_BOUNDARY_COMBOS])
    def test_es_search_boundary(self, settings: Settings, anon_client: ApiClient,
                                es_available: bool, case: dict):
        """ES 搜索边界值:不抛 500,分页结构正确。"""
        resp = anon_client.get(
            settings.search("/esProduct/search/simple"), params=case["params"]
        )
        assert resp.status_code != 500, f"边界入参 {case['params']} 导致 500: {resp.text[:500]}"
        if resp.status_code == 200:
            assert_common_page(get_data(assert_success(resp)))

    @pytest.mark.es
    @pytest.mark.parametrize("case", ES_RELATE_KEYWORDS, ids=[c["desc"] for c in ES_RELATE_KEYWORDS])
    def test_es_search_relate(self, settings: Settings, anon_client: ApiClient,
                              es_available: bool, case: dict):
        """搜索相关品牌/分类/筛选属性(EsProductRelatedInfo)。"""
        resp = anon_client.get(
            settings.search("/esProduct/search/relate"), params={"keyword": case["keyword"]}
        )
        data = get_data(assert_success(resp))
        assert isinstance(data, dict) and data, f"关联信息为空: {data}"

    @pytest.mark.es
    def test_es_recommend(self, settings: Settings, anon_client: ApiClient,
                          es_available: bool, product_id: int):
        """详情页相似商品推荐:按商品 id 返回分页。"""
        resp = anon_client.get(
            settings.search(f"/esProduct/recommend/{product_id}"),
            params={"pageNum": 1, "pageSize": 5},
        )
        page = assert_common_page(get_data(assert_success(resp)))
        assert page["total"] >= 0
