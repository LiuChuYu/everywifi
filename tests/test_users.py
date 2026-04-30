import json


def test_create_user(client):
    rv = client.post(
        "/users",
        data=json.dumps({"username": "alice", "email": "alice@example.com", "password": "secret"}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    assert "id" in data


def test_create_user_duplicate_username(client):
    payload = {"username": "bob", "email": "bob@example.com", "password": "pw"}
    client.post("/users", data=json.dumps(payload), content_type="application/json")
    payload2 = {"username": "bob", "email": "bob2@example.com", "password": "pw"}
    rv = client.post("/users", data=json.dumps(payload2), content_type="application/json")
    assert rv.status_code == 409


def test_create_user_duplicate_email(client):
    client.post(
        "/users",
        data=json.dumps({"username": "charlie", "email": "same@example.com", "password": "pw"}),
        content_type="application/json",
    )
    rv = client.post(
        "/users",
        data=json.dumps({"username": "charlie2", "email": "same@example.com", "password": "pw"}),
        content_type="application/json",
    )
    assert rv.status_code == 409


def test_create_user_missing_fields(client):
    rv = client.post(
        "/users",
        data=json.dumps({"username": "x"}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_get_user(client):
    rv = client.post(
        "/users",
        data=json.dumps({"username": "dave", "email": "dave@example.com", "password": "pw"}),
        content_type="application/json",
    )
    user_id = rv.get_json()["id"]
    rv2 = client.get(f"/users/{user_id}")
    assert rv2.status_code == 200
    assert rv2.get_json()["username"] == "dave"


def test_get_user_not_found(client):
    rv = client.get("/users/9999")
    assert rv.status_code == 404


def test_login_success(client):
    client.post(
        "/users",
        data=json.dumps({"username": "eve", "email": "eve@example.com", "password": "mypass"}),
        content_type="application/json",
    )
    rv = client.post(
        "/users/login",
        data=json.dumps({"username": "eve", "password": "mypass"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert "token" in data
    assert len(data["token"]) > 0


def test_login_wrong_password(client):
    client.post(
        "/users",
        data=json.dumps({"username": "frank", "email": "frank@example.com", "password": "correct"}),
        content_type="application/json",
    )
    rv = client.post(
        "/users/login",
        data=json.dumps({"username": "frank", "password": "wrong"}),
        content_type="application/json",
    )
    assert rv.status_code == 404
