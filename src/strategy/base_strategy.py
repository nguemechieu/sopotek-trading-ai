from event_bus.event import Event
from event_bus.event_types import EventType


class BaseStrategy:

    def __init__(self, event_bus):
        self.bus = event_bus

    # ===============================
    # EMIT SIGNAL
    # ===============================

    async def signal(self, symbol, side, amount):
        order = {
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "type": "market"
        }

        event = Event(EventType.ORDER, order)

        await self.bus.publish(event)
