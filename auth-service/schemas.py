from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    two_factor_required: bool = False
    access_token: str | None = None
    temporary_token: str | None = None
    token_type: str = "bearer"


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code: str


class TwoFactorCode(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class TwoFactorStatus(BaseModel):
    two_factor_enabled: bool


class TwoFactorLogin(TwoFactorCode):
    temporary_token: str
