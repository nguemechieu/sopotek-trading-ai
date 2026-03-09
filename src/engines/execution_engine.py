from event_bus.event_types import EventType


class ExecutionEngine:

    def __init__(self, broker, bus):
        self.broker = broker
        self.bus = bus

        self.bus.subscribe(EventType.ORDER, self.execute)

    async def execute(self, event):
        order = event.data

        await self.broker.create_order(
            symbol=order["symbol"],
            side=order["side"],
            amount=order["amount"],
            type=order["type"],
            price=order["price"],
            stop_loss=order["stop_loss"],
            take_profit=order["take_profit"],
            slippage=order["slippage"]
        )
