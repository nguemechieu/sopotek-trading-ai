from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Iterable

from sopotek.agents.base import BaseAgent
from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import Candle, Signal
from sopotek.ml.features import compute_indicator_features


class SignalAgent(BaseAgent, ABC):
    name = "signal_agent"

    def __init__(
        self,
        *,
        timeframe: str = "1m",
        lookback: int = 64,
        min_history: int = 25,
        default_quantity: float = 1.0,
        symbols: Iterable[str] | None = None,
    ) -> None:
        self.timeframe = timeframe
        self.lookback = max(16, int(lookback))
        self.min_history = max(10, int(min_history))
        self.default_quantity = max(0.0001, float(default_quantity))
        self.enabled_symbols = {str(symbol) for symbol in (symbols or [])}
        self.history: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=self.lookback))
        self.bus: AsyncEventBus | None = None

    def attach(self, event_bus: AsyncEventBus) -> None:
        self.bus = event_bus
        event_bus.subscribe(EventType.CANDLE, self._on_candle)

    async def _on_candle(self, event) -> None:
        candle = getattr(event, "data", None)
        if candle is None or self.bus is None:
            return
        if not isinstance(candle, Candle):
            candle = Candle(**dict(candle))
        if self.timeframe and candle.timeframe != self.timeframe:
            return
        if self.enabled_symbols and candle.symbol not in self.enabled_symbols:
            return

        bucket = self.history[candle.symbol]
        bucket.append(candle)
        if len(bucket) < self.min_history:
            return

        signal = self.generate_signal(candle.symbol, list(bucket))
        if signal is None:
            return
        if not isinstance(signal, Signal):
            signal = Signal(**dict(signal))
        await self.bus.publish(EventType.SIGNAL, signal, priority=60, source=self.name)

    @abstractmethod
    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal | None:
        ...


class TrendFollowingAgent(SignalAgent):
    name = "trend_following"

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal | None:
        features = compute_indicator_features(candles)
        if not features:
            return None
        ema_gap = float(features.get("ema_gap") or 0.0)
        rsi = float(features.get("rsi") or 50.0)
        last = candles[-1]
        if ema_gap > 0.001 and rsi >= 55.0:
            confidence = min(0.99, 0.55 + abs(ema_gap) * 10.0 + max(0.0, (rsi - 55.0) / 100.0))
            return Signal(
                symbol=symbol,
                side="buy",
                quantity=self.default_quantity,
                price=float(last.close),
                confidence=confidence,
                strategy_name=self.name,
                reason="Trend continuation above slow EMA",
                metadata={"features": features},
            )
        if ema_gap < -0.001 and rsi <= 45.0:
            confidence = min(0.99, 0.55 + abs(ema_gap) * 10.0 + max(0.0, (45.0 - rsi) / 100.0))
            return Signal(
                symbol=symbol,
                side="sell",
                quantity=self.default_quantity,
                price=float(last.close),
                confidence=confidence,
                strategy_name=self.name,
                reason="Downtrend continuation below slow EMA",
                metadata={"features": features},
            )
        return None


class MeanReversionAgent(SignalAgent):
    name = "mean_reversion"

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal | None:
        features = compute_indicator_features(candles)
        if not features:
            return None
        zscore = float(features.get("zscore") or 0.0)
        rsi = float(features.get("rsi") or 50.0)
        last = candles[-1]
        if zscore <= -1.4 or rsi <= 30.0:
            confidence = min(0.95, 0.55 + abs(min(zscore, -1.4)) / 3.0)
            return Signal(
                symbol=symbol,
                side="buy",
                quantity=self.default_quantity,
                price=float(last.close),
                confidence=confidence,
                strategy_name=self.name,
                reason="Oversold mean reversion setup",
                metadata={"features": features},
            )
        if zscore >= 1.4 or rsi >= 70.0:
            confidence = min(0.95, 0.55 + abs(max(zscore, 1.4)) / 3.0)
            return Signal(
                symbol=symbol,
                side="sell",
                quantity=self.default_quantity,
                price=float(last.close),
                confidence=confidence,
                strategy_name=self.name,
                reason="Overbought mean reversion setup",
                metadata={"features": features},
            )
        return None


class BreakoutAgent(SignalAgent):
    name = "breakout"

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal | None:
        features = compute_indicator_features(candles)
        if not features:
            return None
        breakout_up = float(features.get("breakout_up") or 0.0)
        breakout_down = float(features.get("breakout_down") or 0.0)
        volume_ratio = float(features.get("volume_ratio") or 1.0)
        last = candles[-1]
        if breakout_up >= 0.0 and volume_ratio >= 1.15:
            confidence = min(0.98, 0.6 + volume_ratio / 10.0)
            return Signal(
                symbol=symbol,
                side="buy",
                quantity=self.default_quantity,
                price=float(last.close),
                confidence=confidence,
                strategy_name=self.name,
                reason="Range breakout with volume confirmation",
                metadata={"features": features},
            )
        if breakout_down >= 0.0 and volume_ratio >= 1.15:
            confidence = min(0.98, 0.6 + volume_ratio / 10.0)
            return Signal(
                symbol=symbol,
                side="sell",
                quantity=self.default_quantity,
                price=float(last.close),
                confidence=confidence,
                strategy_name=self.name,
                reason="Breakdown with volume confirmation",
                metadata={"features": features},
            )
        return None


class MLAgent(SignalAgent):
    name = "ml_agent"

    def __init__(
        self,
        predictor,
        *,
        timeframe: str = "1m",
        lookback: int = 64,
        min_history: int = 25,
        default_quantity: float = 1.0,
        probability_threshold: float = 0.58,
        symbols: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            timeframe=timeframe,
            lookback=lookback,
            min_history=min_history,
            default_quantity=default_quantity,
            symbols=symbols,
        )
        self.predictor = predictor
        self.probability_threshold = max(0.0, min(1.0, float(probability_threshold)))

    def generate_signal(self, symbol: str, candles: list[Candle]) -> Signal | None:
        features = compute_indicator_features(candles)
        if not features:
            return None

        probability = float(self.predictor.predict_probability(features))
        if probability < self.probability_threshold:
            return None

        ema_gap = float(features.get("ema_gap") or 0.0)
        side = "buy" if ema_gap >= 0 else "sell"
        last = candles[-1]
        return Signal(
            symbol=symbol,
            side=side,
            quantity=self.default_quantity,
            price=float(last.close),
            confidence=min(0.99, probability),
            strategy_name=self.name,
            reason=f"ML probability {probability:.2f} cleared threshold",
            metadata={"features": features, "model_probability": probability},
        )

