# -*- coding: utf-8 -*-
"""订单 fixture:覆盖 business_flow.yaml flow-04 完整链路。

链路(全部真实接口,无 Mock):
    收货地址列表   GET  /mall-portal/member/address/list      -> member_address_id
    加购          (复用 cart_fixtures.cart_item_id)
    生成确认单     POST /mall-portal/order/generateConfirmOrder -> confirm_order
    生成订单       POST /mall-portal/order/generateOrder       -> generated_order
    支付回调       POST /mall-portal/order/paySuccess          -> paid_order_id

数据清理策略:
- 已支付订单(状态=待发货)无法直接删除(deleteOrder 仅允许 已关闭/已完成),
  尝试删除失败仅记录日志,真实订单数据保留在库中便于排查。
- 未支付订单:先 cancelUserOrder(待付款 -> 已关闭),再 deleteOrder,可完整清理。
"""
import pytest

from config.settings import Settings
from fixtures.cart_fixtures import (
    add_cart_item,
    assert_cart_item_absent,
    delete_cart_item,
    find_cart_item_id,
)
from utils.assertions import assert_success, get_data, resp_json
from utils.http_client import ApiClient
from utils.logger import get_logger

log = get_logger("fixtures.order")


@pytest.fixture(scope="function")
def member_address_id(settings: Settings, member_client: ApiClient) -> int:
    """测试会员的收货地址 id(优先默认地址,否则取第一条)。"""
    resp = member_client.get(settings.portal("/member/address/list"))
    addresses = get_data(assert_success(resp)) or []
    if not addresses:
        pytest.skip(
            "测试会员无收货地址(ums_member_receive_address 为空),"
            "请按 document/sql/mall.sql 初始化,或通过 POST /member/address/add 添加"
        )
    default = [a for a in addresses if a.get("defaultStatus") == 1]
    return (default or addresses)[0]["id"]


@pytest.fixture(scope="function")
def confirm_order(settings: Settings, member_client: ApiClient, cart_item_id: int) -> dict:
    """根据购物车条目生成确认单,返回 ConfirmOrderResult。"""
    resp = member_client.post(
        settings.portal("/order/generateConfirmOrder"), json=[cart_item_id]
    )
    data = get_data(assert_success(resp))
    assert isinstance(data, dict) and data, f"确认单数据异常: {data}"
    return data


def generate_order_payload(member_address_id: int, cart_item_id: int) -> dict:
    """组装 OrderParam(memberReceiveAddressId/couponId/useIntegration/payType/cartIds)。"""
    return {
        "memberReceiveAddressId": member_address_id,
        "couponId": None,
        "useIntegration": 0,
        "payType": 1,
        "cartIds": [cart_item_id],
    }


@pytest.fixture(scope="function")
def generated_order(settings: Settings, member_client: ApiClient,
                    confirm_order: dict, cart_item_id: int,
                    member_address_id: int) -> dict:
    """提交确认单生成正式订单,返回 data(Map: order / orderItemList)。

    实测本 fork 的 generateOrder 返回 Map 包装({"order": {...},
    "orderItemList": [...]}),注意 /order/detail/{id} 才是扁平结构。
    """
    resp = member_client.post(
        settings.portal("/order/generateOrder"),
        json=generate_order_payload(member_address_id, cart_item_id),
    )
    data = get_data(assert_success(resp))
    assert data and data.get("order"), f"生成订单响应缺少 order 字段: {data}"
    yield data

    # 只有 generateOrder 的响应才包含 order；确认单本身不创建待清理资源。
    order_id = data["order"]["id"]
    detail_resp = member_client.get(settings.portal(f"/order/detail/{order_id}"))
    detail = (resp_json(detail_resp).get("data") or {}) if detail_resp.status_code == 200 else {}
    if detail.get("status") == 0:
        cancel_resp = member_client.post(
            settings.portal("/order/cancelUserOrder"), params={"orderId": order_id}
        )
        delete_resp = member_client.post(
            settings.portal("/order/deleteOrder"), params={"orderId": order_id}
        )
        log.info("清理 generated_order %s: cancel=%s delete=%s",
                 order_id, cancel_resp.status_code, delete_resp.status_code)
    else:
        log.info("订单 %s 状态为 %s,不执行取消清理", order_id, detail.get("status"))


@pytest.fixture(scope="function")
def order_id(generated_order: dict) -> int:
    """新生成订单的 id。"""
    return generated_order["order"]["id"]


@pytest.fixture(scope="function")
def paid_order_id(settings: Settings, member_client: ApiClient, order_id: int) -> int:
    """已支付订单:generateOrder -> paySuccess(状态流转 待付款 -> 待发货)。

    清理:待发货订单无法删除,尝试 deleteOrder 并仅记录结果。
    """
    resp = member_client.post(
        settings.portal("/order/paySuccess"),
        params={"orderId": order_id, "payType": 1},
    )
    assert_success(resp)
    yield order_id
    delete_resp = member_client.post(
        settings.portal("/order/deleteOrder"), params={"orderId": order_id}
    )
    if delete_resp.status_code != 200:
        log.warning("清理已支付订单 %s 失败(待发货订单通常不可删除): %s",
                    order_id, delete_resp.text[:300])


@pytest.fixture(scope="function")
def unpaid_order_id(settings: Settings, member_client: ApiClient,
                    product_id: int, sku_id: int, member_address_id: int) -> int:
    """未支付订单:独立加购 -> 生成订单(不支付),用例结束后取消并删除。

    自包含:不依赖 cart_item_id/confirm_order 等 fixture,可与支付类用例并行互不干扰。
    """
    assert_cart_item_absent(settings, member_client, product_id, sku_id)
    add_cart_item(settings, member_client, product_id, sku_id, quantity=1)
    cart_id = find_cart_item_id(settings, member_client, product_id, sku_id)

    resp = member_client.post(
        settings.portal("/order/generateOrder"),
        json=generate_order_payload(member_address_id, cart_id),
    )
    data = get_data(assert_success(resp))
    order_id = data["order"]["id"]  # generateOrder 为 Map 包装(实测)
    log.info("已生成未支付订单 id=%s", order_id)

    yield order_id

    # 清理:取消(待付款 -> 已关闭)后删除,不影响后续用例
    cancel_resp = member_client.post(
        settings.portal("/order/cancelUserOrder"), params={"orderId": order_id}
    )
    delete_resp = member_client.post(
        settings.portal("/order/deleteOrder"), params={"orderId": order_id}
    )
    log.info("清理未支付订单 %s: cancel=%s delete=%s",
             order_id, cancel_resp.status_code, delete_resp.status_code)
    # 订单生成后购物车条目已被消费删除,兜底清理一次(幂等)
    delete_cart_item(settings, member_client, cart_id)
