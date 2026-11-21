from conftest import ADMIN_PASSWORD, ADMIN_USER


def test_register_and_login(client):
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
    assert resp.status_code == 201
    assert resp.get_json()["user"]["role"] == "user"

    resp = client.post("/api/auth/login", json={"username": "alice", "password": "secret123"})
    assert resp.status_code == 200
    assert resp.get_json()["access_token"]


def test_register_validation(client):
    assert client.post("/api/auth/register", json={"username": "ab", "password": "secret123"}).status_code == 400
    assert client.post("/api/auth/register", json={"username": "alice", "password": "123"}).status_code == 400


def test_duplicate_username_rejected(client):
    payload = {"username": "alice", "password": "secret123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 400


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert resp.status_code == 401


def test_admin_bootstrapped_from_env(client):
    resp = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["role"] == "admin"


def test_default_admin_credentials_do_not_exist(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 401


def test_protected_route_requires_auth(client):
    assert client.get("/api/documents").status_code == 401


def test_admin_route_forbidden_for_regular_user(client, user_headers):
    resp = client.delete("/api/documents/1", headers=user_headers)
    assert resp.status_code == 403


def test_admin_route_allowed_for_admin(client, admin_headers):
    resp = client.delete("/api/documents/999", headers=admin_headers)
    assert resp.status_code == 404  # authorised, but the document does not exist


def test_invalid_token_rejected(client):
    resp = client.get("/api/documents", headers={"Authorization": "Bearer not-a-token"})
    assert resp.status_code == 401


def test_debug_endpoints_removed(client, admin_headers):
    assert client.get("/api/debug/session", headers=admin_headers).status_code == 404
