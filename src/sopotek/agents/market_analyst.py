from __future__ import annotations

from collections import defaultdict, deque

from sopotek.agents.base import BaseAgent
from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import AnalystInsight, Candle
from sopotek.ml.regime_engine import RegimeEngine


class MarketAnalystAgent(BaseAgent):
    name = "market_analyst"

    def __init__(self, *, timeframe: str = "1m", lookback: int = 96, regime_engine: RegimeEngine | None = None) -> None:
        self.bus: AsyncEventBus | None = None
        self.latest_insights: dict[str, AnalystInsight] = {}
        self.timeframe = timeframe
        self.lookback = max(24, int(lookback))
        self.history: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=self.lookback))
        self.regime_engine = regime_engine or RegimeEngine()

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
        bucket = self.history[candle.symbol]
        bucket.append(candle)
        snapshot = self.regime_engine.classify_candles(list(bucket))
        if len(bucket) == 1 and snapshot.regime == "neutral":
            opening_price = float(candle.open or 0.0)
            closing_price = float(candle.close or 0.0)
            if closing_price > opening_price:
                snapshot.regime = "bullish"
                snapshot.preferred_strategy = "trend_following"
            elif closing_price < opening_price:
                snapshot.regime = "bearish"
                snapshot.preferred_strategy = "mean_reversion"
        regime = snapshot.regime
        preferred_strategy = snapshot.preferred_strategy or (
            "trend_following" if regime == "bullish" else "mean_reversion" if regime == "neutral" else "ml_agent"
        )
        insight = AnalystInsight(
            symbol=candle.symbol,
            regime=regime,
            momentum=snapshot.momentum,
            volatility=1.0 + float(snapshot.atr_pct or 0.0),
            preferred_strategy=preferred_strategy,
            metadata={
                "timeframe": candle.timeframe,
                "trend_strength": snapshot.trend_strength,
                "volatility_regime": snapshot.volatility_regime,
                "cluster_id": snapshot.cluster_id,
                **dict(snapshot.metadata),
            },
        )
        self.latest_insights[candle.symbol] = insight
        await self.bus.publish(EventType.REGIME, snapshot, priority=48, source=self.name)
        await self.bus.publish(EventType.REGIME_UPDATES, snapshot, priority=48, source=self.name)
        await self.bus.publish(EventType.ANALYST_INSIGHT, insight, priority=50, source=self.name)
