from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import Candle, FeatureVector, OrderBookSnapshot
from sopotek.ml.features import compute_indicator_features


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        self.latest_order_book_features: dict[str, dict[str, float]] = {}
        self.latest_order_book_metadata: dict[str, dict[str, str | float]] = {}
        self.latest: dict[str, FeatureVector] = {}
        self.bus.subscribe(EventType.CANDLE, self._on_candle)
        self.bus.subscribe(EventType.ORDER_BOOK, self._on_order_book)

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
        await self._emit_feature_vector(candle.symbol, timestamp=candle.end, close=float(candle.close))

    async def _on_order_book(self, event) -> None:
        snapshot = getattr(event, "data", None)
        if snapshot is None:
            return
        if not isinstance(snapshot, OrderBookSnapshot):
            snapshot = OrderBookSnapshot(**dict(snapshot))
        features, metadata = self._extract_order_book_features(snapshot)
        if not features:
            return
        self.latest_order_book_features[snapshot.symbol] = features
        self.latest_order_book_metadata[snapshot.symbol] = metadata
        if len(self.history.get(snapshot.symbol, ())) < self.min_history:
            return
        latest_candle = self.history[snapshot.symbol][-1]
        await self._emit_feature_vector(snapshot.symbol, timestamp=snapshot.timestamp, close=float(latest_candle.close))

    async def _emit_feature_vector(self, symbol: str, *, timestamp, close: float | None) -> None:
        bucket = self.history[symbol]
        features = compute_indicator_features(list(bucket))
        if not features:
            return
        features.update(self.latest_order_book_features.get(symbol, {}))
        vector = FeatureVector(
            symbol=symbol,
            timeframe=bucket[-1].timeframe,
            values=features,
            close=close,
            metadata={
                "history_length": len(bucket),
                **dict(self.latest_order_book_metadata.get(symbol, {})),
            },
            timestamp=timestamp or _utc_now(),
        )
        self.latest[symbol] = vector
        await self.bus.publish(EventType.FEATURE_VECTOR, vector, priority=45, source="feature_engine")

    def _extract_order_book_features(self, snapshot: OrderBookSnapshot) -> tuple[dict[str, float], dict[str, str | float]]:
        bids = sorted([(float(price), float(size)) for price, size in list(snapshot.bids or []) if float(size) > 0.0], key=lambda item: item[0], reverse=True)[:5]
        asks = sorted([(float(price), float(size)) for price, size in list(snapshot.asks or []) if float(size) > 0.0], key=lambda item: item[0])[:5]
        if not bids or not asks:
            return {}, {}

        best_bid, best_bid_size = bids[0]
        best_ask, best_ask_size = asks[0]
        mid = (best_bid + best_ask) / 2.0 if (best_bid + best_ask) > 0 else 0.0
        bid_depth = sum(size for _, size in bids)
        ask_depth = sum(size for _, size in asks)
        total_depth = bid_depth + ask_depth
        imbalance = ((bid_depth - ask_depth) / total_depth) if total_depth > 0 else 0.0
        spread_bps = (((best_ask - best_bid) / mid) * 10000.0) if mid > 0 else 0.0
        max_bid_size = max(size for _, size in bids)
        max_ask_size = max(size for _, size in asks)
        wall_total = max_bid_size + max_ask_size
        wall_imbalance = ((max_bid_size - max_ask_size) / wall_total) if wall_total > 0 else 0.0
        average_top_size = (sum(size for _, size in bids + asks) / max(1, len(bids) + len(asks)))
        large_order_ratio = (max(max_bid_size, max_ask_size) / average_top_size) if average_top_size > 0 else 0.0
        dominant_side = "bid" if max_bid_size >= max_ask_size else "ask"
        return (
            {
                "order_book_imbalance": imbalance,
                "order_book_spread_bps": spread_bps,
                "bid_depth_top5": bid_depth,
                "ask_depth_top5": ask_depth,
                "liquidity_wall_imbalance": wall_imbalance,
                "large_order_ratio": large_order_ratio,
                "best_bid_size": best_bid_size,
                "best_ask_size": best_ask_size,
            },
            {
                "dominant_liquidity_side": dominant_side,
                "best_bid": best_bid,
                "best_ask": best_ask,
            },
        )

