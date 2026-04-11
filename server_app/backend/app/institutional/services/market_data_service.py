from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class MarketDataService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["market_data_service"])

    async def normalize_ingestion(self) -> None:
        """Normalize REST and WebSocket venue payloads into internal market topics."""
