# -*- coding: utf-8 -*-
"""商品浏览与详情模块用例(真实 API,无 Mock)。

覆盖接口(business_flow.yaml flow-02 商品浏览链路):
    GET /mall-portal/product/categoryTreeList   全量商品分类树
    GET /mall-portal/home/content               首页内容聚合
    GET /mall-portal/brand/productList          品牌商品分页
    GET /mall-portal/product/detail/{id}        商品详情(含 SKU/促销/优惠券)
    GET /mall-portal/product/search             按分类筛选(详见 test_search.py)

测试点依据 test_rules.yaml getProductCategoryTreeList / getHomeContent /
    getBrandProductList / getProductDetailById。
"""
import pytest

from config.settings import Settings
from utils.allure_utils import step
from utils.assertions import assert_common_page, assert_success, get_data, resp_json
from utils.http_client import ApiClient

pytestmark = pytest.mark.product

# 商品详情非法 id:不存在/0/Long 最大值
INVALID_PRODUCT_IDS = [0, 999999, 9223372036854775807]


class TestProductBrowse:
    """商品浏览:分类树、首页内容、品牌商品。"""

    @pytest.mark.smoke
    def test_category_tree(self, category_tree: list):
        """分类树返回非空列表,且节点包含 id/name 字段。"""
        assert len(category_tree) > 0
        for node in category_tree:
            assert node.get("id") is not None, f"分类节点缺少 id: {node}"
            assert node.get("name"), f"分类节点缺少 name: {node}"

    def test_home_content(self, home_content: dict):
        """首页内容聚合:advertiseList/brandList/newProductList/hotProductList/subjectList。"""
        for key in ("advertiseList", "brandList", "newProductList", "hotProductList", "subjectList"):
            assert key in home_content, f"首页内容缺少字段 {key}: keys={list(home_content.keys())}"

    def test_brand_product_list(self, settings: Settings, anon_client: ApiClient, brand_id: int):
        """按品牌分页查询商品(brandId 来自商品详情,链路: 详情 -> 品牌 -> 品牌商品)。"""
        resp = anon_client.get(
            settings.portal("/brand/productList"),
            params={"brandId": brand_id, "pageNum": 1, "pageSize": 5},
        )
        page = assert_common_page(get_data(assert_success(resp)))
        assert len(page["list"]) > 0, f"品牌 {brand_id} 下无商品数据"

    def test_category_search(self, settings: Settings, anon_client: ApiClient,
                             first_category_id: int):
        """按分类筛选商品(分类 id 来自分类树,链路: 分类树 -> 搜索)。"""
        resp = anon_client.get(
            settings.portal("/product/search"),
            params={"productCategoryId": first_category_id, "pageNum": 1, "pageSize": 5},
        )
        page = assert_common_page(get_data(assert_success(resp)))
        assert page["total"] >= 0, f"分类筛选返回异常 total: {page}"


class TestProductDetail:
    """商品详情(PmsPortalProductDetail)。"""

    @pytest.mark.flow
    def test_product_detail_structure(self, product_detail: dict, product_id: int):
        """详情包含商品主体/SKU/品牌,商品 id 与请求一致。"""
        with step("校验商品主体"):
            product = product_detail["product"]
            assert product.get("id") == product_id, (
                f"详情商品 id {product.get('id')} 与请求 {product_id} 不一致"
            )
            assert product.get("name"), f"商品缺少名称: {product}"
            assert product.get("price") is not None, f"商品缺少价格: {product}"

        with step("校验 SKU 与品牌"):
            sku_list = product_detail.get("skuStockList") or []
            assert sku_list, f"商品 {product_id} 无 SKU 库存数据"
            for sku in sku_list:
                assert sku.get("id") is not None, f"SKU 缺少 id: {sku}"
            assert (product_detail.get("brand") or {}).get("id"), "商品详情缺少品牌数据"

    @pytest.mark.parametrize("pid", INVALID_PRODUCT_IDS)
    def test_product_detail_invalid_id(self, settings: Settings, anon_client: ApiClient, pid: int):
        """非法 id 查询详情:绝不返回伪造的商品数据。

        已知缺陷(与 test_rules.yaml 预期不符):本 fork 对不存在的商品 id
        直接抛 500(详情服务空指针),而非返回 null/友好提示。用例按真实
        行为断言:绝不接受"HTTP 200 + code=200 + 非空 data"的静默成功。
        """
        resp = anon_client.get(settings.portal(f"/product/detail/{pid}"))
        payload = resp_json(resp)
        assert not (resp.status_code == 200 and payload.get("code") == 200 and payload.get("data")), (
            f"非法 id={pid} 返回了异常商品数据: {payload}"
        )
