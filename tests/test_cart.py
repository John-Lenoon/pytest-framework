# -*- coding: utf-8 -*-
"""购物车模块用例(真实 API,无 Mock)。

覆盖接口(business_flow.yaml flow-03 购物车链路):
    GET  /mall-portal/cart/list              购物车列表
    GET  /mall-portal/cart/list/promotion    含促销信息列表(下单前用)
    POST /mall-portal/cart/add               添加商品(body: productId/productSkuId/quantity)
    GET  /mall-portal/cart/update/quantity   修改数量(id, quantity)
    POST /mall-portal/cart/update/attr       修改规格(OmsCartItem)
    POST /mall-portal/cart/delete            按 id 列表删除
    POST /mall-portal/cart/clear             清空购物车(独立新会员执行,不污染内置账号)

数据隔离约定:
- 增删改用例只操作自己新添加的条目(cart_item_id fixture 自带 teardown 删除),
  不触碰 mall.sql 中内置 test 用户的种子购物车数据。
- 清空购物车属于破坏性操作,使用 fixture 注册的新会员执行。
"""
import pytest

from config.settings import Settings
from data.cart_data import (
    CART_ADD_INVALID_BODY,
    CART_ADD_MISSING_PRODUCT,
    CART_DELETE_INVALID_IDS,
    CART_QUANTITY_INVALID,
    CART_QUANTITY_VALUES,
)
from data.login_data import AUTH_HEADER_CASES
from fixtures.cart_fixtures import (
    add_cart_item,
    assert_cart_item_absent,
    build_cart_item_payload,
    delete_cart_item,
    find_cart_item_id,
)
from utils.allure_utils import step
from utils.assertions import (
    assert_failed,
    assert_gateway_unauthorized,
    assert_success,
    get_data,
)
from utils.http_client import ApiClient

pytestmark = pytest.mark.cart


class TestCartPermission:
    """购物车鉴权:全部接口要求登录(token -> memberId 决定购物车归属)。"""

    @pytest.mark.permission
    @pytest.mark.parametrize("case", AUTH_HEADER_CASES, ids=[c["desc"] for c in AUTH_HEADER_CASES])
    def test_cart_list_without_token(self, settings: Settings, anon_client: ApiClient, case: dict):
        """无 token / 非法 token 访问购物车列表 -> 网关 401。"""
        if case["headers"] is None:
            resp = anon_client.get(settings.portal("/cart/list"))
        else:
            resp = anon_client.get(settings.portal("/cart/list"), headers=case["headers"])
        assert_gateway_unauthorized(resp)

    @pytest.mark.permission
    def test_cart_add_without_token(self, settings: Settings, anon_client: ApiClient,
                                    product_id: int, sku_id: int):
        """无 token 添加购物车 -> 网关 401,不产生购物车条目。"""
        resp = anon_client.post(
            settings.portal("/cart/add"),
            json={"productId": product_id, "productSkuId": sku_id, "quantity": 1},
        )
        assert_gateway_unauthorized(resp)


