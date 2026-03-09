from strategy.base_strategy import BaseStrategy
from event_bus.event_types import EventType


class ArbitrageStrategy(BaseStrategy):

    def __init__(self, event_bus):

        super().__init__(event_bus)

        self.prices = {}

        self.bus.subscribe(EventType.MARKET_TICK, self.on_tick)

    async def on_tick(self, event):

        tick = event.data

        exchange = tick["exchange"]
        symbol = tick["symbol"]
        price = tick["price"]

        if symbol not in self.prices:
            self.prices[symbol] = {}

        self.prices[symbol][exchange] = price

        exchanges = list(self.prices[symbol].keys())

        if len(exchanges) < 2:
            return

        p1 = self.prices[symbol][exchanges[0]]
        p2 = self.prices[symbol][exchanges[1]]

        spread = abs(p1 - p2) / min(p1, p2)

        if spread > 0.01:

            if p1 < p2:

                await self.signal(symbol, "BUY", 0.01)

            else:

                await self.signal(symbol, "SELL", 0.01)
