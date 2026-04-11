from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class RiskEngineService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["risk_engine_service"])

    async def evaluate_pre_trade_limits(self) -> None:
        """Apply trade risk, exposure, and drawdown checks before execution."""
