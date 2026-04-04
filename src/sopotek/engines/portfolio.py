from __future__ import annotations

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import ExecutionReport, PortfolioSnapshot, Position, PositionUpdate


class PortfolioEngine:
    def __init__(self, event_bus: AsyncEventBus, *, starting_cash: float = 100000.0) -> None:
        self.bus = event_bus
        self.starting_cash = float(starting_cash)
        self.cash = float(starting_cash)
        self.peak_equity = float(starting_cash)
        self.positions: dict[str, Position] = {}
        self.latest_snapshot = PortfolioSnapshot(cash=self.cash, equity=self.cash)
        self.bus.subscribe(EventType.ORDER_FILLED, self._on_fill)
        self.bus.subscribe(EventType.MARKET_TICK, self._on_tick)

    async def _on_fill(self, event) -> None:
        report = getattr(event, "data", None)
        if report is None:
            return
        if not isinstance(report, ExecutionReport):
            report = ExecutionReport(**dict(report))
        price = float(report.fill_price or report.requested_price or 0.0)
        quantity = float(report.filled_quantity if report.filled_quantity is not None else report.quantity)
        if quantity <= 0:
            return
        signed_quantity = quantity if str(report.side).lower() == "buy" else -quantity
        position = self.positions.setdefault(report.symbol, Position(symbol=report.symbol))

        if position.quantity == 0 or (position.quantity > 0) == (signed_quantity > 0):
            new_quantity = position.quantity + signed_quantity
            if new_quantity != 0:
                position.average_price = (
                    (position.quantity * position.average_price) + (signed_quantity * price)
                ) / new_quantity
            position.quantity = new_quantity
        else:
            prior_quantity = position.quantity
            closing_quantity = min(abs(position.quantity), abs(signed_quantity))
            pnl_direction = 1.0 if prior_quantity > 0 else -1.0
            position.realized_pnl += (price - position.average_price) * closing_quantity * pnl_direction
            position.quantity += signed_quantity
            if position.quantity == 0:
                position.average_price = 0.0
            elif (prior_quantity > 0 and position.quantity < 0) or (prior_quantity < 0 and position.quantity > 0):
                position.average_price = price

        position.last_price = price
        self.cash -= signed_quantity * price
        await self._publish_position_update(position)
        await self._publish_snapshot()

    async def _on_tick(self, event) -> None:
        payload = dict(getattr(event, "data", {}) or {})
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol or symbol not in self.positions:
            return
        price = float(payload.get("price") or payload.get("last") or payload.get("close") or 0.0)
        if price <= 0:
            return
        position = self.positions[symbol]
        position.last_price = price
        await self._publish_position_update(position)
        await self._publish_snapshot()

    async def _publish_position_update(self, position: Position) -> None:
        update = PositionUpdate(
            symbol=position.symbol,
            quantity=float(position.quantity),
            average_price=float(position.average_price),
            current_price=float(position.last_price),
            unrealized_pnl=float(position.unrealized_pnl),
            realized_pnl=float(position.realized_pnl),
            market_value=float(position.market_value),
        )
        await self.bus.publish(EventType.POSITION_UPDATE, update, priority=88, source="portfolio_engine")

    async def _publish_snapshot(self) -> None:
        unrealized = sum(position.unrealized_pnl for position in self.positions.values())
        realized = sum(position.realized_pnl for position in self.positions.values())
        gross_exposure = sum(abs(position.market_value) for position in self.positions.values())
        net_exposure = sum(position.market_value for position in self.positions.values())
        equity = self.cash + net_exposure
        self.peak_equity = max(self.peak_equity, equity)
        drawdown_pct = 0.0 if self.peak_equity <= 0 else max(0.0, (self.peak_equity - equity) / self.peak_equity)
        snapshot = PortfolioSnapshot(
            cash=self.cash,
            equity=equity,
            positions={symbol: position for symbol, position in self.positions.items()},
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            drawdown_pct=drawdown_pct,
        )
        self.latest_snapshot = snapshot
        await self.bus.publish(EventType.PORTFOLIO_SNAPSHOT, snapshot, priority=90, source="portfolio_engine")
