import asyncio

from event_bus.event_bus import EventBus
from strategy.momentum_strategy import MomentumStrategy


def test_momentum_strategy_emits_order_after_enough_ticks():
    async def scenario():
        bus = EventBus()
        strategy = MomentumStrategy(bus)

        for price in range(100, 120):
            event = type("Event", (), {"data": {"symbol": "BTC/USDT", "price": float(price)}})()
            await strategy.on_tick(event)

        order_event = await bus.queue.get()
        assert order_event.data["symbol"] == "BTC/USDT"
        assert order_event.data["side"] in {"BUY", "SELL"}

    asyncio.run(scenario())
