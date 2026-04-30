import json


# ── helpers ──────────────────────────────────────────────────────────────────

def _create_user(client, username="u1"):
    rv = client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@x.com", "password": "pw"}),
        content_type="application/json",
    )
    return rv.get_json()["id"]


def _login(client, username="u1"):
    rv = client.post(
        "/users/login",
        data=json.dumps({"username": username, "password": "pw"}),
        content_type="application/json",
    )
    return rv.get_json()["token"]


def _create_account(client, user_id, credit_limit=50000, billing_enabled=True):
    rv = client.post(
        "/accounts",
        data=json.dumps({"user_id": user_id, "credit_limit": credit_limit, "billing_enabled": billing_enabled}),
        content_type="application/json",
    )
    return rv.get_json()["id"]


def _setup(client, username="s1", credit_limit=50000):
    user_id = _create_user(client, username)
    _create_account(client, user_id, credit_limit=credit_limit)
    token = _login(client, username)
    return user_id, token


# ── tests ─────────────────────────────────────────────────────────────────────

def test_start_session(client):
    _, token = _setup(client, "sa")
    rv = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "aa:bb:cc:dd:ee:01"}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["device_id"] == "aa:bb:cc:dd:ee:01"
    assert data["is_active"] is True


def test_start_multiple_sessions_same_account(client):
    """同一帳戶可同時開多個裝置的 Session"""
    _, token = _setup(client, "sb")
    rv1 = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:00:00:00:00:01"}),
        content_type="application/json",
    )
    rv2 = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:00:00:00:00:02"}),
        content_type="application/json",
    )
    assert rv1.status_code == 201
    assert rv2.status_code == 201
    assert rv1.get_json()["id"] != rv2.get_json()["id"]


def test_end_session(client):
    _, token = _setup(client, "sc")
    session_id = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:end:00:00:00:01"}),
        content_type="application/json",
    ).get_json()["id"]

    rv = client.post(f"/sessions/{session_id}/end")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["is_active"] is False
    assert data["ended_at"] is not None


def test_end_session_twice(client):
    _, token = _setup(client, "sd")
    session_id = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:dbl:00:00:00:01"}),
        content_type="application/json",
    ).get_json()["id"]
    client.post(f"/sessions/{session_id}/end")
    rv = client.post(f"/sessions/{session_id}/end")
    assert rv.status_code == 400


def test_list_active_sessions(client):
    user_id, token = _setup(client, "se")
    account_id = client.get(f"/accounts/user/{user_id}").get_json()["id"]

    client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:01"}),
        content_type="application/json",
    )
    session_id = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:02"}),
        content_type="application/json",
    ).get_json()["id"]
    client.post(f"/sessions/{session_id}/end")

    rv = client.get(f"/sessions/account/{account_id}/active")
    assert rv.status_code == 200
    active = rv.get_json()
    assert len(active) == 1
    assert active[0]["device_id"] == "mac:01"


def test_start_session_no_billing(client):
    """未啟用計費時不允許開 Session"""
    user_id = _create_user(client, "sf")
    _create_account(client, user_id, credit_limit=50000, billing_enabled=False)
    token = _login(client, "sf")
    rv = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:nobillin"}),
        content_type="application/json",
    )
    assert rv.status_code == 403


def test_start_session_credit_exhausted(client):
    """信用額度耗盡時不允許開 Session"""
    _, token = _setup(client, "sg", credit_limit=0)
    rv = client.post(
        "/sessions",
        data=json.dumps({"token": token, "device_id": "mac:nocredit"}),
        content_type="application/json",
    )
    assert rv.status_code == 403


def test_start_session_invalid_token(client):
    rv = client.post(
        "/sessions",
        data=json.dumps({"token": "bad", "device_id": "mac:xx"}),
        content_type="application/json",
    )
    assert rv.status_code == 404


def test_start_session_missing_device_id(client):
    _, token = _setup(client, "sh")
    rv = client.post(
        "/sessions",
        data=json.dumps({"token": token}),
        content_type="application/json",
    )
    assert rv.status_code == 400
