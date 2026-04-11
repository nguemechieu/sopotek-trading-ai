from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class TradingCoreService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["trading_core_service"])

    async def submit_order_intent(self) -> None:
        """Translate validated strategy intent into routed venue orders."""
