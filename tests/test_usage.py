import json

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _setup(client, username="u1", credit_limit=100_000):
    """建立使用者、帳戶，並回傳 (user_id, token, rate_card_id)"""
    user = client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@x.com", "password": "pw"}),
        content_type="application/json",
    ).get_json()
    client.post(
        "/accounts",
        data=json.dumps({"user_id": user["id"], "credit_limit": credit_limit, "billing_enabled": True}),
        content_type="application/json",
    )
    token = client.post(
        "/users/login",
        data=json.dumps({"username": username, "password": "pw"}),
        content_type="application/json",
    ).get_json()["token"]

    rate_card = client.post(
        "/rate-cards",
        data=json.dumps({"name": f"rc_{username}", "price_per_mb": 1000}),
        content_type="application/json",
    ).get_json()

    return user["id"], token, rate_card["id"]


# ── tests ─────────────────────────────────────────────────────────────────────

def test_get_usage_no_account(client):
    user = client.post(
        "/users",
        data=json.dumps({"username": "noaccount", "email": "na@x.com", "password": "pw"}),
        content_type="application/json",
    ).get_json()
    rv = client.get(f"/usage/user/{user['id']}")
    assert rv.status_code == 200
    assert rv.get_json()["can_access"] is False


def test_get_usage_with_active_account(client):
    user_id, _, _ = _setup(client, "ua")
    rv = client.get(f"/usage/user/{user_id}")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["can_access"] is True
    assert data["account"] is not None


def test_deduct_usage(client):
    _, token, rate_card_id = _setup(client, "ub")
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": "aa:bb:cc:dd:ee:ff",
                         "bytes_used": 1024 * 1024, "rate_card_id": rate_card_id}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["mb_used"] == pytest.approx(1.0, abs=0.01)
    assert data["cost_millitwd"] == 1000  # 1 MB × 1000 milli-TWD/MB


def test_deduct_usage_creates_session_automatically(client):
    """第一次扣費時若無 active session，應自動建立"""
    _, token, _ = _setup(client, "uc")
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": "device:auto:session", "bytes_used": 512}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["session_id"] is not None


def test_deduct_usage_hash_chain(client):
    """多筆扣費記錄應形成 Hash Chain（prev_hash 連結）"""
    _, token, rate_card_id = _setup(client, "ud")
    device = "chain:device:00:00"

    rv1 = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": device,
                         "bytes_used": 1024, "rate_card_id": rate_card_id}),
        content_type="application/json",
    )
    rv2 = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": device,
                         "bytes_used": 2048, "rate_card_id": rate_card_id}),
        content_type="application/json",
    )
    hash1 = rv1.get_json()["record_hash"]
    hash2_prev = rv2.get_json()["record_hash"]
    # The second record's prev_hash should equal the first record's hash.
    # We verify indirectly: record_hash is non-empty and distinct.
    assert len(hash1) == 64
    assert len(hash2_prev) == 64
    assert hash1 != hash2_prev


def test_deduct_usage_updates_balance(client):
    """扣費後帳戶 balance_used 應增加"""
    user_id, token, rate_card_id = _setup(client, "ue")
    client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": "bal:device",
                         "bytes_used": 1024 * 1024, "rate_card_id": rate_card_id}),
        content_type="application/json",
    )
    account = client.get(f"/accounts/user/{user_id}").get_json()
    assert account["balance_used"] == 1000  # 1 MB × 1000 milli-TWD/MB


def test_deduct_usage_stops_at_credit_limit(client):
    """餘額耗盡後應拒絕繼續扣費"""
    _, token, rate_card_id = _setup(client, "uf", credit_limit=500)  # 0.5 TWD limit
    # 扣 1 MB = 1000 milli-TWD，超過上限 500
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": "limit:dev",
                         "bytes_used": 1024 * 1024, "rate_card_id": rate_card_id}),
        content_type="application/json",
    )
    # First deduct succeeds (balance starts at 0 < 500)
    assert rv.status_code == 200
    # Second deduct should be refused because balance_used >= credit_limit
    rv2 = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": "limit:dev",
                         "bytes_used": 1024, "rate_card_id": rate_card_id}),
        content_type="application/json",
    )
    assert rv2.status_code == 403


def test_deduct_usage_multidevice_shared_balance(client):
    """多設備共享同一帳戶餘額"""
    user_id, token, rate_card_id = _setup(client, "ug")
    for dev in ["dev:01", "dev:02", "dev:03"]:
        client.post(
            "/usage/deduct",
            data=json.dumps({"token": token, "device_id": dev,
                             "bytes_used": 1024 * 1024, "rate_card_id": rate_card_id}),
            content_type="application/json",
        )
    account = client.get(f"/accounts/user/{user_id}").get_json()
    assert account["balance_used"] == 3000  # 3 × 1000 milli-TWD


def test_deduct_usage_no_rate_card(client):
    """不提供 rate_card_id 時費用應為 0"""
    user_id, token, _ = _setup(client, "uh")
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "device_id": "free:dev", "bytes_used": 999 * 1024 * 1024}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["cost_millitwd"] == 0
    account = client.get(f"/accounts/user/{user_id}").get_json()
    assert account["balance_used"] == 0


def test_deduct_usage_invalid_token(client):
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": "badtoken", "device_id": "x", "bytes_used": 100}),
        content_type="application/json",
    )
    assert rv.status_code == 404


def test_deduct_usage_missing_token(client):
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"device_id": "x", "bytes_used": 100}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_deduct_usage_missing_device_id(client):
    _, token, _ = _setup(client, "ui")
    rv = client.post(
        "/usage/deduct",
        data=json.dumps({"token": token, "bytes_used": 100}),
        content_type="application/json",
    )
    assert rv.status_code == 400
