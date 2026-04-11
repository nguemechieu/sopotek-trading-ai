from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole | None = None
    accept_terms: bool = False


class LoginRequest(BaseModel):
    identifier: str | None = Field(default=None, min_length=3, max_length=255)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    remember_me: bool = False
    otp_code: str | None = Field(default=None, min_length=6, max_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16)
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)
    remember_me: bool | None = None


class EmailVerificationRequest(BaseModel):
    token: str = Field(min_length=16)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    issuer: str


class TwoFactorConfirmRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=8)


class TwoFactorDisableRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=8)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool
    email_verified: bool
    two_factor_enabled: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: datetime | None = None
    refresh_expires_at: datetime | None = None
    remember_me: bool = False
    verification_required: bool = False
    email_verification_token: str | None = None
    email_verification_url: str | None = None
    user: UserResponse
