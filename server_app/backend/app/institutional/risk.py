from __future__ import annotations

from dataclasses import dataclass, field

from .brokerage import AssetClass


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_risk_per_trade_pct: float = 0.01
    max_portfolio_exposure_pct: float = 1.50
    daily_drawdown_limit_pct: float = 0.03
    auto_liquidation_drawdown_pct: float = 0.05
    default_stop_buffer_pct: float = 0.0075


@dataclass(slots=True)
class PortfolioState:
    net_liquidation: float
    current_exposure: float
    daily_pnl: float
    active_positions: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    account_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_price: float | None
    asset_class: AssetClass


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str
    capped_quantity: float
    notional: float
    risk_amount: float
    exposure_after: float
    auto_liquidate: bool = False


class InstitutionalRiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def size_position(self, net_liquidation: float, entry_price: float, stop_price: float | None) -> float:
        stop = stop_price or (entry_price * (1.0 - self.limits.default_stop_buffer_pct))
        unit_risk = max(abs(entry_price - stop), entry_price * 0.0001)
        return (net_liquidation * self.limits.max_risk_per_trade_pct) / unit_risk

    def evaluate(self, portfolio: PortfolioState, order: ProposedOrder) -> RiskDecision:
        if portfolio.net_liquidation <= 0:
            return RiskDecision(
                approved=False,
                reason="Account is not funded.",
                capped_quantity=0.0,
                notional=0.0,
                risk_amount=0.0,
                exposure_after=portfolio.current_exposure,
            )

        drawdown_pct = max(0.0, (-portfolio.daily_pnl) / portfolio.net_liquidation)
        if drawdown_pct >= self.limits.auto_liquidation_drawdown_pct:
            return RiskDecision(
                approved=False,
                reason="Daily drawdown breached auto-liquidation threshold.",
                capped_quantity=0.0,
                notional=0.0,
                risk_amount=0.0,
                exposure_after=portfolio.current_exposure,
                auto_liquidate=True,
            )
        if drawdown_pct >= self.limits.daily_drawdown_limit_pct:
            return RiskDecision(
                approved=False,
                reason="Daily drawdown limit reached.",
                capped_quantity=0.0,
                notional=0.0,
                risk_amount=0.0,
                exposure_after=portfolio.current_exposure,
            )

        stop_price = order.stop_price or (
            order.entry_price
            * (1.0 - self.limits.default_stop_buffer_pct if order.side == "buy" else 1.0 + self.limits.default_stop_buffer_pct)
        )
        unit_risk = max(abs(order.entry_price - stop_price), order.entry_price * 0.0001)
        max_risk_amount = portfolio.net_liquidation * self.limits.max_risk_per_trade_pct
        max_trade_quantity = max_risk_amount / unit_risk

        max_exposure_amount = portfolio.net_liquidation * self.limits.max_portfolio_exposure_pct
        remaining_exposure = max(0.0, max_exposure_amount - portfolio.current_exposure)
        max_exposure_quantity = remaining_exposure / order.entry_price if order.entry_price else 0.0
        capped_quantity = min(order.quantity, max_trade_quantity, max_exposure_quantity)
        notional = capped_quantity * order.entry_price
        risk_amount = capped_quantity * unit_risk
        exposure_after = portfolio.current_exposure + notional

        if capped_quantity <= 0:
            return RiskDecision(
                approved=False,
                reason="No available exposure or trade risk budget remains.",
                capped_quantity=0.0,
                notional=0.0,
                risk_amount=0.0,
                exposure_after=portfolio.current_exposure,
            )

        approved = capped_quantity >= order.quantity
        reason = "approved" if approved else "approved_with_size_cap"
        return RiskDecision(
            approved=True,
            reason=reason,
            capped_quantity=capped_quantity,
            notional=notional,
            risk_amount=risk_amount,
            exposure_after=exposure_after,
        )
