import json


def test_list_rate_cards_empty(client):
    rv = client.get("/rate-cards")
    assert rv.status_code == 200
    assert rv.get_json() == []


def test_create_rate_card(client):
    rv = client.post(
        "/rate-cards",
        data=json.dumps({"name": "Standard", "price_per_mb": 2000, "description": "2 TWD/MB"}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["name"] == "Standard"
    assert data["price_per_mb"] == 2000
    assert data["description"] == "2 TWD/MB"


def test_create_rate_card_duplicate(client):
    payload = {"name": "Dup", "price_per_mb": 1000}
    client.post("/rate-cards", data=json.dumps(payload), content_type="application/json")
    rv = client.post("/rate-cards", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 409


def test_create_rate_card_missing_fields(client):
    rv = client.post(
        "/rate-cards",
        data=json.dumps({"name": "No Price"}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_create_rate_card_invalid_price(client):
    rv = client.post(
        "/rate-cards",
        data=json.dumps({"name": "Bad", "price_per_mb": -1}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_create_rate_card_free(client):
    rv = client.post(
        "/rate-cards",
        data=json.dumps({"name": "Free", "price_per_mb": 0}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    assert rv.get_json()["price_per_mb"] == 0


def test_list_rate_cards(client):
    client.post("/rate-cards", data=json.dumps({"name": "A", "price_per_mb": 1000}), content_type="application/json")
    client.post("/rate-cards", data=json.dumps({"name": "B", "price_per_mb": 2000}), content_type="application/json")
    rv = client.get("/rate-cards")
    assert rv.status_code == 200
    assert len(rv.get_json()) == 2


def test_get_rate_card(client):
    rv = client.post(
        "/rate-cards",
        data=json.dumps({"name": "Premium", "price_per_mb": 5000}),
        content_type="application/json",
    )
    card_id = rv.get_json()["id"]
    rv2 = client.get(f"/rate-cards/{card_id}")
    assert rv2.status_code == 200
    assert rv2.get_json()["name"] == "Premium"

