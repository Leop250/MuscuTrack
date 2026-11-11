import os

import jwt

ACCOUNT = {"email": "leo@example.com", "password": "motdepasse123"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "auth-service"}


def test_register_creates_user_without_exposing_password(client):
    response = client.post("/register", json=ACCOUNT)
    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": ACCOUNT["email"]}


def test_register_rejects_duplicate_email_regardless_of_case(client):
    client.post("/register", json=ACCOUNT)
    response = client.post(
        "/register", json={**ACCOUNT, "email": ACCOUNT["email"].upper()}
    )
    assert response.status_code == 409


def test_register_rejects_invalid_data(client):
    bad_email = client.post("/register", json={**ACCOUNT, "email": "pas-un-email"})
    short_password = client.post("/register", json={**ACCOUNT, "password": "court"})
    assert bad_email.status_code == 422
    assert short_password.status_code == 422


def test_login_returns_valid_jwt(client):
    user_id = client.post("/register", json=ACCOUNT).json()["id"]
    response = client.post("/login", json=ACCOUNT)
    assert response.status_code == 200
    payload = jwt.decode(
        response.json()["access_token"],
        os.environ["JWT_SECRET"],
        algorithms=["HS256"],
    )
    assert payload["sub"] == str(user_id)
    assert payload["exp"] > payload["iat"]


def test_login_rejects_wrong_password(client):
    client.post("/register", json=ACCOUNT)
    response = client.post("/login", json={**ACCOUNT, "password": "mauvaismotdepasse"})
    assert response.status_code == 401


def test_login_rejects_unknown_email_with_same_message(client):
    client.post("/register", json=ACCOUNT)
    wrong_password = client.post(
        "/login", json={**ACCOUNT, "password": "mauvaismotdepasse"}
    )
    unknown_email = client.post(
        "/login", json={**ACCOUNT, "email": "inconnu@example.com"}
    )
    assert unknown_email.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_me_requires_token_and_returns_profile(client):
    assert client.get("/me").status_code == 401
    client.post("/register", json=ACCOUNT)
    token = client.post("/login", json=ACCOUNT).json()["access_token"]
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.json() == {"id": 1, "email": ACCOUNT["email"], "two_factor_enabled": False}