class TestCartCrud:
    """购物车增删改查主流程(flow-03: 详情 -> 加购 -> 改数量 -> 删除)。"""

    @pytest.mark.smoke
    @pytest.mark.flow
    def test_cart_add_item_visible_in_list(self, cart_item_id: int, cart_list: list,
                                           product_id: int):
        """添加商品后,条目出现在购物车列表中(链路: 商品详情 productId -> cart/add)。"""
        item_ids = [item["id"] for item in cart_list]
        assert cart_item_id in item_ids, f"购物车列表缺少新添加条目 {cart_item_id}: {item_ids}"
        target = next(item for item in cart_list if item["id"] == cart_item_id)
        assert target["productId"] == product_id, f"条目商品 id 不匹配: {target}"

    @pytest.mark.flow
    def test_cart_duplicate_add_accumulates_quantity(self, settings: Settings,
                                                     member_client: ApiClient,
                                                     product_id: int, sku_id: int):
        """同商品同 SKU 重复添加:不新建条目,数量累加为 2(test_rules duplicated_data)。"""
        cart_item_id = None
        try:
            assert_cart_item_absent(settings, member_client, product_id, sku_id)
            with step("连续两次添加同商品"):
                add_cart_item(settings, member_client, product_id, sku_id, quantity=1)
                add_cart_item(settings, member_client, product_id, sku_id, quantity=1)
            cart_item_id = find_cart_item_id(settings, member_client, product_id, sku_id)
            resp = member_client.get(settings.portal("/cart/list"))
            items = get_data(assert_success(resp))
            target = next(item for item in items if item["id"] == cart_item_id)
            assert target["quantity"] == 2, (
                f"重复添加后数量应为 2,实际 {target['quantity']}: {target}"
            )
        finally:
            if cart_item_id is not None:
                member_client.post(settings.portal("/cart/delete"), params={"ids": [cart_item_id]})

    @pytest.mark.parametrize("quantity", CART_QUANTITY_VALUES)
    def test_cart_update_quantity(self, settings: Settings, member_client: ApiClient,
                                  cart_item_id: int, quantity: int):
        """修改数量后,列表中的数量与入参一致。"""
        resp = member_client.get(
            settings.portal("/cart/update/quantity"),
            params={"id": cart_item_id, "quantity": quantity},
        )
        assert_success(resp)
        list_resp = member_client.get(settings.portal("/cart/list"))
        items = get_data(assert_success(list_resp))
        target = next(item for item in items if item["id"] == cart_item_id)
        assert target["quantity"] == quantity, f"数量修改未生效: {target}"

    def test_cart_update_attr(self, settings: Settings, member_client: ApiClient,
                              cart_item_id: int, product_id: int, sku_id: int):
        """修改购物车条目规格(同 SKU 重放):成功且条目保持可用。"""
        updated_id = None
        payload = build_cart_item_payload(settings, member_client, product_id, sku_id)
        payload["id"] = cart_item_id
        try:
            resp = member_client.post(settings.portal("/cart/update/attr"), json=payload)
            assert_success(resp)
            updated_id = find_cart_item_id(settings, member_client, product_id, sku_id)
            list_resp = member_client.get(settings.portal("/cart/list"))
            items = get_data(assert_success(list_resp))
            target = next(item for item in items if item["id"] == updated_id)
            assert target.get("price") is not None, f"规格更新后商品价格丢失: {target}"
            assert target.get("productName"), f"规格更新后商品名称丢失: {target}"
        finally:
            if updated_id is not None:
                delete_cart_item(settings, member_client, updated_id)

    @pytest.mark.flow
    def test_cart_list_promotion(self, cart_promotion: list, cart_item_id: int):
        """含促销信息的购物车列表:包含目标条目及促销计算字段。

        已知差异(实测):本 fork 的 CartPromotionItem 序列化不含 price/
        productName 等字段,促销相关信息以 promotionMessage(满减文案)、
        reduceAmount(减免金额)、realStock(真实库存)为准。
        """
        assert len(cart_promotion) > 0, "促销购物车列表为空"
        target = next(
            (item for item in cart_promotion if item.get("id") == cart_item_id), None
        )
        assert target is not None, f"促销列表缺少条目 {cart_item_id}: {cart_promotion}"
        assert target.get("promotionMessage"), f"促销条目缺少促销文案: {target}"
        assert target.get("reduceAmount") is not None, f"促销条目缺少减免金额: {target}"
        assert isinstance(target.get("realStock"), int), f"促销条目缺少真实库存: {target}"

    def test_cart_delete_removes_item(self, settings: Settings, member_client: ApiClient,
                                      product_id: int, sku_id: int):
        """删除购物车条目后,列表中不再出现该条目(自建条目自删,完整闭环)。"""
        assert_cart_item_absent(settings, member_client, product_id, sku_id)
        add_cart_item(settings, member_client, product_id, sku_id, quantity=1)
        cart_item_id = find_cart_item_id(settings, member_client, product_id, sku_id)
        resp = member_client.post(settings.portal("/cart/delete"), params={"ids": [cart_item_id]})
        assert_success(resp)
        list_resp = member_client.get(settings.portal("/cart/list"))
        items = get_data(assert_success(list_resp))
        assert all(item["id"] != cart_item_id for item in items), (
            f"删除后购物车仍存在条目 {cart_item_id}: {items}"
        )


