from event_bus.event import Event
from event_bus.event_types import EventType


class MarketDataEngine:

    def __init__(self, broker, event_bus):
        self.broker = broker
        self.bus = event_bus

    async def stream(self):
        while True:
            tick = await self.broker.fetch_ticker("BTC/USDT")

            event = Event(
                EventType.MARKET_TICK,
                tick
            )

            await self.bus.publish(event)
