from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class PortfolioService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["portfolio_service"])

    async def recompute_holdings(self) -> None:
        """Revalue holdings, exposures, and PnL after fills or market moves."""
