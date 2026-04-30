import json


def test_list_plans_empty(client):
    rv = client.get("/plans")
    assert rv.status_code == 200
    assert rv.get_json() == []


def test_create_plan(client):
    rv = client.post(
        "/plans",
        data=json.dumps({"name": "Day Pass", "price": 50, "data_limit_mb": 500, "duration_days": 1}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["name"] == "Day Pass"
    assert data["price"] == 50
    assert data["data_limit_mb"] == 500
    assert data["duration_days"] == 1


def test_create_plan_duplicate(client):
    payload = {"name": "Weekly", "price": 200, "data_limit_mb": 5000, "duration_days": 7}
    client.post("/plans", data=json.dumps(payload), content_type="application/json")
    rv = client.post("/plans", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 409


def test_create_plan_missing_fields(client):
    rv = client.post(
        "/plans",
        data=json.dumps({"name": "Bad Plan"}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_create_plan_invalid_price(client):
    rv = client.post(
        "/plans",
        data=json.dumps({"name": "Bad", "price": -1, "data_limit_mb": 100, "duration_days": 1}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_create_plan_unlimited_data(client):
    rv = client.post(
        "/plans",
        data=json.dumps({"name": "Unlimited", "price": 999, "data_limit_mb": 0, "duration_days": 30}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    assert rv.get_json()["data_limit_mb"] == 0


def test_list_plans(client):
    client.post(
        "/plans",
        data=json.dumps({"name": "P1", "price": 10, "data_limit_mb": 100, "duration_days": 1}),
        content_type="application/json",
    )
    client.post(
        "/plans",
        data=json.dumps({"name": "P2", "price": 20, "data_limit_mb": 200, "duration_days": 2}),
        content_type="application/json",
    )
    rv = client.get("/plans")
    assert rv.status_code == 200
    assert len(rv.get_json()) == 2


def test_get_plan(client):
    rv = client.post(
        "/plans",
        data=json.dumps({"name": "Monthly", "price": 500, "data_limit_mb": 20000, "duration_days": 30}),
        content_type="application/json",
    )
    plan_id = rv.get_json()["id"]
    rv2 = client.get(f"/plans/{plan_id}")
    assert rv2.status_code == 200
    assert rv2.get_json()["name"] == "Monthly"
