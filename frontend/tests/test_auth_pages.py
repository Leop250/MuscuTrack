import json

AUTH = "http://auth-service:8000"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "frontend"}


def test_protected_pages_redirect_to_login(client):
    for path in ("/dashboard", "/sessions", "/sessions/new", "/records", "/account"):
        response = client.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_login_sets_http_only_cookie(client, services):
    services.on("POST", f"{AUTH}/login", json={"access_token": "abc", "token_type": "bearer"})
    response = client.post("/login", data={"email": "leo@example.com", "password": "motdepasse123"})
    assert response.headers["location"] == "/dashboard"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("access_token=abc")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_login_error_is_shown(client, services):
    services.on("POST", f"{AUTH}/login", 401, {"detail": "Email ou mot de passe incorrect"})
    response = client.post("/login", data={"email": "leo@example.com", "password": "mauvais"})
    assert response.status_code == 401
    assert "Email ou mot de passe incorrect." in response.text


def test_login_with_2fa(client, services):
    services.on("POST", f"{AUTH}/login", json={"two_factor_required": True, "temporary_token": "temp"})
    response = client.post("/login", data={"email": "leo@example.com", "password": "motdepasse123"})
    assert response.headers["location"] == "/login/2fa"
    assert "access_token" not in client.cookies

    services.on("POST", f"{AUTH}/login/2fa", 401, {"detail": "Code incorrect"})
    assert "Code incorrect" in client.post("/login/2fa", data={"code": "000000"}).text

    services.on("POST", f"{AUTH}/login/2fa", json={"access_token": "final"})
    response = client.post("/login/2fa", data={"code": " 123456 "})
    assert response.headers["location"] == "/dashboard"
    assert json.loads(services.last("POST", f"{AUTH}/login/2fa").content) == {
        "temporary_token": "temp",
        "code": "123456",
    }
    assert client.cookies.get("access_token") == "final"


def test_2fa_page_needs_a_pending_login(client):
    assert client.get("/login/2fa").headers["location"] == "/login"


def test_register_checks_confirmation_then_logs_in(client, services):
    data = {"email": "leo@example.com", "password": "motdepasse123", "password_confirm": "autre"}
    assert "ne correspondent pas" in client.post("/register", data=data).text

    services.on("POST", f"{AUTH}/register", 201, {"id": 1, "email": "leo@example.com"})
    services.on("POST", f"{AUTH}/login", json={"access_token": "abc"})
    response = client.post("/register", data={**data, "password_confirm": "motdepasse123"})
    assert response.headers["location"] == "/dashboard"


def test_register_shows_duplicate_email(client, services):
    services.on("POST", f"{AUTH}/register", 409, {"detail": "Cet email est déjà utilisé"})
    data = {"email": "leo@example.com", "password": "motdepasse123", "password_confirm": "motdepasse123"}
    assert "Cet email est déjà utilisé" in client.post("/register", data=data).text


def test_logout_clears_cookie(logged_client):
    response = logged_client.post("/logout")
    assert response.headers["location"] == "/login"
    assert 'access_token=""' in response.headers["set-cookie"]


def test_expired_token_sends_back_to_login(logged_client, services):
    services.on("GET", f"{AUTH}/me", 401, {"detail": "Jeton invalide ou expiré"})
    response = logged_client.get("/account")
    assert response.headers["location"] == "/login"


def test_account_and_2fa_activation(logged_client, services):
    services.on("GET", f"{AUTH}/me", json={"id": 1, "email": "leo@example.com", "two_factor_enabled": False})
    assert "Activer la double authentification" in logged_client.get("/account").text

    setup = {"secret": "ABCDEF", "otpauth_uri": "otpauth://x", "qr_code": "data:image/png;base64,AAA"}
    services.on("POST", f"{AUTH}/2fa/setup", json=setup)
    page = logged_client.post("/account/2fa/setup").text
    assert "ABCDEF" in page and "data:image/png;base64,AAA" in page
    assert services.last("POST", f"{AUTH}/2fa/setup").headers["authorization"] == "Bearer jeton-utilisateur"

    services.on("POST", f"{AUTH}/2fa/verify", json={"two_factor_enabled": True})
    form = {"code": "123456", "secret": "ABCDEF", "qr_code": setup["qr_code"]}
    assert logged_client.post("/account/2fa/verify", data=form).headers["location"] == "/account"


def test_service_down_shows_error_page(logged_client, services):
    services.on("GET", f"{AUTH}/me", 500, {"detail": "boom"})
    response = logged_client.get("/account")
    assert response.status_code == 503
    assert "ne répond pas" in response.text
