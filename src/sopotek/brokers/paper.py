from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sopotek.broker.base import BaseBroker
from sopotek.core.models import OrderIntent


class PaperBroker(BaseBroker):
    """Deterministic paper broker with slippage, latency, and partial fills."""

    def __init__(
        self,
        *,
        seed: int = 7,
        slippage_bps: float = 3.0,
        partial_fill_probability: float = 0.25,
        min_fill_ratio: float = 0.55,
        min_latency_ms: float = 0.0,
        max_latency_ms: float = 0.0,
        fee_bps: float = 1.0,
    ) -> None:
        self.random = random.Random(seed)
        self.slippage_bps = max(0.0, float(slippage_bps))
        self.partial_fill_probability = max(0.0, min(1.0, float(partial_fill_probability)))
        self.min_fill_ratio = max(0.05, min(1.0, float(min_fill_ratio)))
        self.min_latency_ms = max(0.0, float(min_latency_ms))
        self.max_latency_ms = max(self.min_latency_ms, float(max_latency_ms))
        self.fee_bps = max(0.0, float(fee_bps))
        self.latest_prices: dict[str, float] = {}
        self.order_log: list[dict[str, float | str | bool]] = []

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        return []

    def update_market_price(self, symbol: str, price: float, *, timestamp: datetime | None = None) -> None:
        del timestamp
        self.latest_prices[str(symbol)] = float(price)

    async def place_order(self, order: OrderIntent):
        reference_price = float(order.price or self.latest_prices.get(order.symbol) or 0.0)
        if reference_price <= 0:
            raise ValueError(f"No reference price available for {order.symbol}")

        latency_ms = self.random.uniform(self.min_latency_ms, self.max_latency_ms)
        if latency_ms > 0:
            await asyncio.sleep(latency_ms / 1000.0)

        slippage = self.slippage_bps * (0.5 + self.random.random())
        side = str(order.side).lower()
        signed_slippage = slippage if side == "buy" else -slippage
        fill_price = reference_price * (1.0 + signed_slippage / 10000.0)

        partial = self.random.random() < self.partial_fill_probability
        if partial:
            fill_ratio = self.min_fill_ratio + ((1.0 - self.min_fill_ratio) * self.random.random())
            filled_quantity = float(order.quantity) * fill_ratio
        else:
            filled_quantity = float(order.quantity)
        remaining_quantity = max(0.0, float(order.quantity) - filled_quantity)
        fee = filled_quantity * fill_price * (self.fee_bps / 10000.0)
        status = "partially_filled" if remaining_quantity > 1e-12 else "filled"
        payload = {
            "id": f"paper-{len(self.order_log) + 1}",
            "status": status,
            "price": reference_price,
            "fill_price": fill_price,
            "filled_quantity": filled_quantity,
            "remaining_quantity": remaining_quantity,
            "partial": remaining_quantity > 1e-12,
            "latency_ms": latency_ms,
            "slippage_bps": abs(signed_slippage),
            "fee": fee,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.order_log.append(payload)
        return payload

    async def stream_ticks(self, symbol: str) -> AsyncIterator[dict]:
        if False:
            yield {"symbol": symbol}

