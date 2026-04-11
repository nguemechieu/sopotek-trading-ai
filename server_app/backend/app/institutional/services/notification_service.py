from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class NotificationService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["notification_service"])

    async def dispatch_operator_alert(self) -> None:
        """Deliver critical alerts to desktop, email, Telegram, or SMS channels."""
