import os
from datetime import datetime, timedelta, timezone

# Valeurs factices, à définir avant d'importer l'application qui les lit.
os.environ.update(
    POSTGRES_USER="test",
    POSTGRES_PASSWORD="test",
    POSTGRES_HOST="localhost",
    POSTGRES_PORT="5432",
    POSTGRES_DB="test",
    JWT_SECRET="cle-factice-reservee-aux-tests-unitaires",
)

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app


def make_token(user_id: int, token_type: str = "access", lifetime_s: int = 3600) -> str:
    # Reproduit les jetons émis par auth-service.
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=lifetime_s),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


def auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


@pytest.fixture
def client():
    # SQLite en mémoire : chaque test repart d'une base vide, sans PostgreSQL.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Sans "with", le démarrage de l'application ne cherche pas à joindre PostgreSQL.
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()
