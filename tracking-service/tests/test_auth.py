from conftest import make_token


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok", "service": "tracking-service"}


def test_routes_require_a_token(client):
    for path in ("/sessions", "/exercises", "/records", "/records/best"):
        assert client.get(path).status_code == 401


def test_rejects_invalid_expired_and_2fa_pending_tokens(client):
    tokens = [
        "faux",
        make_token(1, lifetime_s=-10),
        make_token(1, token_type="2fa_pending"),
    ]
    for token in tokens:
        response = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
