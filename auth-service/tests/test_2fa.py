import time

import pyotp
import pytest

ACCOUNT = {"email": "leo@example.com", "password": "motdepasse123"}


def wrong_code(secret: str) -> str:
    # Un code toujours différent des codes acceptés (précédent, actuel, suivant).
    totp = pyotp.TOTP(secret)
    now = time.time()
    accepted = {totp.at(now, offset) for offset in (-1, 0, 1, 2)}
    return next(c for c in ("000000", "111111", "222222", "333333", "444444") if c not in accepted)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def access_token(client) -> str:
    client.post("/register", json=ACCOUNT)
    return client.post("/login", json=ACCOUNT).json()["access_token"]


@pytest.fixture
def secret(client, access_token) -> str:
    # Compte avec la 2FA activée.
    secret = client.post("/2fa/setup", headers=bearer(access_token)).json()["secret"]
    client.post(
        "/2fa/verify",
        headers=bearer(access_token),
        json={"code": pyotp.TOTP(secret).now()},
    )
    return secret


def temporary_token(client) -> str:
    return client.post("/login", json=ACCOUNT).json()["temporary_token"]


def test_setup_requires_authentication(client):
    assert client.post("/2fa/setup").status_code == 401
    assert client.post("/2fa/setup", headers=bearer("faux")).status_code == 401


def test_setup_returns_secret_and_qr_code(client, access_token):
    response = client.post("/2fa/setup", headers=bearer(access_token))
    assert response.status_code == 200
    body = response.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/Muscu%20Track:leo%40example.com")
    assert body["secret"] in body["otpauth_uri"]
    assert body["qr_code"].startswith("data:image/png;base64,")


def test_login_stays_simple_until_code_is_verified(client, access_token):
    client.post("/2fa/setup", headers=bearer(access_token))
    assert "access_token" in client.post("/login", json=ACCOUNT).json()


def test_verify_rejects_wrong_code_and_before_setup(client, access_token):
    before_setup = client.post(
        "/2fa/verify", headers=bearer(access_token), json={"code": "123456"}
    )
    assert before_setup.status_code == 400

    secret = client.post("/2fa/setup", headers=bearer(access_token)).json()["secret"]
    wrong = client.post(
        "/2fa/verify", headers=bearer(access_token), json={"code": wrong_code(secret)}
    )
    assert wrong.status_code == 401
    assert "access_token" in client.post("/login", json=ACCOUNT).json()


def test_code_must_have_six_digits(client, access_token):
    response = client.post(
        "/2fa/verify", headers=bearer(access_token), json={"code": "abc"}
    )
    assert response.status_code == 422


def test_setup_refused_once_enabled(client, access_token, secret):
    response = client.post("/2fa/setup", headers=bearer(access_token))
    assert response.status_code == 409


def test_login_with_2fa_returns_only_temporary_token(client, secret):
    body = client.post("/login", json=ACCOUNT).json()
    assert body["two_factor_required"] is True
    assert "temporary_token" in body
    assert "access_token" not in body


def test_full_login_with_valid_code(client, secret):
    response = client.post(
        "/login/2fa",
        json={
            "temporary_token": temporary_token(client),
            "code": pyotp.TOTP(secret).now(),
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    # Le jeton final est accepté : la 2FA étant active, /2fa/setup répond 409 et non 401.
    assert client.post("/2fa/setup", headers=bearer(token)).status_code == 409


def test_login_2fa_rejects_wrong_code(client, secret):
    response = client.post(
        "/login/2fa",
        json={"temporary_token": temporary_token(client), "code": wrong_code(secret)},
    )
    assert response.status_code == 401


def test_temporary_token_cannot_be_used_as_access_token(client, secret):
    response = client.post("/2fa/setup", headers=bearer(temporary_token(client)))
    assert response.status_code == 401


def test_access_token_cannot_replace_temporary_token(client, access_token, secret):
    response = client.post(
        "/login/2fa",
        json={"temporary_token": access_token, "code": pyotp.TOTP(secret).now()},
    )
    assert response.status_code == 401


def test_too_many_wrong_codes_lock_the_account(client, secret):
    token = temporary_token(client)
    bad = wrong_code(secret)
    for _ in range(5):
        response = client.post(
            "/login/2fa", json={"temporary_token": token, "code": bad}
        )
        assert response.status_code == 401

    # Même le bon code est refusé pendant le blocage.
    locked = client.post(
        "/login/2fa",
        json={"temporary_token": token, "code": pyotp.TOTP(secret).now()},
    )
    assert locked.status_code == 429


def test_lock_expires(client, secret, monkeypatch):
    token = temporary_token(client)
    bad = wrong_code(secret)
    for _ in range(5):
        client.post("/login/2fa", json={"temporary_token": token, "code": bad})

    # Avance l'horloge lue par check_totp_code au-delà des 5 minutes de blocage.
    real_time = time.time
    monkeypatch.setattr("main.time.time", lambda: real_time() + 301)
    response = client.post(
        "/login/2fa",
        json={"temporary_token": token, "code": pyotp.TOTP(secret).now()},
    )
    assert response.status_code == 200
