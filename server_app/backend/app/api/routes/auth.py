from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_auth_rate_limiter
from app.core.security import (
    build_auth_session,
    build_totp_uri,
    create_email_verification_token,
    create_password_reset_token,
    decode_email_verification_token,
    decode_password_reset_token,
    decode_refresh_token,
    generate_totp_secret,
    get_current_user,
    get_db,
    hash_password,
    verify_password,
    verify_totp_code,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    EmailVerificationRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    TwoFactorConfirmRequest,
    TwoFactorDisableRequest,
    TwoFactorSetupResponse,
    UserResponse,
)
from app.services.bootstrap import provision_user_defaults


router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return str(getattr(request.client, "host", "") or "unknown")


async def _enforce_auth_rate_limit(limiter, request: Request, scope: str, identifier: str) -> None:
    allowed, retry_after = await limiter.hit(scope, f"{_client_ip(request)}::{str(identifier or 'unknown').strip().lower()}")
    if allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many {scope.replace('-', ' ')} attempts. Retry in {int(retry_after)} seconds.",
        headers={"Retry-After": str(max(1, int(retry_after)))},
    )


def _resolve_login_identifier(payload: LoginRequest) -> str:
    return str(payload.identifier or payload.email or payload.username or "").strip().lower()


def _build_verification_preview(*, user: User, settings) -> tuple[str | None, str | None]:
    if user.email_verified:
        return None, None
    token = create_email_verification_token(subject=user.id, settings=settings)
    if settings.environment.lower() == "production":
        return None, None
    url = f"{settings.frontend_base_url.rstrip('/')}/login?verify_token={token}"
    return token, url


def _token_response_for_user(*, user: User, request: Request, remember_me: bool = False) -> TokenResponse:
    settings = request.app.state.settings
    session_payload = build_auth_session(user=user, settings=settings, remember_me=remember_me)
    verification_token, verification_url = _build_verification_preview(user=user, settings=settings)
    return TokenResponse(
        **session_payload,
        verification_required=not bool(user.email_verified),
        email_verification_token=verification_token,
        email_verification_url=verification_url,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter=Depends(get_auth_rate_limiter),
) -> TokenResponse:
    await _enforce_auth_rate_limit(limiter, request, "register", payload.email)
    if not payload.accept_terms:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You must accept the terms to register.")
    existing = await db.scalar(
        select(User).where(or_(User.email == payload.email.lower(), User.username == payload.username.lower()))
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user_count = int(await db.scalar(select(func.count(User.id))) or 0)
    if user_count > 0 and payload.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts must be created from the admin control center.",
        )
    requested_role = UserRole.ADMIN if user_count == 0 else (payload.role or UserRole.TRADER)
    user = User(
        email=payload.email.lower(),
        username=payload.username.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=requested_role,
        is_active=True,
        email_verified=False,
    )
    db.add(user)
    await db.flush()
    await provision_user_defaults(db, user)
    await request.app.state.license_service.provision_free_license(db, user)
    await db.commit()
    await db.refresh(user)

    await limiter.reset("register", f"{_client_ip(request)}::{payload.email.lower()}")
    return _token_response_for_user(user=user, request=request)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter=Depends(get_auth_rate_limiter),
) -> TokenResponse:
    identifier = _resolve_login_identifier(payload)
    if not identifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email or username is required")
    await _enforce_auth_rate_limit(limiter, request, "login", identifier)
    user = await db.scalar(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    settings = request.app.state.settings
    if settings.require_verified_email and not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your email before signing in")
    if user.two_factor_enabled:
        if not payload.otp_code or not user.two_factor_secret or not verify_totp_code(user.two_factor_secret, payload.otp_code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticator code")
    await limiter.reset("login", f"{_client_ip(request)}::{identifier}")
    return _token_response_for_user(user=user, request=request, remember_me=bool(payload.remember_me))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token_payload = decode_refresh_token(payload.refresh_token, request.app.state.settings)
    subject = str(token_payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid refresh token")
    user = await db.scalar(select(User).where(User.id == subject))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or inactive")
    remember_me = bool(payload.remember_me) if payload.remember_me is not None else False
    return _token_response_for_user(user=user, request=request, remember_me=remember_me)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter=Depends(get_auth_rate_limiter),
) -> ForgotPasswordResponse:
    await _enforce_auth_rate_limit(limiter, request, "forgot-password", payload.email)
    settings = request.app.state.settings
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    response = ForgotPasswordResponse(
        message="If that account exists, a password reset link has been prepared."
    )
    if user is None:
        return response

    reset_token = create_password_reset_token(subject=user.id, settings=settings)
    if settings.environment.lower() != "production":
        reset_url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={reset_token}"
        response.reset_token = reset_token
        response.reset_url = reset_url
    return response


@router.post("/reset-password", response_model=TokenResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token_payload = decode_password_reset_token(payload.token, request.app.state.settings)
    subject = str(token_payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password reset token")

    user = await db.scalar(select(User).where(User.id == subject))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or inactive")

    user.password_hash = hash_password(payload.password)
    await db.commit()
    await db.refresh(user)

    return _token_response_for_user(user=user, request=request)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(
    payload: EmailVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token_payload = decode_email_verification_token(payload.token, request.app.state.settings)
    subject = str(token_payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email verification token")
    user = await db.scalar(select(User).where(User.id == subject))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or inactive")
    user.email_verified = True
    await db.commit()
    await db.refresh(user)
    return _token_response_for_user(user=user, request=request)


@router.post("/resend-verification", response_model=ForgotPasswordResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter=Depends(get_auth_rate_limiter),
) -> ForgotPasswordResponse:
    await _enforce_auth_rate_limit(limiter, request, "email-verification", payload.email)
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    response = ForgotPasswordResponse(message="If that account exists, a verification link has been prepared.")
    if user is None:
        return response
    verification_token, verification_url = _build_verification_preview(user=user, settings=request.app.state.settings)
    response.reset_token = verification_token
    response.reset_url = verification_url
    return response


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorSetupResponse:
    secret = str(current_user.two_factor_secret or generate_totp_secret())
    current_user.two_factor_secret = secret
    await db.commit()
    issuer = "Sopotek Trading AI"
    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_url=build_totp_uri(secret=secret, email=current_user.email, issuer=issuer),
        issuer=issuer,
    )


@router.post("/2fa/confirm", response_model=UserResponse)
async def confirm_two_factor(
    payload: TwoFactorConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    secret = str(current_user.two_factor_secret or "").strip()
    if not secret or not verify_totp_code(secret, payload.otp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid authenticator code")
    current_user.two_factor_enabled = True
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.post("/2fa/disable", response_model=UserResponse)
async def disable_two_factor(
    payload: TwoFactorDisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    secret = str(current_user.two_factor_secret or "").strip()
    if current_user.two_factor_enabled and (not secret or not verify_totp_code(secret, payload.otp_code)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid authenticator code")
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
