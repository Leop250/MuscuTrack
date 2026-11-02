import os
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(hours=1)

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


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_LIFETIME}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
