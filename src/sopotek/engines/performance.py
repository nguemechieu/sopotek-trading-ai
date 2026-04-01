from __future__ import annotations

import math

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import PerformanceMetrics, PortfolioSnapshot, TradeFeedback


class PerformanceEngine:
    def __init__(self, event_bus: AsyncEventBus) -> None:
        self.bus = event_bus
        self.total_trades = 0
        self.closed_trades = 0
        self.realized_pnl = 0.0
        self.returns: list[float] = []
        self.max_drawdown_pct = 0.0
        self.latest_metrics = PerformanceMetrics()

        self.bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self.bus.subscribe(EventType.TRADE_FEEDBACK, self._on_trade_feedback)
        self.bus.subscribe(EventType.PORTFOLIO_SNAPSHOT, self._on_portfolio_snapshot)

    async def _on_order_filled(self, event) -> None:
        del event
        self.total_trades += 1

    async def _on_trade_feedback(self, event) -> None:
        feedback = getattr(event, "data", None)
        if feedback is None:
            return
        if not isinstance(feedback, TradeFeedback):
            feedback = TradeFeedback(**dict(feedback))
        self.closed_trades += 1
        self.realized_pnl += float(feedback.pnl)
        capital_base = max(abs(float(feedback.entry_price * feedback.quantity)), 1e-9)
        self.returns.append(float(feedback.pnl) / capital_base)

    async def _on_portfolio_snapshot(self, event) -> None:
        snapshot = getattr(event, "data", None)
        if snapshot is None:
            return
        if not isinstance(snapshot, PortfolioSnapshot):
            snapshot = PortfolioSnapshot(**dict(snapshot))
        self.max_drawdown_pct = max(self.max_drawdown_pct, float(snapshot.drawdown_pct or 0.0))
        wins = sum(1 for value in self.returns if value > 0)
        mean_return = sum(self.returns) / len(self.returns) if self.returns else 0.0
        variance = sum((value - mean_return) ** 2 for value in self.returns) / len(self.returns) if self.returns else 0.0
        std_return = math.sqrt(max(variance, 0.0))
        sharpe_like = (mean_return / std_return) * math.sqrt(len(self.returns)) if std_return > 0 else 0.0
        self.latest_metrics = PerformanceMetrics(
            total_trades=self.total_trades,
            closed_trades=self.closed_trades,
            win_rate=(wins / self.closed_trades) if self.closed_trades else 0.0,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=float(snapshot.unrealized_pnl),
            equity=float(snapshot.equity),
            gross_exposure=float(snapshot.gross_exposure),
            net_exposure=float(snapshot.net_exposure),
            max_drawdown_pct=self.max_drawdown_pct,
            sharpe_like=sharpe_like,
            symbols=sorted(snapshot.positions.keys()),
        )
        await self.bus.publish(EventType.PERFORMANCE_METRICS, self.latest_metrics, priority=92, source="performance_engine")

