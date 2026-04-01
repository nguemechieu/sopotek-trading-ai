from __future__ import annotations

from collections import defaultdict, deque

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import Candle, FeatureVector
from sopotek.ml.features import compute_indicator_features


class FeatureEngine:
    """Computes live features from the rolling candle stream."""

    def __init__(
        self,
        event_bus: AsyncEventBus,
        *,
        timeframe: str = "1m",
        max_history: int = 256,
        min_history: int = 25,
    ) -> None:
        self.bus = event_bus
        self.timeframe = timeframe
        self.max_history = max(32, int(max_history))
        self.min_history = max(10, int(min_history))
        self.history: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=self.max_history))
        self.latest: dict[str, FeatureVector] = {}
        self.bus.subscribe(EventType.CANDLE, self._on_candle)

    async def _on_candle(self, event) -> None:
        candle = getattr(event, "data", None)
        if candle is None:
            return
        if not isinstance(candle, Candle):
            candle = Candle(**dict(candle))
        if self.timeframe and candle.timeframe != self.timeframe:
            return

        bucket = self.history[candle.symbol]
        bucket.append(candle)
        if len(bucket) < self.min_history:
            return

        features = compute_indicator_features(list(bucket))
        if not features:
            return
        vector = FeatureVector(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            values=features,
            close=float(candle.close),
            metadata={"history_length": len(bucket)},
            timestamp=candle.end,
        )
        self.latest[candle.symbol] = vector
        await self.bus.publish(EventType.FEATURE_VECTOR, vector, priority=45, source="feature_engine")

