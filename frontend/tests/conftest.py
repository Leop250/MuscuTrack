import os

os.environ.update(
    AUTH_SERVICE_URL="http://auth-service:8000",
    TRACKING_SERVICE_URL="http://tracking-service:8000",
)

import httpx
import pytest
from fastapi.testclient import TestClient

import api
from main import app


class FakeServices:
    """Remplace auth-service et tracking-service : réponses prévues à l'avance, requêtes enregistrées."""

    def __init__(self):
        self.routes: dict[tuple[str, str], httpx.Response] = {}
        self.requests: list[httpx.Request] = []

    def on(self, method: str, url: str, status: int = 200, json=None) -> None:
        self.routes[(method, url)] = httpx.Response(status, json=json)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, str(request.url))
        if key not in self.routes:
            raise AssertionError(f"Appel inattendu : {key}")
        return self.routes[key]

    def last(self, method: str, url: str) -> httpx.Request:
        return next(r for r in reversed(self.requests) if (r.method, str(r.url)) == (method, url))


@pytest.fixture
def services(monkeypatch):
    fake = FakeServices()
    monkeypatch.setattr(api, "client", httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return fake


@pytest.fixture
def client(services):
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def logged_client(client):
    client.cookies.set("access_token", "jeton-utilisateur")
    return client
