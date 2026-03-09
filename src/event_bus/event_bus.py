import asyncio
from collections import defaultdict


class EventBus:

    def __init__(self):

        self.queue = asyncio.Queue()

        self.subscribers = defaultdict(list)

    async def publish(self, event):

        await self.queue.put(event)

    def subscribe(self, event_type, handler):

        self.subscribers[event_type].append(handler)

    async def start(self):

        while True:

            event = await self.queue.get()

            handlers = self.subscribers.get(event.type, [])

            for handler in handlers:
                asyncio.create_task(handler(event))
