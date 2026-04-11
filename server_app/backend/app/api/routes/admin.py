from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_license_service
from app.core.security import get_db, hash_password, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.license import AdminUserCreateRequest, AdminUserUpdateRequest, LicenseAdminUserResponse
from app.services.bootstrap import provision_user_defaults


router = APIRouter()


async def _serialize_admin_user(db: AsyncSession, user: User, license_service) -> LicenseAdminUserResponse:
    license = await license_service.get_primary_license(db, user.id)
    return LicenseAdminUserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        is_active=bool(user.is_active),
        email_verified=bool(user.email_verified),
        two_factor_enabled=bool(user.two_factor_enabled),
        current_license_id=getattr(license, "id", None),
        current_license_plan=getattr(license, "plan", None),
        current_license_status=getattr(license, "status", None),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _assert_not_removing_last_active_admin(db: AsyncSession, user: User, *, next_role: UserRole, next_is_active: bool) -> None:
    if user.role != UserRole.ADMIN or not user.is_active:
        return
    if next_role == UserRole.ADMIN and next_is_active:
        return

    remaining_admins = int(
        await db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.id != user.id,
            )
        )
        or 0
    )
    if remaining_admins <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one active admin account must remain available.",
        )


@router.patch("/users/{user_id}", response_model=LicenseAdminUserResponse)
async def update_admin_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> LicenseAdminUserResponse:
    _ = current_user
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    next_role = payload.role or user.role
    next_is_active = bool(payload.is_active) if payload.is_active is not None else bool(user.is_active)
    await _assert_not_removing_last_active_admin(db, user, next_role=next_role, next_is_active=next_is_active)

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.email_verified is not None:
        user.email_verified = payload.email_verified
    if payload.clear_two_factor_secret:
        user.two_factor_enabled = False
        user.two_factor_secret = None

    await db.commit()
    await db.refresh(user)
    return await _serialize_admin_user(db, user, license_service)


@router.post("/users", response_model=LicenseAdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> LicenseAdminUserResponse:
    _ = current_user
    existing = await db.scalar(
        select(User).where(
            or_(
                User.email == payload.email.lower(),
                User.username == payload.username.lower(),
            )
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = User(
        email=payload.email.lower(),
        username=payload.username.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
        email_verified=payload.email_verified,
    )
    db.add(user)
    await db.flush()
    await provision_user_defaults(db, user)
    await license_service.provision_free_license(db, user)
    await db.commit()
    await db.refresh(user)
    return await _serialize_admin_user(db, user, license_service)
