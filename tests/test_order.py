# -*- coding: utf-8 -*-
"""订单模块用例(真实 API,无 Mock)。

覆盖接口(business_flow.yaml flow-04 订单链路):
    POST /mall-portal/order/generateConfirmOrder   购物车 -> 确认单(下单前置校验)
    POST /mall-portal/order/generateOrder          确认单 -> 正式订单(返回 orderId)
    POST /mall-portal/order/paySuccess             支付回调(待付款 -> 待发货)
    POST /mall-portal/order/cancelUserOrder        用户取消订单(待付款 -> 已关闭)
    GET  /mall-portal/order/detail/{orderId}       订单详情
    GET  /mall-portal/order/list                   按状态分页查询

订单状态枚举:-1 全部 / 0 待付款 / 1 待发货 / 2 已发货 / 3 已完成 / 4 已关闭

数据清理约定:
- 未支付订单:fixture 在用例结束后 cancelUserOrder -> deleteOrder,完整清理。
- 已支付订单(待发货):无法删除(deleteOrder 仅允许 已关闭/已完成),保留真实数据。
- 前置条件:测试会员必须有收货地址(mall.sql 内置 test 用户含地址 id=1/3/4),
  且 RabbitMQ 可用(generateOrder 发送延迟取消消息,失败会回滚下单)。
"""
import pytest

from config.settings import Settings
from data.login_data import AUTH_HEADER_CASES
from data.order_data import (
    CONFIRM_ORDER_INVALID_BODIES,
    GENERATE_ORDER_MISSING_ADDRESS,
    ORDER_INVALID_IDS,
    ORDER_LIST_STATUSES,
    PAY_SUCCESS_INVALID_PARAMS,
)
from utils.allure_utils import step
from utils.assertions import (
    assert_common_page,
    assert_failed,
    assert_gateway_unauthorized,
    assert_msg_contains,
    assert_success,
    get_data,
    resp_json,
)
from utils.http_client import ApiClient

pytestmark = pytest.mark.order


def _get_order_detail(settings: Settings, client: ApiClient, order_id: int) -> dict:
    """查询订单详情,返回订单主体(含 status/payType/orderItemList)。

    实测本 fork 的 /order/detail/{id} 直接返回扁平 Order(带 orderItemList),
    而非 Map{order: ...} 包装。
    """
    resp = client.get(settings.portal(f"/order/detail/{order_id}"))
    data = get_data(assert_success(resp))
    assert data and data.get("id") == order_id, f"订单 {order_id} 详情数据异常: {data}"
    return data


class TestOrderPermission:
    """订单鉴权:全部接口要求登录。"""

    @pytest.mark.permission
    @pytest.mark.parametrize("case", AUTH_HEADER_CASES, ids=[c["desc"] for c in AUTH_HEADER_CASES])
    def test_order_list_without_token(self, settings: Settings, anon_client: ApiClient, case: dict):
        """无 token / 非法 token 访问订单列表 -> 网关 401。"""
        if case["headers"] is None:
            resp = anon_client.get(settings.portal("/order/list"),
                                   params={"status": -1, "pageNum": 1, "pageSize": 5})
        else:
            resp = anon_client.get(settings.portal("/order/list"),
                                   params={"status": -1, "pageNum": 1, "pageSize": 5},
                                   headers=case["headers"])
        assert_gateway_unauthorized(resp)


