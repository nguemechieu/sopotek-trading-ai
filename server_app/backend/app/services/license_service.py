from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_license_access_token
from app.models.device import Device
from app.models.enums import LicensePlan, LicenseStatus, LogLevel, SubscriptionStatus
from app.models.license import License
from app.models.log import LogEntry
from app.models.subscription import Subscription
from app.models.user import User


LICENSE_KEY_PATTERN = re.compile(r"^SOPOTEK-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
LICENSE_ALPHABET = string.ascii_uppercase + string.digits


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    plan: LicensePlan
    label: str
    max_devices: int
    features: tuple[str, ...]
    interval: str | None = None
    price_id: str | None = None


class LicenseService:
    def __init__(self, settings) -> None:
        self.settings = settings

    def _hash_secret(self) -> str:
        return str(self.settings.license_key_pepper or self.settings.secret_key)

    def plan_catalog(self) -> list[PlanDefinition]:
        return [
            PlanDefinition(
                plan=LicensePlan.FREE,
                label="Free",
                max_devices=1,
                features=("workspace", "manual_trading", "market_monitoring"),
            ),
            PlanDefinition(
                plan=LicensePlan.PRO,
                label="Pro",
                max_devices=3,
                features=("workspace", "manual_trading", "ai_trading", "multi_exchange", "desktop_sync", "live_trading"),
                interval="month",
                price_id=self.settings.stripe_pro_monthly_price_id,
            ),
            PlanDefinition(
                plan=LicensePlan.ELITE,
                label="Elite",
                max_devices=10,
                features=(
                    "workspace",
                    "manual_trading",
                    "ai_trading",
                    "multi_exchange",
                    "desktop_sync",
                    "live_trading",
                    "portfolio_automation",
                    "institutional_risk",
                    "priority_support",
                ),
                interval="month",
                price_id=self.settings.stripe_elite_monthly_price_id,
            ),
        ]

    def plan_definition(self, plan: LicensePlan) -> PlanDefinition:
        for definition in self.plan_catalog():
            if definition.plan == plan:
                return definition
        raise KeyError(f"Unsupported license plan: {plan}")

    def normalize_license_key(self, license_key: str) -> str:
        return str(license_key or "").strip().upper()

    def hash_license_key(self, license_key: str) -> str:
        normalized = self.normalize_license_key(license_key)
        return hmac.new(
            self._hash_secret().encode("utf-8"),
            normalized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def hash_device_id(self, device_id: str) -> str:
        normalized = str(device_id or "").strip()
        return hmac.new(
            self._hash_secret().encode("utf-8"),
            normalized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def mask_license_key(self, license_key: str) -> str:
        parts = self.normalize_license_key(license_key).split("-")
        if len(parts) != 4:
            return "SOPOTEK-****-****-****"
        return f"{parts[0]}-{parts[1]}-****-{parts[3]}"

    def is_valid_license_key_format(self, license_key: str) -> bool:
        return bool(LICENSE_KEY_PATTERN.match(self.normalize_license_key(license_key)))

    def mask_device_hash(self, device_hash: str) -> str:
        normalized = str(device_hash or "").strip().upper()
        if len(normalized) < 12:
            return normalized or "unknown"
        return f"{normalized[:8]}...{normalized[-6:]}"

    def serialize_plan(self, definition: PlanDefinition) -> dict[str, object]:
        return {
            "plan": definition.plan.value,
            "label": definition.label,
            "billing_interval": definition.interval,
            "max_devices": definition.max_devices,
            "features": list(definition.features),
            "price_id": definition.price_id,
        }

    async def _generate_unique_license_key(self, session: AsyncSession) -> str:
        for _ in range(32):
            segments = [
                "".join(secrets.choice(LICENSE_ALPHABET) for _ in range(4)),
                "".join(secrets.choice(LICENSE_ALPHABET) for _ in range(4)),
                "".join(secrets.choice(LICENSE_ALPHABET) for _ in range(4)),
            ]
            raw_key = f"SOPOTEK-{segments[0]}-{segments[1]}-{segments[2]}"
            existing = await session.scalar(select(License.id).where(License.key_hash == self.hash_license_key(raw_key)))
            if existing is None:
                return raw_key
        raise RuntimeError("Unable to generate a unique license key")

    async def get_primary_license(self, session: AsyncSession, user_id: str) -> License | None:
        return await session.scalar(
            select(License).where(License.user_id == user_id).order_by(License.created_at.desc())
        )

    def _subscription_status_for_license_status(self, status: LicenseStatus) -> SubscriptionStatus:
        return SubscriptionStatus.ACTIVE if status == LicenseStatus.ACTIVE else SubscriptionStatus.SUSPENDED

    async def ensure_subscription_record(
        self,
        session: AsyncSession,
        *,
        license: License,
        provider: str,
        plan: LicensePlan,
        status: SubscriptionStatus,
    ) -> Subscription:
        subscription = await session.scalar(
            select(Subscription)
            .where(Subscription.license_id == license.id, Subscription.provider == provider)
            .order_by(Subscription.updated_at.desc())
        )
        if subscription is None:
            subscription = Subscription(
                user_id=license.user_id,
                license_id=license.id,
                provider=provider,
                plan=plan,
                status=status,
            )
            session.add(subscription)
        else:
            subscription.plan = plan
            subscription.status = status
        await session.flush()
        return subscription

    async def provision_free_license(self, session: AsyncSession, user: User) -> tuple[License, str | None]:
        existing = await self.get_primary_license(session, user.id)
        if existing is not None:
            if not existing.features_json:
                definition = self.plan_definition(existing.plan)
                existing.features_json = list(definition.features)
                existing.max_devices = definition.max_devices
            await self.ensure_subscription_record(
                session,
                license=existing,
                provider="internal",
                plan=existing.plan,
                status=SubscriptionStatus.ACTIVE,
            )
            await session.flush()
            return existing, None

        definition = self.plan_definition(LicensePlan.FREE)
        raw_key = await self._generate_unique_license_key(session)
        license = License(
            user_id=user.id,
            plan=LicensePlan.FREE,
            status=LicenseStatus.ACTIVE,
            key_hash=self.hash_license_key(raw_key),
            key_mask=self.mask_license_key(raw_key),
            max_devices=definition.max_devices,
            features_json=list(definition.features),
        )
        session.add(license)
        await session.flush()
        await self.ensure_subscription_record(
            session,
            license=license,
            provider="internal",
            plan=LicensePlan.FREE,
            status=SubscriptionStatus.ACTIVE,
        )
        return license, raw_key

    async def issue_license_key(self, session: AsyncSession, user: User) -> tuple[License, str]:
        license = await self.get_primary_license(session, user.id)
        if license is None:
            license, raw_key = await self.provision_free_license(session, user)
            return license, raw_key or await self._generate_unique_license_key(session)

        raw_key = await self._generate_unique_license_key(session)
        license.key_hash = self.hash_license_key(raw_key)
        license.key_mask = self.mask_license_key(raw_key)
        if not license.features_json:
            definition = self.plan_definition(license.plan)
            license.features_json = list(definition.features)
            license.max_devices = definition.max_devices
        await session.flush()
        return license, raw_key

    async def issue_admin_license_key(
        self,
        session: AsyncSession,
        *,
        user: User,
        plan: LicensePlan,
        status: LicenseStatus = LicenseStatus.ACTIVE,
        max_devices: int | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[License, str]:
        definition = self.plan_definition(plan)
        license = await self.get_primary_license(session, user.id)
        raw_key = await self._generate_unique_license_key(session)
        resolved_max_devices = max_devices if max_devices is not None else definition.max_devices
        if license is None:
            license = License(
                user_id=user.id,
                plan=plan,
                status=status,
                key_hash=self.hash_license_key(raw_key),
                key_mask=self.mask_license_key(raw_key),
                max_devices=resolved_max_devices,
                features_json=list(definition.features),
                expires_at=expires_at,
            )
            session.add(license)
        else:
            license.plan = plan
            license.status = status
            license.key_hash = self.hash_license_key(raw_key)
            license.key_mask = self.mask_license_key(raw_key)
            license.max_devices = resolved_max_devices
            license.features_json = list(definition.features)
            license.expires_at = expires_at
        await session.flush()
        await self.ensure_subscription_record(
            session,
            license=license,
            provider="internal",
            plan=plan,
            status=self._subscription_status_for_license_status(status),
        )
        await session.flush()
        return license, raw_key

    async def update_license_admin(
        self,
        session: AsyncSession,
        *,
        license: License,
        plan: LicensePlan | None = None,
        status: LicenseStatus | None = None,
        max_devices: int | None = None,
        expires_at: datetime | None = None,
        clear_expires_at: bool = False,
    ) -> License:
        resolved_plan = plan or license.plan
        if plan is not None:
            definition = self.plan_definition(resolved_plan)
            license.plan = resolved_plan
            license.features_json = list(definition.features)
            if max_devices is None:
                license.max_devices = definition.max_devices
        if max_devices is not None:
            license.max_devices = max_devices
        if status is not None:
            license.status = status
        if clear_expires_at:
            license.expires_at = None
        elif expires_at is not None:
            license.expires_at = expires_at
        await session.flush()
        await self.ensure_subscription_record(
            session,
            license=license,
            provider="internal",
            plan=license.plan,
            status=self._subscription_status_for_license_status(license.status),
        )
        await session.flush()
        return license

    async def log_security_event(
        self,
        session: AsyncSession,
        *,
        license: License | None,
        user_id: str | None,
        message: str,
        payload: dict[str, object],
        level: LogLevel = LogLevel.WARNING,
    ) -> None:
        session.add(
            LogEntry(
                user_id=user_id,
                category="license_security",
                source="license-service",
                level=level,
                message=message,
                payload=payload,
            )
        )
        if license is not None:
            license.suspicious_events += 1

    async def summarize_license(self, session: AsyncSession, license: License) -> dict[str, object]:
        active_devices = int(
            await session.scalar(
                select(func.count(Device.id)).where(Device.license_id == license.id, Device.is_active.is_(True))
            )
            or 0
        )
        subscription = await session.scalar(
            select(Subscription).where(Subscription.license_id == license.id).order_by(Subscription.updated_at.desc())
        )
        return {
            "id": license.id,
            "plan": license.plan.value,
            "status": license.status.value,
            "license_key_masked": license.key_mask,
            "max_devices": license.max_devices,
            "active_devices": active_devices,
            "features": list(license.features_json or self.plan_definition(license.plan).features),
            "expires_at": license.expires_at,
            "suspicious_events": license.suspicious_events,
            "subscription_status": getattr(subscription, "status", None).value if subscription is not None else None,
            "stripe_customer_id": license.stripe_customer_id,
            "created_at": license.created_at,
            "updated_at": license.updated_at,
        }

    async def summarize_license_admin(self, session: AsyncSession, license: License, user: User) -> dict[str, object]:
        summary = await self.summarize_license(session, license)
        devices = (
            await session.scalars(
                select(Device).where(Device.license_id == license.id).order_by(Device.updated_at.desc(), Device.created_at.desc())
            )
        ).all()
        summary.update(
            {
                "user_id": user.id,
                "user_email": user.email,
                "user_username": user.username,
                "user_full_name": user.full_name,
                "user_role": user.role.value,
                "user_is_active": bool(user.is_active),
                "failed_validation_count": license.failed_validation_count,
                "validation_count": license.validation_count,
                "last_validated_at": license.last_validated_at,
                "last_validated_ip": license.last_validated_ip,
                "last_validated_version": license.last_validated_version,
                "devices": [
                    {
                        "id": device.id,
                        "device_hash_masked": self.mask_device_hash(device.device_hash),
                        "app_version": device.app_version,
                        "last_ip": device.last_ip,
                        "validation_count": device.validation_count,
                        "is_active": bool(device.is_active),
                        "created_at": device.created_at,
                        "updated_at": device.updated_at,
                    }
                    for device in devices
                ],
            }
        )
        return summary

    async def list_admin_licenses(self, session: AsyncSession) -> list[dict[str, object]]:
        rows = (
            await session.execute(
                select(License, User).join(User, User.id == License.user_id).order_by(License.updated_at.desc(), License.created_at.desc())
            )
        ).all()
        items: list[dict[str, object]] = []
        for license, user in rows:
            items.append(await self.summarize_license_admin(session, license, user))
        return items

    async def validate_license(
        self,
        session: AsyncSession,
        *,
        license_key: str,
        device_id: str,
        app_version: str,
        request_ip: str | None,
    ) -> dict[str, object]:
        if not self.is_valid_license_key_format(license_key):
            return {"valid": False, "message": "Invalid license key format"}

        license = await session.scalar(select(License).where(License.key_hash == self.hash_license_key(license_key)))
        if license is None:
            return {"valid": False, "message": "License not found"}
        user = await session.scalar(select(User).where(User.id == license.user_id))
        if user is None or not user.is_active:
            return {"valid": False, "message": "License owner is inactive"}
        if license.status != LicenseStatus.ACTIVE:
            return {"valid": False, "message": f"License is {license.status.value}"}
        if license.expires_at is not None and license.expires_at <= datetime.now(timezone.utc):
            license.status = LicenseStatus.EXPIRED
            await session.flush()
            await session.commit()
            return {"valid": False, "message": "License has expired"}

        device_hash = self.hash_device_id(device_id)
        device = await session.scalar(
            select(Device).where(Device.license_id == license.id, Device.device_hash == device_hash)
        )
        if device is None:
            active_device_count = int(
                await session.scalar(
                    select(func.count(Device.id)).where(Device.license_id == license.id, Device.is_active.is_(True))
                )
                or 0
            )
            if active_device_count >= license.max_devices:
                license.failed_validation_count += 1
                await self.log_security_event(
                    session,
                    license=license,
                    user_id=user.id,
                    message="Device binding limit exceeded",
                    payload={
                        "license_id": license.id,
                        "device_hash": device_hash,
                        "request_ip": request_ip,
                        "app_version": app_version,
                        "max_devices": license.max_devices,
                    },
                )
                await session.flush()
                await session.commit()
                return {"valid": False, "message": "Device limit exceeded"}
            device = Device(
                license_id=license.id,
                user_id=user.id,
                device_hash=device_hash,
                app_version=app_version,
                last_ip=request_ip,
                validation_count=1,
                is_active=True,
            )
            session.add(device)
        else:
            device.app_version = app_version
            device.last_ip = request_ip
            device.validation_count += 1
            device.is_active = True

        license.validation_count += 1
        license.failed_validation_count = 0
        license.last_validated_at = datetime.now(timezone.utc)
        license.last_validated_ip = request_ip
        license.last_validated_version = app_version

        features = list(license.features_json or self.plan_definition(license.plan).features)
        access_token, token_expires_at = create_license_access_token(
            subject=license.id,
            user_id=user.id,
            plan=license.plan.value,
            features=features,
            device_hash=device_hash,
            settings=self.settings,
        )
        offline_valid_until = datetime.now(timezone.utc) + timedelta(hours=self.settings.license_offline_grace_hours)

        await session.flush()
        await session.commit()
        return {
            "valid": True,
            "plan": license.plan.value,
            "features": features,
            "expires_at": license.expires_at,
            "offline_valid_until": offline_valid_until,
            "access_token": access_token,
            "token_expires_at": token_expires_at,
            "max_devices": license.max_devices,
            "active_devices": int(
                await session.scalar(
                    select(func.count(Device.id)).where(Device.license_id == license.id, Device.is_active.is_(True))
                )
                or 0
            ),
        }

    async def apply_subscription_state(
        self,
        session: AsyncSession,
        *,
        license: License,
        plan: LicensePlan,
        status: SubscriptionStatus,
        provider: str,
        current_period_end: datetime | None,
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
        stripe_price_id: str | None,
        failure_reason: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Subscription:
        definition = self.plan_definition(plan)
        license.plan = plan
        license.max_devices = definition.max_devices
        license.features_json = list(definition.features)
        license.expires_at = current_period_end
        license.stripe_customer_id = stripe_customer_id
        license.status = LicenseStatus.ACTIVE if status == SubscriptionStatus.ACTIVE else LicenseStatus.SUSPENDED

        subscription = await session.scalar(
            select(Subscription)
            .where(
                Subscription.license_id == license.id,
                Subscription.provider == provider,
            )
            .order_by(Subscription.updated_at.desc())
        )
        if subscription is None:
            subscription = Subscription(
                user_id=license.user_id,
                license_id=license.id,
                provider=provider,
            )
            session.add(subscription)

        subscription.plan = plan
        subscription.status = status
        subscription.stripe_customer_id = stripe_customer_id
        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.stripe_price_id = stripe_price_id
        subscription.current_period_end = current_period_end
        subscription.cancel_at_period_end = False
        subscription.failure_reason = failure_reason
        if status == SubscriptionStatus.ACTIVE:
            subscription.last_payment_at = datetime.now(timezone.utc)
        subscription.metadata_json = dict(metadata or {})
        await session.flush()
        return subscription

    async def suspend_license(
        self,
        session: AsyncSession,
        *,
        license: License,
        provider: str,
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
        stripe_price_id: str | None,
        failure_reason: str,
        metadata: dict[str, object] | None = None,
    ) -> Subscription:
        license.status = LicenseStatus.SUSPENDED
        subscription = await self.apply_subscription_state(
            session,
            license=license,
            plan=license.plan,
            status=SubscriptionStatus.SUSPENDED,
            provider=provider,
            current_period_end=license.expires_at,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=stripe_price_id,
            failure_reason=failure_reason,
            metadata=metadata,
        )
        return subscription
