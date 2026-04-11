from __future__ import annotations

from dataclasses import dataclass, field

from core.config import RiskConfig
from portfolio.capital_allocator import CapitalAllocationPlan
from risk.drawdown_controller import DrawdownController
from risk.exposure_manager import ExposureManager


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str
    adjusted_notional: float
    metadata: dict = field(default_factory=dict)


class RiskEngine:
    def __init__(
        self,
        *,
        config: RiskConfig | None = None,
        drawdown_controller: DrawdownController | None = None,
        exposure_manager: ExposureManager | None = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.drawdown_controller = drawdown_controller or DrawdownController(self.config.max_portfolio_drawdown)
        self.exposure_manager = exposure_manager or ExposureManager()
        self.kill_switch_reason: str | None = None

    @property
    def kill_switch_active(self) -> bool:
        return bool(self.kill_switch_reason)

    def arm_kill_switch(self, reason: str) -> None:
        self.kill_switch_reason = str(reason or "Kill switch activated").strip()

    def reset_kill_switch(self) -> None:
        self.kill_switch_reason = None

    def review(
        self,
        plan: CapitalAllocationPlan,
        *,
        account_equity: float,
        gross_exposure: float = 0.0,
        realized_volatility: float = 0.0,
        symbol_exposure: float = 0.0,
    ) -> RiskDecision:
        equity = max(0.0, float(account_equity or 0.0))
        if equity <= 0:
            return RiskDecision(False, "Account equity is zero.", 0.0, {})
        if self.kill_switch_active:
            return RiskDecision(False, self.kill_switch_reason or "Kill switch active.", 0.0, {})

        drawdown_status = self.drawdown_controller.evaluate(equity)
        if drawdown_status.breached:
            self.arm_kill_switch("Max portfolio drawdown breached.")
            return RiskDecision(False, self.kill_switch_reason or "Max portfolio drawdown breached.", 0.0, {"drawdown": drawdown_status.drawdown_pct})

        if float(realized_volatility or 0.0) >= self.config.abnormal_volatility_threshold:
            self.arm_kill_switch("Abnormal volatility kill switch triggered.")
            return RiskDecision(False, self.kill_switch_reason or "Abnormal volatility kill switch triggered.", 0.0, {"realized_volatility": realized_volatility})

        max_trade_notional = equity * self.config.max_risk_per_trade / max(float(plan.risk_estimate or 0.0), 1e-6)
        adjusted_notional = min(float(plan.target_notional or 0.0), max_trade_notional)
        projected_symbol = symbol_exposure + adjusted_notional
        if projected_symbol / equity > self.config.max_symbol_exposure_pct:
            return RiskDecision(False, "Max symbol exposure would be breached.", 0.0, {"projected_symbol_exposure_pct": projected_symbol / equity})
        projected_gross = gross_exposure + adjusted_notional
        if projected_gross / equity > self.config.max_gross_leverage:
            return RiskDecision(False, "Max leverage would be breached.", 0.0, {"projected_gross_leverage": projected_gross / equity})
        if adjusted_notional <= 0:
            return RiskDecision(False, "Risk engine scaled the order to zero.", 0.0, {})
        return RiskDecision(
            True,
            "Approved by institutional risk engine.",
            adjusted_notional,
            {
                "drawdown_pct": drawdown_status.drawdown_pct,
                "max_trade_notional": max_trade_notional,
                "projected_gross_leverage": projected_gross / equity,
            },
        )