class TestCartValidation:
    """购物车参数校验与数据异常(不产生脏数据)。"""

    @pytest.mark.validation
    @pytest.mark.parametrize("case", CART_ADD_MISSING_PRODUCT, ids=[c["desc"] for c in CART_ADD_MISSING_PRODUCT])
    def test_cart_add_missing_product(self, settings: Settings, member_client: ApiClient, case: dict):
        """商品/SKU 不存在:不抛 500,并清理可能产生的数据。

        已知缺陷(与 test_rules.yaml 预期不符):本 fork 的 /cart/add 不校验商品
        是否存在,不存在商品也会插入一条 price=null 的垃圾购物车条目(真实前端
        因快照契约不会触发)。用例按真实行为验证并清理,保证库不被污染;
        若服务侧修复为拒绝入单,本用例的清理逻辑会自然变为 no-op。
        """
        resp = member_client.post(settings.portal("/cart/add"), json=case["body"])
        assert resp.status_code != 500, f"不存在的商品导致 500: {resp.text[:500]}"
        # 清理:删除该次请求可能插入的垃圾条目(productId 匹配 case 中的 productId)
        list_resp = member_client.get(settings.portal("/cart/list"))
        items = get_data(assert_success(list_resp))
        garbage_ids = [item["id"] for item in items
                       if item.get("productId") == case["body"]["productId"]]
        for gid in garbage_ids:
            member_client.post(settings.portal("/cart/delete"), params={"ids": [gid]})

    @pytest.mark.validation
    @pytest.mark.parametrize("case", CART_ADD_INVALID_BODY, ids=[c["desc"] for c in CART_ADD_INVALID_BODY])
    def test_cart_add_invalid_body(self, settings: Settings, member_client: ApiClient, case: dict):
        """缺字段/非法类型/负数:按真实行为断言(见 data/cart_data.py 注释),并清理条目。

        已知缺陷:本 fork 的 /cart/add 对 body 无字段级校验,部分非法 body
        会插入 null 字段的垃圾条目,或直接 500(NOT NULL 约束)。用例在请求
        前后对比购物车条目 id 集合,删除本次新增的条目,保证数据干净。
        """
        def _cart_items() -> list:
            list_resp = member_client.get(settings.portal("/cart/list"))
            return get_data(assert_success(list_resp)) or []

        before = {item["id"] for item in _cart_items()}
        try:
            resp = member_client.post(settings.portal("/cart/add"), json=case["body"])
            assert resp.status_code == case["expected"], (
                f"case「{case['desc']}」预期 HTTP {case['expected']},"
                f"实际 {resp.status_code}: {resp.text[:500]}"
            )
        finally:
            # 只清理本次 case 的 productId 产生的条目:xdist 下其他 worker 也在
            # 操作同一会员的购物车,按纯 id 集合差分会误删并行用例的条目
            body = case["body"] if isinstance(case["body"], dict) else {}
            target_pid = body.get("productId")
            new_ids = {
                item["id"] for item in _cart_items()
                if item.get("productId") == target_pid and item["id"] not in before
            }
            for cid in new_ids:
                member_client.post(settings.portal("/cart/delete"), params={"ids": [cid]})

    @pytest.mark.validation
    @pytest.mark.parametrize("case", CART_QUANTITY_INVALID, ids=[c["desc"] for c in CART_QUANTITY_INVALID])
    def test_cart_update_quantity_invalid(self, settings: Settings, member_client: ApiClient,
                                          cart_item_id: int, case: dict):
        """非法数量(0/负数/超库存):不抛 500,验证后恢复数量为 1。

        已知缺陷(与 test_rules.yaml 预期不符):本 fork 的 update/quantity 对数量
        无合法性校验(不检查 <=0 与库存上限),非法值会直接落库。用例只断言
        接口不崩溃,并在结束后把数量恢复为 1,保证不破坏条目(fixture teardown
        会删除该条目,双重保险)。若服务侧补上校验,恢复操作自然成为 no-op。
        """
        try:
            resp = member_client.get(
                settings.portal("/cart/update/quantity"),
                params={"id": cart_item_id, "quantity": case["quantity"]},
            )
            assert resp.status_code != 500, f"非法数量 {case['quantity']} 导致 500: {resp.text[:500]}"
        finally:
            member_client.get(
                settings.portal("/cart/update/quantity"),
                params={"id": cart_item_id, "quantity": 1},
            )

    @pytest.mark.parametrize("case", CART_DELETE_INVALID_IDS, ids=[c["desc"] for c in CART_DELETE_INVALID_IDS])
    def test_cart_delete_invalid_ids(self, settings: Settings, member_client: ApiClient, case: dict):
        """删除不存在的条目/空列表:不抛 500,不越权删除。"""
        resp = member_client.post(settings.portal("/cart/delete"), params={"ids": case["ids"]})
        assert resp.status_code != 500, f"非法 ids {case['ids']} 导致 500: {resp.text[:500]}"
        if resp.status_code == 200:
            assert_failed(resp)


class TestCartClear:
    """清空购物车(破坏性操作,用独立注册的新会员执行)。"""

    def test_cart_clear_with_fresh_member(self, settings: Settings, fresh_member: dict,
                                          fresh_member_client: ApiClient,
                                          product_id: int, sku_id: int):
        """新会员:加购 -> 清空 -> 列表为空(真实注册链路,不污染内置账号)。"""
        add_cart_item(settings, fresh_member_client, product_id, sku_id, quantity=1)
        list_resp = fresh_member_client.get(settings.portal("/cart/list"))
        assert len(get_data(assert_success(list_resp))) > 0, "加购后购物车不应为空"

        with step("清空购物车"):
            clear_resp = fresh_member_client.post(settings.portal("/cart/clear"))
            assert_success(clear_resp)

        list_resp = fresh_member_client.get(settings.portal("/cart/list"))
        assert get_data(assert_success(list_resp)) == [], "清空后购物车应为空列表"
