from __future__ import annotations

from event_bus.event_bus import EventBus
from sopotek.core.event_bus import AsyncEventBus, InMemoryEventStore


def build_event_bus(*, async_mode: bool = False, persistent: bool = False):
    """Create a sync or async event bus backed by the existing platform primitives."""

    if async_mode:
        store = InMemoryEventStore() if persistent else None
        return AsyncEventBus(store=store, enable_persistence=bool(store is not None))
    return EventBus()


__all__ = ["AsyncEventBus", "EventBus", "build_event_bus"]
