from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class LicenseSubscriptionService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["license_subscription_service"])

    async def sync_stripe_entitlements(self) -> None:
        """Reconcile Stripe subscription state into license and feature gates."""
