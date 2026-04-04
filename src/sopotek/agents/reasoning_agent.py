from __future__ import annotations

from sopotek.agents.base import BaseAgent
from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import AnalystInsight, FeatureVector, ModelDecision, OrderBookSnapshot, ReasoningDecision, Signal


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


class ReasoningAgent(BaseAgent):
    """Publishes explainable trade rationale from live signals and features."""

    name = "reasoning_agent"

    def __init__(self) -> None:
        self.bus: AsyncEventBus | None = None
        self.latest_features: dict[str, FeatureVector] = {}
        self.latest_insights: dict[str, AnalystInsight] = {}
        self.latest_model_scores: dict[str, ModelDecision] = {}
        self.latest_order_books: dict[str, OrderBookSnapshot] = {}

    def attach(self, event_bus: AsyncEventBus) -> None:
        self.bus = event_bus
        event_bus.subscribe(EventType.FEATURE_VECTOR, self._on_feature_vector)
        event_bus.subscribe(EventType.ANALYST_INSIGHT, self._on_analyst_insight)
        event_bus.subscribe(EventType.MODEL_SCORE, self._on_model_score)
        event_bus.subscribe(EventType.ORDER_BOOK, self._on_order_book)
        event_bus.subscribe(EventType.SIGNAL, self._on_signal)

    async def _on_feature_vector(self, event) -> None:
        vector = getattr(event, "data", None)
        if vector is None:
            return
        if not isinstance(vector, FeatureVector):
            vector = FeatureVector(**dict(vector))
        self.latest_features[vector.symbol] = vector

    async def _on_analyst_insight(self, event) -> None:
        insight = getattr(event, "data", None)
        if insight is None:
            return
        if not isinstance(insight, AnalystInsight):
            insight = AnalystInsight(**dict(insight))
        self.latest_insights[insight.symbol] = insight

    async def _on_model_score(self, event) -> None:
        decision = getattr(event, "data", None)
        if decision is None:
            return
        if not isinstance(decision, ModelDecision):
            decision = ModelDecision(**dict(decision))
        self.latest_model_scores[decision.symbol] = decision

    async def _on_order_book(self, event) -> None:
        snapshot = getattr(event, "data", None)
        if snapshot is None:
            return
        if not isinstance(snapshot, OrderBookSnapshot):
            snapshot = OrderBookSnapshot(**dict(snapshot))
        self.latest_order_books[snapshot.symbol] = snapshot

    async def _on_signal(self, event) -> None:
        signal = getattr(event, "data", None)
        if signal is None or self.bus is None:
            return
        if not isinstance(signal, Signal):
            signal = Signal(**dict(signal))
        decision = self._build_decision(signal)
        await self.bus.publish(EventType.REASONING_DECISION, decision, priority=58, source=self.name)

    def _build_decision(self, signal: Signal) -> ReasoningDecision:
        features = dict((self.latest_features.get(signal.symbol).values if self.latest_features.get(signal.symbol) is not None else {}) or {})
        insight = self.latest_insights.get(signal.symbol)
        model_score = self.latest_model_scores.get(signal.symbol)
        side = str(signal.side).lower()
        regime = str(getattr(insight, "regime", "unknown") or "unknown")
        volatility = _safe_float(features.get("volatility"), _safe_float(getattr(insight, "volatility", 1.0)) - 1.0)
        rsi = _safe_float(features.get("rsi"), 50.0)
        ema_gap = _safe_float(features.get("ema_gap"), 0.0)
        imbalance = _safe_float(features.get("order_book_imbalance"), 0.0)
        model_probability = None if model_score is None else float(model_score.probability)

        support: list[str] = []
        warnings: list[str] = []

        if side == "buy":
            if regime == "bullish":
                support.append("trend is bullish")
            elif regime == "bearish":
                warnings.append("broader regime is bearish against a long")
            if rsi <= 35.0:
                support.append("RSI is oversold")
            elif rsi >= 70.0:
                warnings.append("RSI is stretched")
            if ema_gap > 0:
                support.append("fast EMA remains above slow EMA")
            if imbalance > 0.1:
                support.append("order book shows bid-side imbalance")
        else:
            if regime == "bearish":
                support.append("trend is bearish")
            elif regime == "bullish":
                warnings.append("broader regime is bullish against a short")
            if rsi >= 65.0:
                support.append("RSI is overbought")
            elif rsi <= 30.0:
                warnings.append("RSI is already washed out")
            if ema_gap < 0:
                support.append("fast EMA remains below slow EMA")
            if imbalance < -0.1:
                support.append("order book shows ask-side imbalance")

        if volatility <= 0.02:
            support.append("volatility is controlled")
        elif volatility >= 0.04:
            warnings.append("volatility is elevated")

        if model_probability is not None:
            if model_probability >= 0.7:
                support.append(f"ML confidence is strong at {model_probability:.2f}")
            elif model_probability < 0.45:
                warnings.append(f"ML confidence is weak at {model_probability:.2f}")

        if not support:
            support.append("signal momentum and live context are aligned enough to review")

        reasoning = f"{str(side).upper()} because " + ", ".join(support[:4]) + "."
        if warnings:
            reasoning += " Watch-outs: " + "; ".join(warnings[:3]) + "."

        risk = "low" if not warnings and signal.confidence >= 0.65 else "high" if len(warnings) >= 2 or volatility >= 0.04 else "medium"
        return ReasoningDecision(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            side=signal.side,
            decision=str(signal.side).upper(),
            confidence=float(signal.confidence),
            reasoning=reasoning,
            risk=risk,
            regime=regime,
            model_probability=model_probability,
            warnings=warnings,
            features={key: _safe_float(value) for key, value in features.items()},
            metadata={
                "preferred_strategy": getattr(insight, "preferred_strategy", None),
                "signal_reason": signal.reason,
                "order_book_seen": signal.symbol in self.latest_order_books,
            },
            timestamp=signal.timestamp,
        )
