import asyncio

from event_bus.event_types import EventType


class ExecutionManager:

    def __init__(self, broker, event_bus, router):

        self.broker = broker
        self.bus = event_bus
        self.router = router

        self.running = False

        # Subscribe to ORDER events
        self.bus.subscribe(EventType.ORDER, self.on_order)

    async def start(self):

        self.running = True

    async def stop(self):

        self.running = False

    async def on_order(self, event):

        if not self.running:
            return

        order = event.data

        try:

            execution = await self.router.route(order)

            if execution:
                fill_event = {
                    "symbol": order["symbol"],
                    "side": order["side"],
                    "qty": order["amount"],
                    "price": execution.get("price")
                }

                await self.bus.publish({
                    "type": EventType.FILL,
                    "data": fill_event
                })

        except Exception as e:

            print("Execution error:", e)
