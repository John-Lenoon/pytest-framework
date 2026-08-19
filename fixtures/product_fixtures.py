# -*- coding: utf-8 -*-
"""商品模块 fixture:分类树、搜索、详情、SKU、品牌、首页内容。

数据依赖(全部来自真实接口,无 Mock):
- 分类树     GET /mall-portal/product/categoryTreeList
- 搜索       GET /mall-portal/product/search(默认 keyword=settings.es.keyword)
- 商品详情   GET /mall-portal/product/detail/{id}
- 首页内容   GET /mall-portal/home/content

链路:worker_product -> product_id -> product_detail -> sku_id / brand_id,
对应 business_flow.yaml flow-02(商品浏览 -> 搜索 -> 详情)。

xdist 并行安全(重要):购物车/订单用例共用同一个会员账号,而本 fork 的
/cart/add 对同一 productId+productSkuId 的重复添加会合并条目;若两个 worker
并行操作同一商品,会出现条目被对方删除、数量被对方累加的串扰(实测 -n 2
复现)。因此 worker_product 按 worker id 从搜索结果中为每个 worker 挑选
一个不同的商品/SKU:worker 内顺序执行互不冲突,worker 间商品不同也互不冲突。
"""
import pytest

from config.settings import Settings
from utils.assertions import assert_success, get_data
from utils.http_client import ApiClient
from utils.logger import get_logger

log = get_logger("fixtures.product")

_MSG_NO_DATA = "返回数据为空,请确认 mall 库已按 document/sql/mall.sql 初始化"


@pytest.fixture(scope="function")
def category_tree(settings: Settings, anon_client: ApiClient) -> list:
    """全量商品分类树(List<PmsProductCategoryNode>)。"""
    resp = anon_client.get(settings.portal("/product/categoryTreeList"))
    data = get_data(assert_success(resp))
    assert isinstance(data, list) and data, f"商品分类树{_MSG_NO_DATA}"
    return data


@pytest.fixture(scope="function")
def first_category_id(category_tree: list) -> int:
    """分类树第一个分类的 id(搜索/筛选用例用)。"""
    return category_tree[0]["id"]


@pytest.fixture(scope="session")
def worker_product(request, settings: Settings, anon_client: ApiClient) -> tuple:
    """(product_id, sku_id):当前 worker 专属的测试商品(见模块注释的 xdist 说明)。"""
    worker_input = getattr(request.config, "workerinput", None) or {}
    worker_id = worker_input.get("workerid", "master")
    index = int(worker_id[2:]) if worker_id.startswith("gw") else 0

    resp = anon_client.get(
        settings.portal("/product/search"),
        params={"keyword": settings.es.keyword, "pageNum": 1, "pageSize": 30},
    )
    page = get_data(assert_success(resp))
    candidates = [item["id"] for item in page.get("list") or []]
    assert candidates, f"搜索 keyword={settings.es.keyword} 无结果,{_MSG_NO_DATA}"

    # 从 worker 对应下标开始,挑选第一个详情可用且带 SKU 库存数据的商品
    for offset in range(len(candidates)):
        pid = candidates[(index + offset) % len(candidates)]
        try:
            detail_resp = anon_client.get(settings.portal(f"/product/detail/{pid}"))
            detail = get_data(assert_success(detail_resp))
        except AssertionError:
            continue
        skus = detail.get("skuStockList") or []
        if skus and skus[0].get("id") is not None:
            log.info("worker=%s 使用测试商品 productId=%s skuId=%s",
                     worker_id, pid, skus[0]["id"])
            return pid, skus[0]["id"]
    raise AssertionError(f"worker={worker_id} 在搜索结果的商品池中找不到可用商品")


@pytest.fixture(scope="session")
def product_id(worker_product: tuple) -> int:
    """当前 worker 专属测试商品的 id(加购/详情/下单等用例的入参)。"""
    return worker_product[0]


@pytest.fixture(scope="session")
def product_detail(settings: Settings, anon_client: ApiClient, product_id: int) -> dict:
    """商品详情 PmsPortalProductDetail(product/brand/属性/skuStockList/促销/优惠券)。"""
    resp = anon_client.get(settings.portal(f"/product/detail/{product_id}"))
    data = get_data(assert_success(resp))
    assert data and data.get("product"), (
        f"商品 {product_id} 详情缺少 product 字段: {data}"
    )
    return data


@pytest.fixture(scope="session")
def sku_id(product_detail: dict) -> int:
    """商品详情中第一个 SKU 的 id(加购入参 productSkuId)。"""
    sku_list = product_detail.get("skuStockList") or []
    assert sku_list, f"商品 {product_detail['product']['id']} 无 SKU 库存数据"
    return sku_list[0]["id"]


@pytest.fixture(scope="session")
def brand_id(product_detail: dict) -> int:
    """商品详情中品牌的 id(搜索品牌筛选入参)。"""
    brand = product_detail.get("brand") or {}
    assert brand.get("id"), f"商品详情缺少品牌数据: {product_detail.get('brand')}"
    return brand["id"]


@pytest.fixture(scope="function")
def home_content(settings: Settings, anon_client: ApiClient) -> dict:
    """首页内容聚合(轮播/推荐/品牌/活动等)。"""
    resp = anon_client.get(settings.portal("/home/content"))
    data = get_data(assert_success(resp))
    assert isinstance(data, dict) and data, f"首页内容{_MSG_NO_DATA}"
    return data
