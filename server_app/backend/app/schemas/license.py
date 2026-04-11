from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.models.enums import LicensePlan, LicenseStatus, SubscriptionStatus, UserRole


class LicensePlanResponse(BaseModel):
    plan: LicensePlan
    label: str
    billing_interval: str | None = None
    max_devices: int
    features: list[str]
    price_id: str | None = None


class LicenseSummaryResponse(BaseModel):
    id: str
    plan: LicensePlan
    status: LicenseStatus
    license_key_masked: str
    max_devices: int
    active_devices: int
    features: list[str]
    expires_at: datetime | None
    suspicious_events: int
    subscription_status: SubscriptionStatus | None = None
    stripe_customer_id: str | None = None
    created_at: datetime
    updated_at: datetime


class LicenseIssueResponse(LicenseSummaryResponse):
    license_key: str


class LicenseDeviceAdminResponse(BaseModel):
    id: str
    device_hash_masked: str
    app_version: str
    last_ip: str | None = None
    validation_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LicenseAdminEntryResponse(LicenseSummaryResponse):
    user_id: str
    user_email: str
    user_username: str
    user_full_name: str | None = None
    user_role: str
    user_is_active: bool
    failed_validation_count: int
    validation_count: int
    last_validated_at: datetime | None = None
    last_validated_ip: str | None = None
    last_validated_version: str | None = None
    devices: list[LicenseDeviceAdminResponse] = Field(default_factory=list)


class LicenseAdminUserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str | None = None
    role: str
    is_active: bool
    email_verified: bool
    two_factor_enabled: bool = False
    current_license_id: str | None = None
    current_license_plan: LicensePlan | None = None
    current_license_status: LicenseStatus | None = None
    created_at: datetime
    updated_at: datetime


class LicenseAdminOverviewResponse(BaseModel):
    items: list[LicenseAdminEntryResponse] = Field(default_factory=list)
    users: list[LicenseAdminUserResponse] = Field(default_factory=list)
    plans: list[LicensePlanResponse] = Field(default_factory=list)
    generated_at: datetime


class AdminLicenseIssueRequest(BaseModel):
    user_id: str = Field(min_length=8, max_length=64)
    plan: LicensePlan = LicensePlan.FREE
    status: LicenseStatus = LicenseStatus.ACTIVE
    max_devices: int | None = Field(default=None, ge=1, le=100)
    expires_at: datetime | None = None


class AdminLicenseUpdateRequest(BaseModel):
    plan: LicensePlan | None = None
    status: LicenseStatus | None = None
    max_devices: int | None = Field(default=None, ge=1, le=100)
    expires_at: datetime | None = None
    clear_expires_at: bool = False


class AdminUserUpdateRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    email_verified: bool | None = None
    clear_two_factor_secret: bool = False


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = UserRole.ADMIN
    is_active: bool = True
    email_verified: bool = True


class AdminLicenseIssueResponse(LicenseAdminEntryResponse):
    license_key: str


class LicenseValidationRequest(BaseModel):
    license_key: str = Field(min_length=22, max_length=32)
    device_id: str = Field(min_length=8, max_length=255)
    app_version: str = Field(min_length=1, max_length=64)


class LicenseValidationResponse(BaseModel):
    valid: bool
    expires_at: datetime | None = None
    offline_valid_until: datetime | None = None
    token_expires_at: datetime | None = None
    plan: LicensePlan | None = None
    features: list[str] = Field(default_factory=list)
    access_token: str | None = None
    max_devices: int | None = None
    active_devices: int | None = None
    message: str | None = None


class CheckoutSessionCreateRequest(BaseModel):
    plan: LicensePlan
    success_url: HttpUrl
    cancel_url: HttpUrl


class CheckoutSessionResponse(BaseModel):
    plan: LicensePlan
    session_id: str
    checkout_url: HttpUrl


class StripeWebhookResponse(BaseModel):
    received: bool = True
    event_type: str
