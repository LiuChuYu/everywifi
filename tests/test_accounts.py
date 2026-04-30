import json


# ── helpers ──────────────────────────────────────────────────────────────────

def _create_user(client, username="u1"):
    rv = client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@x.com", "password": "pw"}),
        content_type="application/json",
    )
    return rv.get_json()["id"]


# ── tests ─────────────────────────────────────────────────────────────────────

def test_create_account(client):
    user_id = _create_user(client, "acc1")
    rv = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 50000}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["user_id"] == user_id
    assert data["credit_limit"] == 50000
    assert data["balance_used"] == 0
    assert data["billing_enabled"] is False


def test_create_account_with_billing_enabled(client):
    user_id = _create_user(client, "acc2")
    rv = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 10000, "billing_enabled": True}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    assert rv.get_json()["billing_enabled"] is True
    assert rv.get_json()["can_access"] is True


def test_create_account_duplicate(client):
    user_id = _create_user(client, "acc3")
    client.post("/accounts", data=json.dumps({"user_id": user_id, "credit_limit": 1000}), content_type="application/json")
    rv = client.post("/accounts", data=json.dumps({"user_id": user_id, "credit_limit": 2000}), content_type="application/json")
    assert rv.status_code == 409


def test_create_account_invalid_credit_limit(client):
    user_id = _create_user(client, "acc4")
    rv = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": -1}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_create_account_missing_user_id(client):
    rv = client.post(
        "/accounts",
        data=json.dumps({"credit_limit": 1000}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_get_account(client):
    user_id = _create_user(client, "acc5")
    account_id = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 5000}),
        content_type="application/json",
    ).get_json()["id"]
    rv = client.get(f"/accounts/{account_id}")
    assert rv.status_code == 200
    assert rv.get_json()["credit_limit"] == 5000


def test_get_account_by_user(client):
    user_id = _create_user(client, "acc6")
    client.post("/accounts", data=json.dumps({"user_id": user_id, "credit_limit": 7000}), content_type="application/json")
    rv = client.get(f"/accounts/user/{user_id}")
    assert rv.status_code == 200
    assert rv.get_json()["user_id"] == user_id


def test_get_account_by_user_not_found(client):
    user_id = _create_user(client, "acc7")
    rv = client.get(f"/accounts/user/{user_id}")
    assert rv.status_code == 404


def test_enable_billing(client):
    user_id = _create_user(client, "acc8")
    account_id = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 10000}),
        content_type="application/json",
    ).get_json()["id"]
    rv = client.post(f"/accounts/{account_id}/enable")
    assert rv.status_code == 200
    assert rv.get_json()["billing_enabled"] is True


def test_enable_billing_requires_credit_limit(client):
    """credit_limit 為 0 時不得啟用計費"""
    user_id = _create_user(client, "acc9")
    account_id = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 0}),
        content_type="application/json",
    ).get_json()["id"]
    rv = client.post(f"/accounts/{account_id}/enable")
    assert rv.status_code == 400


def test_disable_billing(client):
    user_id = _create_user(client, "acc10")
    account_id = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 10000, "billing_enabled": True}),
        content_type="application/json",
    ).get_json()["id"]
    rv = client.post(f"/accounts/{account_id}/disable")
    assert rv.status_code == 200
    assert rv.get_json()["billing_enabled"] is False


def test_update_credit_limit(client):
    user_id = _create_user(client, "acc11")
    account_id = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 5000}),
        content_type="application/json",
    ).get_json()["id"]
    rv = client.patch(
        f"/accounts/{account_id}/credit-limit",
        data=json.dumps({"credit_limit": 20000}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["credit_limit"] == 20000


def test_credit_remaining(client):
    user_id = _create_user(client, "acc12")
    account_id = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 10000, "billing_enabled": True}),
        content_type="application/json",
    ).get_json()["id"]
    data = client.get(f"/accounts/{account_id}").get_json()
    assert data["credit_remaining"] == 10000
    assert data["can_access"] is True
