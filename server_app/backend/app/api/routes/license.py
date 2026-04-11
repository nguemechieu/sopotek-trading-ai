from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_license_rate_limiter, get_license_service, get_stripe_service
from app.core.security import get_current_user, get_db, require_roles
from app.models.enums import UserRole
from app.models.license import License
from app.models.user import User
from app.schemas.license import (
    AdminLicenseIssueRequest,
    AdminLicenseIssueResponse,
    AdminLicenseUpdateRequest,
    CheckoutSessionCreateRequest,
    CheckoutSessionResponse,
    LicenseAdminEntryResponse,
    LicenseAdminOverviewResponse,
    LicenseAdminUserResponse,
    LicenseIssueResponse,
    LicensePlanResponse,
    LicenseSummaryResponse,
    LicenseValidationRequest,
    LicenseValidationResponse,
    StripeWebhookResponse,
)


router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return str(getattr(request.client, "host", "") or "unknown")


@router.get("/plans", response_model=list[LicensePlanResponse])
async def list_plans(license_service=Depends(get_license_service)) -> list[LicensePlanResponse]:
    return [LicensePlanResponse.model_validate(license_service.serialize_plan(plan)) for plan in license_service.plan_catalog()]


@router.get("/me", response_model=LicenseSummaryResponse)
async def get_my_license(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> LicenseSummaryResponse:
    license = await license_service.get_primary_license(db, current_user.id)
    if license is None:
        license, _ = await license_service.provision_free_license(db, current_user)
        await db.commit()
    payload = await license_service.summarize_license(db, license)
    return LicenseSummaryResponse.model_validate(payload)


@router.get("/admin/overview", response_model=LicenseAdminOverviewResponse)
async def get_license_admin_overview(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> LicenseAdminOverviewResponse:
    _ = current_user
    items = await license_service.list_admin_licenses(db)
    users = (await db.scalars(select(User).order_by(User.created_at.asc()))).all()
    latest_license_by_user = {}
    for item in items:
        latest_license_by_user.setdefault(item["user_id"], item)
    return LicenseAdminOverviewResponse(
        items=[LicenseAdminEntryResponse.model_validate(item) for item in items],
        users=[
            LicenseAdminUserResponse(
                id=user.id,
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role.value,
                is_active=bool(user.is_active),
                email_verified=bool(user.email_verified),
                two_factor_enabled=bool(user.two_factor_enabled),
                current_license_id=latest_license_by_user.get(user.id, {}).get("id"),
                current_license_plan=latest_license_by_user.get(user.id, {}).get("plan"),
                current_license_status=latest_license_by_user.get(user.id, {}).get("status"),
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
            for user in users
        ],
        plans=[LicensePlanResponse.model_validate(license_service.serialize_plan(plan)) for plan in license_service.plan_catalog()],
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/issue", response_model=LicenseIssueResponse, status_code=status.HTTP_201_CREATED)
async def issue_license_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> LicenseIssueResponse:
    license, raw_key = await license_service.issue_license_key(db, current_user)
    await db.commit()
    payload = await license_service.summarize_license(db, license)
    payload["license_key"] = raw_key
    return LicenseIssueResponse.model_validate(payload)


@router.post("/admin/issue", response_model=AdminLicenseIssueResponse, status_code=status.HTTP_201_CREATED)
async def issue_license_key_admin(
    payload: AdminLicenseIssueRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> AdminLicenseIssueResponse:
    _ = current_user
    user = await db.scalar(select(User).where(User.id == payload.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    license, raw_key = await license_service.issue_admin_license_key(
        db,
        user=user,
        plan=payload.plan,
        status=payload.status,
        max_devices=payload.max_devices,
        expires_at=payload.expires_at,
    )
    await db.commit()
    admin_payload = await license_service.summarize_license_admin(db, license, user)
    admin_payload["license_key"] = raw_key
    return AdminLicenseIssueResponse.model_validate(admin_payload)


@router.patch("/admin/{license_id}", response_model=LicenseAdminEntryResponse)
async def update_license_admin(
    license_id: str,
    payload: AdminLicenseUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> LicenseAdminEntryResponse:
    _ = current_user
    license = await db.scalar(select(License).where(License.id == license_id))
    if license is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    user = await db.scalar(select(User).where(User.id == license.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License owner not found")
    await license_service.update_license_admin(
        db,
        license=license,
        plan=payload.plan,
        status=payload.status,
        max_devices=payload.max_devices,
        expires_at=payload.expires_at,
        clear_expires_at=payload.clear_expires_at,
    )
    await db.commit()
    admin_payload = await license_service.summarize_license_admin(db, license, user)
    return LicenseAdminEntryResponse.model_validate(admin_payload)


@router.post("/validate", response_model=LicenseValidationResponse)
async def validate_license(
    payload: LicenseValidationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
    rate_limiter=Depends(get_license_rate_limiter),
) -> LicenseValidationResponse:
    settings = request.app.state.settings
    normalized_license = license_service.normalize_license_key(payload.license_key)
    rate_key = f"license-validate:{_client_ip(request)}:{normalized_license}"
    allowed, retry_after = rate_limiter.check(
        rate_key,
        limit=settings.license_validation_rate_limit,
        window_seconds=settings.license_validation_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many validation requests. Retry in {int(retry_after) + 1} seconds.",
        )

    result = await license_service.validate_license(
        db,
        license_key=payload.license_key,
        device_id=payload.device_id,
        app_version=payload.app_version,
        request_ip=_client_ip(request),
    )
    return LicenseValidationResponse.model_validate(result)


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
    stripe_service=Depends(get_stripe_service),
) -> CheckoutSessionResponse:
    license = await license_service.get_primary_license(db, current_user.id)
    if license is None:
        license, _ = await license_service.provision_free_license(db, current_user)
        await db.commit()
    session_payload = await stripe_service.create_checkout_session(
        user=current_user,
        license=license,
        plan=payload.plan,
        success_url=str(payload.success_url),
        cancel_url=str(payload.cancel_url),
    )
    return CheckoutSessionResponse(
        plan=payload.plan,
        session_id=session_payload["session_id"],
        checkout_url=session_payload["checkout_url"],
    )


@router.post("/stripe/webhook", response_model=StripeWebhookResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
    stripe_service=Depends(get_stripe_service),
) -> StripeWebhookResponse:
    result = await stripe_service.handle_webhook(
        db,
        payload=await request.body(),
        signature=stripe_signature,
    )
    return StripeWebhookResponse.model_validate(result)
