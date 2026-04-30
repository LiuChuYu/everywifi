import json

import pytest


def _setup(client, username="u1", plan_mb=500):
    user = client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@x.com", "password": "pw"}),
        content_type="application/json",
    ).get_json()
    plan = client.post(
        "/plans",
        data=json.dumps({"name": f"plan_{username}", "price": 50, "data_limit_mb": plan_mb, "duration_days": 1}),
        content_type="application/json",
    ).get_json()
    purchase = client.post(
        "/purchases",
        data=json.dumps({"user_id": user["id"], "plan_id": plan["id"]}),
        content_type="application/json",
    ).get_json()
    client.post(f"/purchases/{purchase['id']}/pay")

    # 登入取得 token
    login = client.post(
        "/users/login",
        data=json.dumps({"username": username, "password": "pw"}),
        content_type="application/json",
    ).get_json()
    token = login["token"]
    return user["id"], purchase["id"], token


def test_get_usage_no_purchase(client):
    user = client.post(
        "/users",
        data=json.dumps({"username": "nopurchase", "email": "np@x.com", "password": "pw"}),
        content_type="application/json",
    ).get_json()
    rv = client.get(f"/usage/user/{user['id']}")
    assert rv.status_code == 200
    assert rv.get_json()["can_access"] is False


def test_get_usage_with_active_purchase(client):
    user_id, _, _ = _setup(client, "ua")
    rv = client.get(f"/usage/user/{user_id}")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["can_access"] is True
    assert data["active_purchase"] is not None


def test_deduct_usage(client):
    _, _, token = _setup(client, "ub")
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "bytes_used": 1024 * 1024}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["mb_used"] == pytest.approx(1.0, abs=0.01)


def test_deduct_usage_invalid_token(client):
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": "badtoken", "bytes_used": 100}),
        content_type="application/json",
    )
    assert rv.status_code == 404


def test_deduct_usage_missing_token(client):
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"bytes_used": 100}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_deduct_usage_exhausts_quota(client):
    """流量用盡後 is_active 應為 False"""
    user_id, _, token = _setup(client, "uc", plan_mb=1)  # 1 MB 套餐
    # 扣除 2 MB（超過上限）
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "bytes_used": 2 * 1024 * 1024}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["mb_remaining"] == 0
    assert data["is_active"] is False


def test_deduct_usage_unlimited_plan(client):
    """無限流量套餐 mb_remaining 應為 None"""
    _, _, token = _setup(client, "ud", plan_mb=0)
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "bytes_used": 999 * 1024 * 1024}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["mb_remaining"] is None
    assert data["is_active"] is True
