import os

import httpx

# Les services sont joints par leur nom sur le réseau Docker (ou Kubernetes).
AUTH_URL = os.environ["AUTH_SERVICE_URL"].rstrip("/")
TRACKING_URL = os.environ["TRACKING_SERVICE_URL"].rstrip("/")

client = httpx.Client(timeout=10)


def call(base_url: str, method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.request(method, base_url + path, headers=headers, **kwargs)
    # Les erreurs 4xx sont traitées par les pages ; une erreur 5xx affiche la page d'erreur.
    if response.status_code >= 500:
        response.raise_for_status()
    return response


def auth(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    return call(AUTH_URL, method, path, token, **kwargs)


def tracking(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    return call(TRACKING_URL, method, path, token, **kwargs)


def error_detail(response: httpx.Response, default: str) -> str:
    # FastAPI renvoie un texte pour nos erreurs, une liste pour les erreurs de validation.
    try:
        detail = response.json().get("detail")
    except ValueError:
        return default
    return detail if isinstance(detail, str) else default
