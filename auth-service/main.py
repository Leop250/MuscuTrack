from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, engine, get_db, wait_for_db
from models import User
from schemas import Credentials, TokenResponse, UserResponse
from security import DUMMY_HASH, create_access_token, hash_password, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Muscu Track - auth-service", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-service"}


@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(credentials: Credentials, db: Session = Depends(get_db)) -> User:
    user = User(
        email=credentials.email.lower(),
        password_hash=hash_password(credentials.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet email est déjà utilisé")
    db.refresh(user)
    return user


@app.post("/login", response_model=TokenResponse)
def login(credentials: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == credentials.email.lower()))
    password_hash = user.password_hash if user else DUMMY_HASH
    if not verify_password(credentials.password, password_hash) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect")
    return TokenResponse(access_token=create_access_token(user.id))
