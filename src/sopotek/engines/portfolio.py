from __future__ import annotations

from typing import Any

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
        self.position_metadata: dict[str, dict[str, Any]] = {}
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
        prior_quantity = float(position.quantity)
        prior_average_price = float(position.average_price)
        prior_last_price = float(position.last_price)
        previous_trade_id = str(self.position_metadata.get(report.symbol, {}).get("trade_id") or report.order_id)

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
        self.position_metadata[report.symbol] = self._build_position_metadata(
            report,
            trade_id=report.metadata.get("trade_id") or previous_trade_id,
            position=position,
        )
        await self._publish_position_update(position, timestamp=report.timestamp)
        await self._publish_snapshot(timestamp=report.timestamp)
        if abs(prior_quantity) <= 1e-12 and abs(position.quantity) > 1e-12:
            await self._publish_position_open(report, position)
        elif abs(prior_quantity) > 1e-12 and abs(position.quantity) <= 1e-12:
            await self._publish_position_closed(
                report,
                trade_id=previous_trade_id,
                closed_quantity=prior_quantity,
                entry_price=prior_average_price,
                exit_price=price or prior_last_price or prior_average_price,
            )
            self.position_metadata.pop(report.symbol, None)
        elif abs(prior_quantity) > 1e-12 and abs(position.quantity) > 1e-12 and (prior_quantity > 0) != (position.quantity > 0):
            await self._publish_position_closed(
                report,
                trade_id=previous_trade_id,
                closed_quantity=prior_quantity,
                entry_price=prior_average_price,
                exit_price=price or prior_last_price or prior_average_price,
            )
            self.position_metadata[report.symbol] = self._build_position_metadata(
                report,
                trade_id=report.metadata.get("trade_id") or report.order_id,
                position=position,
            )
            await self._publish_position_open(report, position)

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
        await self._publish_position_update(position, timestamp=payload.get("timestamp"))
        await self._publish_snapshot(timestamp=payload.get("timestamp"))

    async def _publish_position_update(self, position: Position, *, timestamp: Any = None) -> None:
        payload = dict(
            symbol=position.symbol,
            quantity=float(position.quantity),
            average_price=float(position.average_price),
            current_price=float(position.last_price),
            unrealized_pnl=float(position.unrealized_pnl),
            realized_pnl=float(position.realized_pnl),
            market_value=float(position.market_value),
            metadata=dict(self.position_metadata.get(position.symbol, {})),
        )
        if timestamp is not None:
            payload["timestamp"] = timestamp
        update = PositionUpdate(**payload)
        await self.bus.publish(EventType.POSITION_UPDATE, update, priority=88, source="portfolio_engine")

    async def _publish_snapshot(self, *, timestamp: Any = None) -> None:
        unrealized = sum(position.unrealized_pnl for position in self.positions.values())
        realized = sum(position.realized_pnl for position in self.positions.values())
        gross_exposure = sum(abs(position.market_value) for position in self.positions.values())
        net_exposure = sum(position.market_value for position in self.positions.values())
        equity = self.cash + net_exposure
        self.peak_equity = max(self.peak_equity, equity)
        drawdown_pct = 0.0 if self.peak_equity <= 0 else max(0.0, (self.peak_equity - equity) / self.peak_equity)
        payload = dict(
            cash=self.cash,
            equity=equity,
            positions={symbol: position for symbol, position in self.positions.items()},
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            drawdown_pct=drawdown_pct,
        )
        if timestamp is not None:
            payload["timestamp"] = timestamp
        snapshot = PortfolioSnapshot(**payload)
        self.latest_snapshot = snapshot
        await self.bus.publish(EventType.PORTFOLIO_SNAPSHOT, snapshot, priority=90, source="portfolio_engine")

    async def _publish_position_open(self, report: ExecutionReport, position: Position) -> None:
        payload = {
            "trade_id": str(self.position_metadata.get(report.symbol, {}).get("trade_id") or report.order_id),
            "symbol": report.symbol,
            "quantity": float(position.quantity),
            "entry_time": report.timestamp,
            "entry_price": float(position.average_price or report.fill_price or report.requested_price or 0.0),
            "current_price": float(position.last_price or report.fill_price or report.requested_price or 0.0),
            "strategy_name": report.strategy_name,
            "expected_horizon": self.position_metadata.get(report.symbol, {}).get("expected_horizon", "medium"),
            "signal_expiry_time": self.position_metadata.get(report.symbol, {}).get("signal_expiry_time"),
            "volatility_at_entry": self.position_metadata.get(report.symbol, {}).get("volatility_at_entry", 0.0),
            "signal_strength": self.position_metadata.get(report.symbol, {}).get("signal_strength", 0.0),
            "asset_class": self.position_metadata.get(report.symbol, {}).get("asset_class", "unknown"),
            "metadata": dict(self.position_metadata.get(report.symbol, {})),
        }
        await self.bus.publish(EventType.POSITIONS_OPEN, payload, priority=87, source="portfolio_engine")

    async def _publish_position_closed(
        self,
        report: ExecutionReport,
        *,
        trade_id: str,
        closed_quantity: float,
        entry_price: float,
        exit_price: float,
    ) -> None:
        payload = {
            "trade_id": str(trade_id or report.order_id),
            "symbol": report.symbol,
            "close_time": report.timestamp,
            "quantity": float(closed_quantity),
            "entry_price": float(entry_price or 0.0),
            "exit_price": float(exit_price or 0.0),
            "reason": str(report.metadata.get("close_reason") or report.metadata.get("time_stop_reason") or "position_closed"),
            "metadata": dict(self.position_metadata.get(report.symbol, {})),
        }
        await self.bus.publish(EventType.POSITIONS_CLOSED, payload, priority=89, source="portfolio_engine")

    def _build_position_metadata(
        self,
        report: ExecutionReport,
        *,
        trade_id: str,
        position: Position,
    ) -> dict[str, Any]:
        metadata = dict(self.position_metadata.get(report.symbol, {}))
        metadata.update(dict(report.metadata or {}))
        metadata["trade_id"] = str(trade_id or report.order_id)
        metadata["strategy_name"] = str(report.strategy_name or metadata.get("strategy_name") or "unknown")
        metadata["expected_horizon"] = str(metadata.get("expected_horizon") or "medium")
        metadata["signal_expiry_time"] = metadata.get("signal_expiry_time")
        metadata["volatility_at_entry"] = float(metadata.get("volatility_at_entry") or metadata.get("volatility") or 0.0)
        metadata["signal_strength"] = float(metadata.get("signal_strength") or metadata.get("confidence") or 0.0)
        metadata["asset_class"] = str(metadata.get("asset_class") or "unknown")
        metadata["entry_price"] = float(position.average_price or report.fill_price or report.requested_price or 0.0)
        return metadata