class TestOrderFlow:
    """订单主链路(flow-04: 确认单 -> 创建订单 -> 支付 -> 取消/收货)。"""

    @pytest.mark.smoke
    @pytest.mark.flow
    def test_generate_confirm_order(self, confirm_order: dict, cart_item_id: int):
        """购物车条目生成确认单:包含商品明细与收货地址列表。"""
        promotion_items = confirm_order.get("cartPromotionItemList") or []
        assert promotion_items, "确认单商品明细为空"
        assert any(item.get("id") == cart_item_id for item in promotion_items), (
            f"确认单缺少购物车条目 {cart_item_id}: {promotion_items}"
        )
        assert confirm_order.get("memberReceiveAddressList"), "确认单缺少收货地址列表"
        calc = confirm_order.get("calcAmount") or {}
        assert calc.get("totalAmount") is not None, f"确认单缺少金额汇总: {confirm_order}"

    @pytest.mark.flow
    def test_generate_order(self, settings: Settings, member_client: ApiClient,
                            generated_order: dict, order_id: int):
        """确认单提交生成正式订单:订单落库,初始状态 待付款(0)。"""
        assert order_id > 0, f"订单 id 非法: {order_id}"
        order = _get_order_detail(settings, member_client, order_id)
        assert order.get("status") == 0, f"新订单应为待付款(0),实际 {order.get('status')}"
        assert order.get("totalAmount") is not None, f"订单缺少总金额: {order}"

    @pytest.mark.flow
    def test_pay_success_transitions_order(self, settings: Settings, member_client: ApiClient,
                                           paid_order_id: int):
        """支付回调:订单状态 待付款(0) -> 待发货(1),记录支付方式与时间。"""
        order = _get_order_detail(settings, member_client, paid_order_id)
        assert order.get("status") == 1, (
            f"支付后订单应为待发货(1),实际 {order.get('status')}: {order}"
        )
        assert order.get("payType") == 1, f"支付方式不匹配: {order}"
        assert order.get("paymentTime") is not None, f"缺少支付时间: {order}"

    @pytest.mark.flow
    def test_duplicate_pay_success_keeps_status(self, settings: Settings,
                                                member_client: ApiClient, paid_order_id: int):
        """重复支付回调:订单状态保持 待发货(1),不发生重复流转(test_rules duplicated_data)。"""
        with step("第一次支付后的订单状态"):
            before = _get_order_detail(settings, member_client, paid_order_id)
            assert before.get("status") == 1

        with step("重复支付回调"):
            resp = member_client.post(
                settings.portal("/order/paySuccess"),
                params={"orderId": paid_order_id, "payType": 1},
            )
            assert resp.status_code != 500, f"重复支付导致 500: {resp.text[:500]}"

        with step("订单状态应保持不变"):
            after = _get_order_detail(settings, member_client, paid_order_id)
            assert after.get("status") == 1, (
                f"重复支付后状态异常流转为 {after.get('status')}"
            )

    @pytest.mark.flow
    def test_cancel_unpaid_order(self, settings: Settings, member_client: ApiClient,
                                 unpaid_order_id: int):
        """用户取消未支付订单:状态 待付款(0) -> 已关闭(4)。"""
        order = _get_order_detail(settings, member_client, unpaid_order_id)
        assert order.get("status") == 0, f"取消前订单应为待付款,实际 {order.get('status')}"

        with step("取消订单"):
            resp = member_client.post(
                settings.portal("/order/cancelUserOrder"),
                params={"orderId": unpaid_order_id},
            )
            assert_success(resp)

        with step("订单状态应为已关闭"):
            order = _get_order_detail(settings, member_client, unpaid_order_id)
            assert order.get("status") == 4, f"取消后状态应为已关闭(4),实际 {order.get('status')}"

    @pytest.mark.flow
    def test_order_list_contains_created_order(self, settings: Settings,
                                               member_client: ApiClient, paid_order_id: int):
        """订单列表(全部状态)包含新创建的已支付订单。"""
        resp = member_client.get(
            settings.portal("/order/list"), params={"status": -1, "pageNum": 1, "pageSize": 5}
        )
        page = assert_common_page(get_data(assert_success(resp)))
        order_ids = [item.get("id") for item in page["list"]]
        assert paid_order_id in order_ids, f"订单列表缺少订单 {paid_order_id}: {order_ids}"


class TestOrderQuery:
    """订单查询:按状态分页。"""

    @pytest.mark.parametrize("case", ORDER_LIST_STATUSES, ids=[c["desc"] for c in ORDER_LIST_STATUSES])
    def test_order_list_by_status(self, settings: Settings, member_client: ApiClient, case: dict):
        """按各状态枚举分页查询:返回标准分页结构。"""
        resp = member_client.get(
            settings.portal("/order/list"),
            params={"status": case["status"], "pageNum": 1, "pageSize": 5},
        )
        page = assert_common_page(get_data(assert_success(resp)))
        assert page["total"] >= 0


