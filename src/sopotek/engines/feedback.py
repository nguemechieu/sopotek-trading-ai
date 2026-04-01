from __future__ import annotations

from dataclasses import dataclass

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import ExecutionReport, FeatureVector, ModelDecision, TradeFeedback


@dataclass(slots=True)
class _OpenTrade:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    strategy_name: str
    timeframe: str
    features: dict[str, float]
    model_name: str | None
    model_probability: float | None
    metadata: dict


class TradeFeedbackEngine:
    """Turns filled trades into labeled feedback for retraining."""

    def __init__(self, event_bus: AsyncEventBus, *, default_timeframe: str = "1m") -> None:
        self.bus = event_bus
        self.default_timeframe = default_timeframe
        self.latest_features: dict[str, FeatureVector] = {}
        self.latest_model_scores: dict[str, ModelDecision] = {}
        self.open_trades: dict[str, _OpenTrade] = {}

        self.bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        self.bus.subscribe(EventType.MODEL_SCORE, self._on_model_score)
        self.bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)

    async def _on_feature_vector(self, event) -> None:
        vector = getattr(event, "data", None)
        if vector is None:
            return
        if not isinstance(vector, FeatureVector):
            vector = FeatureVector(**dict(vector))
        self.latest_features[vector.symbol] = vector

    async def _on_model_score(self, event) -> None:
        decision = getattr(event, "data", None)
        if decision is None:
            return
        if not isinstance(decision, ModelDecision):
            decision = ModelDecision(**dict(decision))
        self.latest_model_scores[decision.symbol] = decision

    async def _on_order_filled(self, event) -> None:
        report = getattr(event, "data", None)
        if report is None:
            return
        if not isinstance(report, ExecutionReport):
            report = ExecutionReport(**dict(report))
        fill_quantity = float(report.filled_quantity if report.filled_quantity is not None else report.quantity or 0.0)
        if fill_quantity <= 0:
            return

        side = str(report.side).lower()
        signed_quantity = fill_quantity if side == "buy" else -fill_quantity
        price = float(report.fill_price or report.requested_price or 0.0)
        existing = self.open_trades.get(report.symbol)

        if existing is None or (existing.quantity > 0 and signed_quantity > 0) or (existing.quantity < 0 and signed_quantity < 0):
            self._open_or_scale_trade(report, signed_quantity, price)
            return

        closed_quantity = min(abs(existing.quantity), abs(signed_quantity))
        pnl_direction = 1.0 if existing.quantity > 0 else -1.0
        pnl = (price - existing.entry_price) * closed_quantity * pnl_direction
        feedback = TradeFeedback(
            symbol=report.symbol,
            strategy_name=existing.strategy_name,
            side=existing.side,
            quantity=closed_quantity,
            entry_price=existing.entry_price,
            exit_price=price,
            pnl=pnl,
            success=pnl > 0,
            timeframe=existing.timeframe,
            model_name=existing.model_name,
            model_probability=existing.model_probability,
            features=dict(existing.features),
            metadata={**dict(existing.metadata), "exit_strategy": report.strategy_name, "exit_order_id": report.order_id},
        )
        await self.bus.publish(EventType.TRADE_FEEDBACK, feedback, priority=91, source="trade_feedback_engine")

        remaining_quantity = existing.quantity + signed_quantity
        if abs(remaining_quantity) <= 1e-12:
            self.open_trades.pop(report.symbol, None)
            return

        if (existing.quantity > 0 and remaining_quantity > 0) or (existing.quantity < 0 and remaining_quantity < 0):
            existing.quantity = remaining_quantity
            return

        self.open_trades.pop(report.symbol, None)
        self._open_or_scale_trade(report, remaining_quantity, price)

    def _open_or_scale_trade(self, report: ExecutionReport, signed_quantity: float, price: float) -> None:
        existing = self.open_trades.get(report.symbol)
        if existing is None:
            feature_vector = self.latest_features.get(report.symbol)
            decision = self.latest_model_scores.get(report.symbol)
            timeframe = str((report.metadata or {}).get("timeframe") or getattr(feature_vector, "timeframe", None) or self.default_timeframe)
            self.open_trades[report.symbol] = _OpenTrade(
                symbol=report.symbol,
                side=str(report.side).lower(),
                quantity=signed_quantity,
                entry_price=price,
                strategy_name=report.strategy_name,
                timeframe=timeframe,
                features=dict((feature_vector.values if feature_vector is not None else {}) or {}),
                model_name=getattr(decision, "model_name", None),
                model_probability=getattr(decision, "probability", None),
                metadata=dict(report.metadata or {}),
            )
            return

        new_quantity = existing.quantity + signed_quantity
        if abs(new_quantity) <= 1e-12:
            self.open_trades.pop(report.symbol, None)
            return
        weighted_entry = ((existing.entry_price * abs(existing.quantity)) + (price * abs(signed_quantity))) / max(abs(new_quantity), 1e-12)
        existing.entry_price = weighted_entry
        existing.quantity = new_quantity

