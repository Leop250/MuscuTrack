import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, engine, get_db, wait_for_db
from models import User
from schemas import (
    Credentials,
    LoginResponse,
    MeResponse,
    TokenResponse,
    TwoFactorCode,
    TwoFactorLogin,
    TwoFactorSetupResponse,
    TwoFactorStatus,
    UserResponse,
)
from security import (
    ACCESS_TOKEN,
    DUMMY_HASH,
    PENDING_2FA_TOKEN,
    create_access_token,
    create_pending_2fa_token,
    generate_totp_secret,
    hash_password,
    qr_code_data_uri,
    read_token,
    totp_uri,
    verify_password,
    verify_totp,
)

MAX_TOTP_ATTEMPTS = 5
TOTP_LOCK_SECONDS = 300

bearer = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Muscu Track - auth-service", lifespan=lifespan)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    user_id = read_token(credentials.credentials, ACCESS_TOKEN)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré")
    return user


def check_totp_code(user: User, code: str, db: Session) -> None:
    now = int(time.time())
    if user.totp_locked_until and user.totp_locked_until > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop d'essais, réessaie dans quelques minutes",
        )
    if verify_totp(user.totp_secret, code):
        user.totp_failed_attempts = 0
        user.totp_locked_until = None
        db.commit()
        return
    user.totp_failed_attempts += 1
    if user.totp_failed_attempts >= MAX_TOTP_ATTEMPTS:
        user.totp_failed_attempts = 0
        user.totp_locked_until = now + TOTP_LOCK_SECONDS
    db.commit()
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Code incorrect")


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


@app.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@app.post("/2fa/setup", response_model=TwoFactorSetupResponse)
def setup_two_factor(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TwoFactorSetupResponse:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "La 2FA est déjà activée")
    user.totp_secret = generate_totp_secret()
    db.commit()
    uri = totp_uri(user.totp_secret, user.email)
    return TwoFactorSetupResponse(
        secret=user.totp_secret, otpauth_uri=uri, qr_code=qr_code_data_uri(uri)
    )


@app.post("/2fa/verify", response_model=TwoFactorStatus)
def verify_two_factor(
    body: TwoFactorCode,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TwoFactorStatus:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "La 2FA est déjà activée")
    if user.totp_secret is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Appelle d'abord /2fa/setup")
    check_totp_code(user, body.code, db)
    user.totp_enabled = True
    db.commit()
    return TwoFactorStatus(two_factor_enabled=True)


@app.post("/login", response_model=LoginResponse, response_model_exclude_none=True)
def login(credentials: Credentials, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == credentials.email.lower()))
    password_hash = user.password_hash if user else DUMMY_HASH
    if not verify_password(credentials.password, password_hash) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect")
    if user.totp_enabled:
        return LoginResponse(
            two_factor_required=True,
            temporary_token=create_pending_2fa_token(user.id),
        )
    return LoginResponse(access_token=create_access_token(user.id))


@app.post("/login/2fa", response_model=TokenResponse)
def login_two_factor(
    body: TwoFactorLogin, db: Session = Depends(get_db)
) -> TokenResponse:
    user_id = read_token(body.temporary_token, PENDING_2FA_TOKEN)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.totp_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré")
    check_totp_code(user, body.code, db)
    return TokenResponse(access_token=create_access_token(user.id))