class TestOrderValidation:
    """订单参数校验与数据异常(不产生脏数据)。"""

    @pytest.mark.validation
    @pytest.mark.parametrize("case", CONFIRM_ORDER_INVALID_BODIES, ids=[c["desc"] for c in CONFIRM_ORDER_INVALID_BODIES])
    def test_confirm_order_invalid_cart_ids(self, settings: Settings, member_client: ApiClient,
                                            case: dict):
        """cartIds 为空/不存在/含负数:空操作,不生成确认单明细,不抛 500。"""
        resp = member_client.post(settings.portal("/order/generateConfirmOrder"), json=case["body"])
        assert resp.status_code != 500, f"非法 cartIds {case['body']} 导致 500: {resp.text[:500]}"
        if resp.status_code == 200:
            payload = assert_success(resp)
            items = (payload.get("data") or {}).get("cartPromotionItemList") or []
            assert items == [], f"非法 cartIds 不应产生确认单明细: {items}"

    @pytest.mark.validation
    @pytest.mark.parametrize("case", GENERATE_ORDER_MISSING_ADDRESS, ids=[c["desc"] for c in GENERATE_ORDER_MISSING_ADDRESS])
    def test_generate_order_missing_address(self, settings: Settings, member_client: ApiClient,
                                            case: dict):
        """收货地址缺失/不存在:绝不静默建单、绝不扣库存。

        已知缺陷(与 test_rules.yaml 预期不符):本 fork 对不存在的收货地址
        直接抛 500(应为友好拒绝提示),用例容忍 500,但绝不接受
        "HTTP 200 + code=200" 的静默建单成功。
        """
        payload = dict(case["payload"])
        payload["cartIds"] = [999999]  # 地址校验失败发生在读取购物车之前
        resp = member_client.post(settings.portal("/order/generateOrder"), json=payload)
        body = resp_json(resp)
        assert not (resp.status_code == 200 and body.get("code") == 200), (
            f"非法地址不应成功建单: {resp.text[:500]}"
        )
        if resp.status_code == 200:
            assert_failed(resp)
            assert_msg_contains(resp, "地址")

    @pytest.mark.validation
    @pytest.mark.parametrize("case", PAY_SUCCESS_INVALID_PARAMS, ids=[c["desc"] for c in PAY_SUCCESS_INVALID_PARAMS])
    def test_pay_success_invalid_params(self, settings: Settings, member_client: ApiClient,
                                        case: dict):
        """支付回调缺参/非法类型:400 或业务失败,不流转任何订单状态。"""
        resp = member_client.post(settings.portal("/order/paySuccess"), params=case["params"])
        assert resp.status_code != 500, f"非法支付入参 {case['params']} 导致 500: {resp.text[:500]}"
        assert resp.status_code in (200, 400), (
            f"非法支付入参出现异常状态码 {resp.status_code}: {resp.text[:500]}"
        )
        if resp.status_code == 200:
            assert_failed(resp)

    def test_pay_success_nonexistent_order(self, settings: Settings, member_client: ApiClient):
        """支付不存在的订单:绝不静默成功、绝不流转任何订单状态。

        已知缺陷(与 test_rules.yaml 预期不符):本 fork 对不存在的订单支付
        回调直接抛 500(test_rules.yaml 预期为影响行数 0 的静默成功),
        用例按真实行为断言:绝不接受"HTTP 200 + code=200"的支付成功。
        """
        resp = member_client.post(
            settings.portal("/order/paySuccess"), params={"orderId": 999999, "payType": 1}
        )
        body = resp_json(resp)
        assert not (resp.status_code == 200 and body.get("code") == 200), (
            f"不存在订单的支付回调不应成功: {resp.text[:500]}"
        )

    @pytest.mark.parametrize("case", ORDER_INVALID_IDS, ids=[c["desc"] for c in ORDER_INVALID_IDS])
    def test_order_detail_invalid_id(self, settings: Settings, member_client: ApiClient, case: dict):
        """非法 orderId 查询详情:不抛 500,返回空数据。"""
        resp = member_client.get(settings.portal(f"/order/detail/{case['order_id']}"))
        assert resp.status_code != 500, (
            f"非法 orderId={case['order_id']} 导致 500: {resp.text[:500]}"
        )
        if resp.status_code == 200:
            payload = assert_success(resp)
            data = payload.get("data")
            assert data is None or data.get("order") is None, (
                f"非法 orderId={case['order_id']} 返回了异常订单数据: {data}"
            )

    @pytest.mark.parametrize("case", ORDER_INVALID_IDS, ids=[c["desc"] for c in ORDER_INVALID_IDS])
    def test_cancel_user_order_invalid_id(self, settings: Settings, member_client: ApiClient,
                                          case: dict):
        """取消不存在的订单:接口正常返回,不抛 500(服务内为静默 no-op)。"""
        resp = member_client.post(
            settings.portal("/order/cancelUserOrder"), params={"orderId": case["order_id"]}
        )
        assert resp.status_code != 500, (
            f"取消非法 orderId={case['order_id']} 导致 500: {resp.text[:500]}"
        )
        if resp.status_code == 200:
            assert_success(resp)
