# -*- coding: utf-8 -*-
"""用户、订单、支付、物流三类场景的 Flask Mock Server。"""
from functools import wraps
from threading import Lock
from typing import Any
from uuid import uuid4

from flask import Flask, g, jsonify, request


def _result(data: Any = None, code: int = 200, message: str = "操作成功"):
    return jsonify({"code": code, "message": message, "data": data})


def create_app() -> Flask:
    app = Flask(__name__)
    lock = Lock()
    users = {"demo": {"id": 1, "username": "demo", "password": "123456"}}
    tokens: dict[str, int] = {}
    orders: dict[int, dict[str, Any]] = {}
    next_order_id = 1000

    def authenticated(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            authorization = request.headers.get("Authorization", "")
            token = authorization.removeprefix("Bearer ").strip()
            if token not in tokens:
                return _result(code=401, message="token 无效或已过期"), 401
            g.user_id = tokens[token]
            return view(*args, **kwargs)
        return wrapper

    @app.get("/health")
    def health():
        return _result({"status": "UP"})

    @app.post("/api/users/login")
    def login():
        body = request.get_json(silent=True) or {}
        user = users.get(body.get("username"))
        if not user or user["password"] != body.get("password"):
            return _result(code=400, message="用户名或密码错误"), 400
        token = uuid4().hex
        with lock:
            tokens[token] = user["id"]
        return _result({"token": token, "tokenHead": "Bearer", "userId": user["id"]})

    @app.post("/api/orders")
    @authenticated
    def create_order():
        nonlocal next_order_id
        body = request.get_json(silent=True) or {}
        if not isinstance(body.get("productId"), int) or not isinstance(body.get("quantity"), int):
            return _result(code=400, message="productId 和 quantity 必须为整数"), 400
        if body["quantity"] <= 0:
            return _result(code=400, message="quantity 必须大于 0"), 400
        with lock:
            next_order_id += 1
            order = {
                "id": next_order_id,
                "memberId": g.user_id,
                "productId": body["productId"],
                "quantity": body["quantity"],
                "status": "UNPAID",
            }
            orders[next_order_id] = order
        return _result(order)

    @app.post("/api/orders/<int:order_id>/pay")
    @authenticated
    def pay_order(order_id: int):
        with lock:
            order = orders.get(order_id)
            if not order or order["memberId"] != g.user_id:
                return _result(code=404, message="订单不存在"), 404
            if order["status"] != "UNPAID":
                return _result(code=409, message="订单已支付"), 409
            order["status"] = "PAID"
            return _result(dict(order))

    @app.get("/api/logistics/<int:order_id>")
    @authenticated
    def logistics(order_id: int):
        order = orders.get(order_id)
        if not order or order["memberId"] != g.user_id:
            return _result(code=404, message="订单不存在"), 404
        if order["status"] != "PAID":
            return _result(code=409, message="订单未支付"), 409
        return _result({
            "orderId": order_id,
            "status": "PICKING",
            "company": "mock-express",
            "trackingNo": f"MOCK{order_id}",
        })

    return app
