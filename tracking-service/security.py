import os

import jwt

# Même clé que auth-service : ce service vérifie les jetons sans jamais en créer.
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN = "access"


def read_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.InvalidTokenError:
        return None
    # Refuse le jeton temporaire de la 2FA : seul un jeton d'accès complet est valable.
    if payload["type"] != ACCESS_TOKEN:
        return None
    return int(payload["sub"])
