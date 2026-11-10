import os
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
import segno
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN = "access"
PENDING_2FA_TOKEN = "2fa_pending"
ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
PENDING_2FA_TOKEN_LIFETIME = timedelta(minutes=5)
TOTP_ISSUER = "Muscu Track"

hasher = PasswordHasher()

# Vérifié quand l'email est inconnu, pour que la réponse prenne le même temps.
DUMMY_HASH = hasher.hash("mot-de-passe-factice")


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: int, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: int) -> str:
    return create_token(user_id, ACCESS_TOKEN, ACCESS_TOKEN_LIFETIME)


def create_pending_2fa_token(user_id: int) -> str:
    return create_token(user_id, PENDING_2FA_TOKEN, PENDING_2FA_TOKEN_LIFETIME)


def read_token(token: str, expected_type: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.InvalidTokenError:
        return None
    if payload["type"] != expected_type:
        return None
    return int(payload["sub"])


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


def qr_code_data_uri(uri: str) -> str:
    return segno.make(uri).png_data_uri(scale=6)


def verify_totp(secret: str, code: str) -> bool:
    # valid_window=1 accepte aussi le code précédent et le suivant (décalage d'horloge).
    return pyotp.TOTP(secret).verify(code, valid_window=1)
