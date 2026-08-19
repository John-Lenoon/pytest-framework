# -*- coding: utf-8 -*-
"""购物车 fixture:添加购物车项并提供其 id,用例结束后自动删除(数据清理)。

关键行为(与 business_flow.yaml flow-03 一致):
- postCartAdd 入参为 {productId, productSkuId, quantity}(memberId 由 token 决定)
- 接口只返回影响行数,不返回购物车项 id -> 通过 /cart/list 反查定位新条目
- 同商品同 SKU 重复添加会在原条目上累加数量,因此查找时按 productId+skuId 匹配即可
- teardown 用 /cart/delete 删除自己添加的条目,不触碰内置 test 用户的种子数据
"""
import pytest

from config.settings import Settings
from utils.assertions import assert_success, get_data, resp_json
from utils.http_client import ApiClient
from utils.logger import get_logger

log = get_logger("fixtures.cart")


def build_cart_item_payload(settings: Settings, client: ApiClient, product_id: int,
                            sku_id: int, quantity: int = 1) -> dict:
    """按 mall-app-web 前端契约组装 OmsCartItem 完整快照。

    关键发现:本 fork 的 /cart/add 完全信任客户端入参,服务端不从商品表回填
    price/productName 等字段;若只传 productId/productSkuId/quantity,
    oms_cart_item.price 落库为 NULL,后续 /cart/list/promotion 计算促销
    (CartPromotionItem.getPrice().subtract) 会抛 NullPointerException -> 500。
    真实前端的做法(此处保持一致):从商品详情接口读取 SKU 价格/图片/规格等,
    随加购请求一并提交完整快照。
    """
    detail_resp = client.get(settings.portal(f"/product/detail/{product_id}"))
    detail = get_data(assert_success(detail_resp))
    product = detail["product"]
    sku_list = detail.get("skuStockList") or []
    sku = next((s for s in sku_list if s.get("id") == sku_id), None)
    assert sku is not None, f"商品 {product_id} 详情中无 SKU {sku_id}: {sku_list}"
    return {
        "productId": product_id,
        "productSkuId": sku_id,
        "quantity": quantity,
        "price": sku.get("price"),
        "productPic": sku.get("pic") or product.get("pic"),
        "productName": product.get("name"),
        "productSubTitle": product.get("subTitle"),
        "productSkuCode": sku.get("skuCode"),
        "productBrand": (detail.get("brand") or {}).get("name"),
        "productSn": product.get("productSn"),
        "productCategoryId": product.get("productCategoryId"),
        "productAttr": sku.get("spData"),
        "deleteStatus": 0,
    }


def add_cart_item(settings: Settings, client: ApiClient, product_id: int, sku_id: int,
                  quantity: int = 1) -> dict:
    """添加商品到购物车并返回 CommonResult 完整 JSON(供用例或 fixture 复用)。"""
    resp = client.post(
        settings.portal("/cart/add"),
        json=build_cart_item_payload(settings, client, product_id, sku_id, quantity),
    )
    return assert_success(resp)


def find_cart_item_id(settings: Settings, client: ApiClient, product_id: int,
                      sku_id: int) -> int:
    """在购物车列表中反查指定商品条目的 id。"""
    resp = client.get(settings.portal("/cart/list"))
    items = get_data(assert_success(resp)) or []
    for item in items:
        if item.get("productId") == product_id and item.get("productSkuId") == sku_id:
            return item["id"]
    raise AssertionError(
        f"购物车列表中未找到 productId={product_id}, productSkuId={sku_id} 的条目: {items}"
    )


def assert_cart_item_absent(settings: Settings, client: ApiClient, product_id: int,
                            sku_id: int) -> None:
    """写入前确认没有同款条目，防止合并后误删用户已有购物车数据。"""
    resp = client.get(settings.portal("/cart/list"))
    items = get_data(assert_success(resp)) or []
    existing = [item for item in items
                if item.get("productId") == product_id and item.get("productSkuId") == sku_id]
    if existing:
        raise AssertionError(
            f"测试商品已存在于购物车，拒绝覆盖已有数据: productId={product_id}, "
            f"skuId={sku_id}, itemIds={[item.get('id') for item in existing]}"
        )


def delete_cart_item(settings: Settings, client: ApiClient, cart_item_id: int) -> None:
    """按 id 删除购物车条目(清理用,失败只记录不抛出)。"""
    resp = client.post(settings.portal("/cart/delete"), params={"ids": [cart_item_id]})
    payload = resp_json(resp)
    if resp.status_code != 200 or payload.get("code") != 200:
        log.warning("清理购物车条目 %s 失败: status=%s body=%s",
                    cart_item_id, resp.status_code, resp.text[:500])


@pytest.fixture(scope="function")
def cart_item_id(settings: Settings, member_client: ApiClient,
                 product_id: int, sku_id: int) -> int:
    """添加一个商品到测试会员购物车,返回条目 id,用例结束后自动删除。

    依赖商品 fixture(product_id/sku_id),对应 flow-02 详情 -> flow-03 加购的链路。
    """
    assert_cart_item_absent(settings, member_client, product_id, sku_id)
    add_cart_item(settings, member_client, product_id, sku_id, quantity=1)
    item_id = find_cart_item_id(settings, member_client, product_id, sku_id)
    log.info("已添加购物车条目 id=%s (productId=%s, skuId=%s)", item_id, product_id, sku_id)
    yield item_id
    delete_cart_item(settings, member_client, item_id)


@pytest.fixture(scope="function")
def cart_list(settings: Settings, member_client: ApiClient) -> list:
    """测试会员当前购物车列表 List<OmsCartItem>。"""
    resp = member_client.get(settings.portal("/cart/list"))
    data = get_data(assert_success(resp))
    assert isinstance(data, list), f"购物车列表应为 list,实际 {type(data).__name__}"
    return data


@pytest.fixture(scope="function")
def cart_promotion(settings: Settings, member_client: ApiClient,
                   cart_item_id: int) -> list:
    """指定购物车条目的促销列表 List<CartPromotionItem>(下单前展示用)。"""
    resp = member_client.get(
        settings.portal("/cart/list/promotion"), params={"cartIds": [cart_item_id]}
    )
    data = get_data(assert_success(resp))
    assert isinstance(data, list), f"促销购物车列表应为 list,实际 {type(data).__name__}"
    return data
