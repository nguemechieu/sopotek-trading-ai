import numpy as np

from strategy.base_strategy import BaseStrategy
from event_bus.event_types import EventType


class MomentumStrategy(BaseStrategy):

    def __init__(self, event_bus):

        super().__init__(event_bus)

        self.prices = []

        self.bus.subscribe(EventType.MARKET_TICK, self.on_tick)

    async def on_tick(self, event):

        tick = event.data

        price = tick["price"]
        symbol = tick["symbol"]

        self.prices.append(price)

        if len(self.prices) < 20:
            return

        short_ma = np.mean(self.prices[-5:])
        long_ma = np.mean(self.prices[-20:])

        if short_ma > long_ma:

            await self.signal(symbol, "BUY", 0.01)

        elif short_ma < long_ma:

            await self.signal(symbol, "SELL", 0.01)
