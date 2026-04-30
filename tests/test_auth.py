import json


def _setup(client, username="authuser", credit_limit=50000):
    client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@x.com", "password": "pw"}),
        content_type="application/json",
    )
    user_info = client.post(
        "/users/login",
        data=json.dumps({"username": username, "password": "pw"}),
        content_type="application/json",
    ).get_json()
    user_id = user_info["user"]["id"]
    token = user_info["token"]

    client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": credit_limit, "billing_enabled": True}),
        content_type="application/json",
    )
    return token, user_id


def test_auth_allowed(client):
    token, _ = _setup(client, "authok")
    rv = client.post(
        "/auth",
        data=json.dumps({"token": token, "mac_address": "aa:bb:cc:dd:ee:ff"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["allowed"] is True
    assert data["reason"] == "ok"


def test_auth_invalid_token(client):
    rv = client.post(
        "/auth",
        data=json.dumps({"token": "invalid", "mac_address": "aa:bb:cc:dd:ee:ff"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["allowed"] is False
    assert "invalid token" in data["reason"]


def test_auth_no_account(client):
    client.post(
        "/users",
        data=json.dumps({"username": "noaccount", "email": "na@x.com", "password": "pw"}),
        content_type="application/json",
    )
    login = client.post(
        "/users/login",
        data=json.dumps({"username": "noaccount", "password": "pw"}),
        content_type="application/json",
    ).get_json()
    token = login["token"]
    rv = client.post(
        "/auth",
        data=json.dumps({"token": token}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["allowed"] is False
    assert "billing not enabled" in data["reason"]


def test_auth_billing_disabled(client):
    client.post(
        "/users",
        data=json.dumps({"username": "nodisabled", "email": "nd@x.com", "password": "pw"}),
        content_type="application/json",
    )
    login = client.post(
        "/users/login",
        data=json.dumps({"username": "nodisabled", "password": "pw"}),
        content_type="application/json",
    ).get_json()
    user_id = login["user"]["id"]
    token = login["token"]
    client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": 50000, "billing_enabled": False}),
        content_type="application/json",
    )
    rv = client.post("/auth", data=json.dumps({"token": token}), content_type="application/json")
    assert rv.status_code == 200
    assert rv.get_json()["allowed"] is False


def test_auth_missing_token(client):
    rv = client.post(
        "/auth",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_auth_returns_user_info(client):
    token, user_id = _setup(client, "authinfo")
    rv = client.post(
        "/auth",
        data=json.dumps({"token": token}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["user_id"] == user_id
    assert "username" in data
    assert "account_id" in data
    assert "credit_remaining" in data


def test_auth_credit_exhausted(client):
    """信用額度耗盡後不允許上網"""
    token, _ = _setup(client, "authexhaust", credit_limit=0)
    rv = client.post("/auth", data=json.dumps({"token": token}), content_type="application/json")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["allowed"] is False
    assert "credit limit" in data["reason"]
