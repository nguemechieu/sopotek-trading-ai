from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LicensePlan, SubscriptionStatus
from app.models.license import License
from app.models.subscription import Subscription
from app.models.user import User
from app.services.license_service import LicenseService

try:
    import stripe
except Exception:  # pragma: no cover - optional dependency for local-only flows
    stripe = None  # type: ignore[assignment]


STRIPE_API_VERSION = "2026-02-25.clover"


def _to_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(float(value), timezone.utc)
    return None


class StripeBillingService:
    def __init__(self, settings, license_service: LicenseService) -> None:
        self.settings = settings
        self.license_service = license_service
        if stripe is not None and settings.stripe_secret_key:
            stripe.api_key = settings.stripe_secret_key
            stripe.api_version = STRIPE_API_VERSION
            stripe.max_network_retries = 2

    @property
    def enabled(self) -> bool:
        return bool(stripe is not None and self.settings.stripe_secret_key)

    def require_enabled(self) -> None:
        if not self.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe billing is not configured for this environment",
            )

    async def create_checkout_session(
        self,
        *,
        user: User,
        license: License,
        plan: LicensePlan,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        self.require_enabled()
        if plan == LicensePlan.FREE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Free plans do not require checkout")

        definition = self.license_service.plan_definition(plan)
        if not definition.price_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"No Stripe price configured for the {plan.value} plan",
            )

        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": definition.price_id, "quantity": 1}],
            customer_email=user.email,
            client_reference_id=user.id,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": user.id,
                "license_id": license.id,
                "plan": plan.value,
            },
            subscription_data={
                "metadata": {
                    "user_id": user.id,
                    "license_id": license.id,
                    "plan": plan.value,
                }
            },
        )
        return {"session_id": checkout_session["id"], "checkout_url": checkout_session["url"]}

    def construct_event(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        self.require_enabled()
        if not self.settings.stripe_webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe webhook secret is not configured",
            )
        if not signature:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature header")
        try:
            return stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=self.settings.stripe_webhook_secret)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook signature") from exc

    async def _resolve_license(
        self,
        session: AsyncSession,
        *,
        metadata: dict[str, Any],
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
    ) -> License | None:
        license_id = str(metadata.get("license_id") or "").strip()
        if license_id:
            return await session.scalar(select(License).where(License.id == license_id))
        if stripe_subscription_id:
            subscription = await session.scalar(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
            )
            if subscription is not None:
                return await session.scalar(select(License).where(License.id == subscription.license_id))
        if stripe_customer_id:
            return await session.scalar(select(License).where(License.stripe_customer_id == stripe_customer_id))
        return None

    async def handle_webhook(self, session: AsyncSession, *, payload: bytes, signature: str | None) -> dict[str, Any]:
        event = self.construct_event(payload, signature)
        event_type = str(event.get("type") or "")
        data = (event.get("data") or {}).get("object") or {}

        if event_type == "checkout.session.completed":
            metadata = dict(data.get("metadata") or {})
            license = await self._resolve_license(
                session,
                metadata=metadata,
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("subscription"),
            )
            if license is not None:
                plan = LicensePlan(str(metadata.get("plan") or license.plan.value))
                await self.license_service.apply_subscription_state(
                    session,
                    license=license,
                    plan=plan,
                    status=SubscriptionStatus.ACTIVE,
                    provider="stripe",
                    current_period_end=None,
                    stripe_customer_id=data.get("customer"),
                    stripe_subscription_id=data.get("subscription"),
                    stripe_price_id=None,
                    metadata=metadata,
                )

        if event_type == "invoice.payment_succeeded":
            lines = (data.get("lines") or {}).get("data") or []
            price_id = None
            if lines:
                price_id = ((lines[0].get("price") or {}) or {}).get("id")
            metadata = dict(data.get("metadata") or {})
            license = await self._resolve_license(
                session,
                metadata=metadata,
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("subscription"),
            )
            if license is not None:
                plan = license.plan
                if price_id == self.settings.stripe_pro_monthly_price_id:
                    plan = LicensePlan.PRO
                if price_id == self.settings.stripe_elite_monthly_price_id:
                    plan = LicensePlan.ELITE
                await self.license_service.apply_subscription_state(
                    session,
                    license=license,
                    plan=plan,
                    status=SubscriptionStatus.ACTIVE,
                    provider="stripe",
                    current_period_end=_to_datetime(data.get("period_end")),
                    stripe_customer_id=data.get("customer"),
                    stripe_subscription_id=data.get("subscription"),
                    stripe_price_id=price_id,
                    metadata=metadata,
                )

        if event_type == "invoice.payment_failed":
            metadata = dict(data.get("metadata") or {})
            license = await self._resolve_license(
                session,
                metadata=metadata,
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("subscription"),
            )
            if license is not None:
                await self.license_service.suspend_license(
                    session,
                    license=license,
                    provider="stripe",
                    stripe_customer_id=data.get("customer"),
                    stripe_subscription_id=data.get("subscription"),
                    stripe_price_id=None,
                    failure_reason=str(data.get("last_finalization_error") or "payment_failed"),
                    metadata=metadata,
                )

        await session.commit()
        return {"received": True, "event_type": event_type}
