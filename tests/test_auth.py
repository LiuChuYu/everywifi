import json


def _setup(client, username="authuser"):
    client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@x.com", "password": "pw"}),
        content_type="application/json",
    )
    plan = client.post(
        "/plans",
        data=json.dumps({"name": f"plan_{username}", "price": 50, "data_limit_mb": 500, "duration_days": 1}),
        content_type="application/json",
    ).get_json()
    user_info = client.post(
        "/users/login",
        data=json.dumps({"username": username, "password": "pw"}),
        content_type="application/json",
    ).get_json()
    user_id = user_info["user"]["id"]
    token = user_info["token"]

    purchase = client.post(
        "/purchases",
        data=json.dumps({"user_id": user_id, "plan_id": plan["id"]}),
        content_type="application/json",
    ).get_json()
    client.post(f"/purchases/{purchase['id']}/pay")

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


def test_auth_no_purchase(client):
    client.post(
        "/users",
        data=json.dumps({"username": "nopay", "email": "nopay@x.com", "password": "pw"}),
        content_type="application/json",
    )
    login = client.post(
        "/users/login",
        data=json.dumps({"username": "nopay", "password": "pw"}),
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
    assert "no active purchase" in data["reason"]


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
    assert "purchase_id" in data
