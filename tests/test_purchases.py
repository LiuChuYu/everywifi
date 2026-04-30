import json


def _create_user(client, username="user1"):
    rv = client.post(
        "/users",
        data=json.dumps({"username": username, "email": f"{username}@example.com", "password": "pw"}),
        content_type="application/json",
    )
    return rv.get_json()["id"]


def _create_plan(client, name="Basic", mb=500):
    rv = client.post(
        "/plans",
        data=json.dumps({"name": name, "price": 50, "data_limit_mb": mb, "duration_days": 1}),
        content_type="application/json",
    )
    return rv.get_json()["id"]


def test_create_purchase(client):
    user_id = _create_user(client)
    plan_id = _create_plan(client)
    rv = client.post(
        "/purchases",
        data=json.dumps({"user_id": user_id, "plan_id": plan_id}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["user_id"] == user_id
    assert data["plan_id"] == plan_id
    assert data["payment_status"] == "pending"


def test_pay_purchase(client):
    user_id = _create_user(client, "u2")
    plan_id = _create_plan(client, "P2")
    rv = client.post(
        "/purchases",
        data=json.dumps({"user_id": user_id, "plan_id": plan_id}),
        content_type="application/json",
    )
    purchase_id = rv.get_json()["id"]
    rv2 = client.post(f"/purchases/{purchase_id}/pay")
    assert rv2.status_code == 200
    data = rv2.get_json()
    assert data["payment_status"] == "paid"
    assert data["expires_at"] is not None
    assert data["is_active"] is True


def test_pay_purchase_twice(client):
    user_id = _create_user(client, "u3")
    plan_id = _create_plan(client, "P3")
    rv = client.post(
        "/purchases",
        data=json.dumps({"user_id": user_id, "plan_id": plan_id}),
        content_type="application/json",
    )
    purchase_id = rv.get_json()["id"]
    client.post(f"/purchases/{purchase_id}/pay")
    rv2 = client.post(f"/purchases/{purchase_id}/pay")
    assert rv2.status_code == 400


def test_get_purchase(client):
    user_id = _create_user(client, "u4")
    plan_id = _create_plan(client, "P4")
    rv = client.post(
        "/purchases",
        data=json.dumps({"user_id": user_id, "plan_id": plan_id}),
        content_type="application/json",
    )
    purchase_id = rv.get_json()["id"]
    rv2 = client.get(f"/purchases/{purchase_id}")
    assert rv2.status_code == 200
    assert rv2.get_json()["id"] == purchase_id


def test_get_user_purchases(client):
    user_id = _create_user(client, "u5")
    plan_id = _create_plan(client, "P5")
    client.post(
        "/purchases",
        data=json.dumps({"user_id": user_id, "plan_id": plan_id}),
        content_type="application/json",
    )
    rv = client.get(f"/purchases/user/{user_id}")
    assert rv.status_code == 200
    assert len(rv.get_json()) == 1


def test_create_purchase_missing_fields(client):
    rv = client.post(
        "/purchases",
        data=json.dumps({"user_id": 1}),
        content_type="application/json",
    )
    assert rv.status_code == 400
