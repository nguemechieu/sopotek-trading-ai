from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.user import User

try:
    import bcrypt as _bcrypt  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    _bcrypt = None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
PBKDF2_ITERATIONS = 600_000
PASSWORD_RESET_SCOPE = "password-reset"
ACCESS_TOKEN_SCOPE = "access"
REFRESH_TOKEN_SCOPE = "refresh"
EMAIL_VERIFICATION_SCOPE = "email-verify"
LICENSE_SESSION_SCOPE = "license-session"
TOTP_WINDOW_STEPS = 1


def hash_password(password: str) -> str:
    if _bcrypt is not None:
        return f"bcrypt${_bcrypt.hashpw(password.encode('utf-8'), _bcrypt.gensalt()).decode('utf-8')}"
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(derived).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    if str(password_hash or "").startswith("bcrypt$"):
        if _bcrypt is None:
            return False
        try:
            _, hashed = password_hash.split("$", 1)
            return bool(_bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")))
        except Exception:
            return False
    try:
        algorithm, raw_iterations, salt_b64, hash_b64 = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def _encode_jwt(payload: dict[str, Any], settings) -> str:
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_access_token(*, subject: str, role: str, settings, remember_me: bool = False) -> tuple[str, datetime]:
    minutes = (
        settings.remember_me_access_token_expire_minutes
        if remember_me
        else settings.access_token_expire_minutes
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "role": role, "scope": ACCESS_TOKEN_SCOPE, "exp": expires_at}
    return _encode_jwt(payload, settings), expires_at


def create_refresh_token(*, subject: str, role: str, settings, remember_me: bool = False) -> tuple[str, datetime]:
    minutes = (
        settings.remember_me_refresh_token_expire_minutes
        if remember_me
        else settings.refresh_token_expire_minutes
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "role": role, "scope": REFRESH_TOKEN_SCOPE, "exp": expires_at}
    return _encode_jwt(payload, settings), expires_at


def create_password_reset_token(*, subject: str, settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)
    payload = {"sub": subject, "scope": PASSWORD_RESET_SCOPE, "exp": expires_at}
    return _encode_jwt(payload, settings)


def create_email_verification_token(*, subject: str, settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.email_verification_token_expire_minutes)
    payload = {"sub": subject, "scope": EMAIL_VERIFICATION_SCOPE, "exp": expires_at}
    return _encode_jwt(payload, settings)


def create_license_access_token(
    *,
    subject: str,
    user_id: str,
    plan: str,
    features: list[str],
    device_hash: str,
    settings,
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.license_token_expire_minutes)
    payload = {
        "sub": subject,
        "uid": user_id,
        "scope": LICENSE_SESSION_SCOPE,
        "plan": plan,
        "features": features,
        "device": device_hash,
        "exp": expires_at,
    }
    return _encode_jwt(payload, settings), expires_at


def decode_access_token(token: str, settings) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc


def decode_password_reset_token(token: str, settings) -> dict[str, Any]:
    payload = decode_access_token(token, settings)
    if payload.get("scope") != PASSWORD_RESET_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
        )
    return payload


def decode_refresh_token(token: str, settings) -> dict[str, Any]:
    payload = decode_access_token(token, settings)
    if payload.get("scope") != REFRESH_TOKEN_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token",
        )
    return payload


def decode_email_verification_token(token: str, settings) -> dict[str, Any]:
    payload = decode_access_token(token, settings)
    if payload.get("scope") != EMAIL_VERIFICATION_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email verification token",
        )
    return payload


def build_auth_session(*, user: User, settings, remember_me: bool = False) -> dict[str, Any]:
    access_token, access_expires_at = create_access_token(
        subject=user.id,
        role=user.role.value,
        settings=settings,
        remember_me=remember_me,
    )
    refresh_token, refresh_expires_at = create_refresh_token(
        subject=user.id,
        role=user.role.value,
        settings=settings,
        remember_me=remember_me,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": access_expires_at,
        "refresh_expires_at": refresh_expires_at,
        "remember_me": remember_me,
    }


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_totp_uri(*, secret: str, email: str, issuer: str) -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}"
        f"?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def _normalize_base32_secret(secret: str) -> bytes:
    raw = str(secret or "").strip().upper().replace(" ", "")
    padded = raw + ("=" * ((8 - (len(raw) % 8)) % 8))
    return base64.b32decode(padded, casefold=True)


def _totp_code(secret: str, *, for_time: int) -> str:
    timestep = int(for_time // 30)
    secret_bytes = _normalize_base32_secret(secret)
    digest = hmac.new(secret_bytes, timestep.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = digest[offset : offset + 4]
    value = int.from_bytes(truncated, "big") & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp_code(secret: str, code: str, *, at_time: datetime | None = None) -> bool:
    normalized_code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(normalized_code) != 6:
        return False
    base_time = int((at_time or datetime.now(timezone.utc)).timestamp())
    for step in range(-TOTP_WINDOW_STEPS, TOTP_WINDOW_STEPS + 1):
        candidate = _totp_code(secret, for_time=base_time + (step * 30))
        if hmac.compare_digest(candidate, normalized_code):
            return True
    return False


async def get_db(request: Request):
    session_factory = request.app.state.session_factory
    async for session in get_db_session(session_factory):
        yield session


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token, request.app.state.settings)
    if payload.get("scope") not in {"", ACCESS_TOKEN_SCOPE, None}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    user = await db.scalar(select(User).where(User.id == subject))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_roles(*roles):
    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if roles and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _dependency
