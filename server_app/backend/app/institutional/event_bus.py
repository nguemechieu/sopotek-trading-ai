from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable

from .events import EventEnvelope, EventTopic


EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class AsyncEventBus(ABC):
    @abstractmethod
    async def publish(self, envelope: EventEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        raise NotImplementedError


class InMemoryEventBus(AsyncEventBus):
    def __init__(self) -> None:
        self._handlers: dict[EventTopic, list[EventHandler]] = defaultdict(list)
        self.messages: list[EventEnvelope] = []

    async def publish(self, envelope: EventEnvelope) -> None:
        self.messages.append(envelope)
        for handler in list(self._handlers.get(envelope.topic, [])):
            await handler(envelope)

    def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)
