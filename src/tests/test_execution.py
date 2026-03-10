import asyncio

from event_bus.event_bus import EventBus
from event_bus.event_types import EventType
from execution.execution_manager import ExecutionManager
from execution.order_router import OrderRouter


class MockBroker:
    def __init__(self, balance=None, markets=None):
        self.orders = []
        self._balance = balance if balance is not None else {}

        exchange = type("Exchange", (), {})()
        exchange.markets = markets or {}
        exchange.amount_to_precision = lambda symbol, amount: amount
        self.exchange = exchange

    async def create_order(self, symbol, side, amount, type="market", price=None):
        order = {
            "id": "order-1",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "type": type,
            "price": price,
            "status": "filled",
        }
        self.orders.append(order)
        return order

    async def fetch_balance(self):
        return self._balance

    async def fetch_ticker(self, symbol):
        return {"symbol": symbol, "price": 100.0, "bid": 100.0, "ask": 100.0}


def test_execute_accepts_keyword_order_arguments():
    broker = MockBroker(balance={"free": {"USDT": 1000}})
    bus = EventBus()
    manager = ExecutionManager(broker, bus, OrderRouter(broker))

    order = asyncio.run(
        manager.execute(symbol="BTC/USDT", side="buy", amount=0.01, price=42000)
    )

    assert order["symbol"] == "BTC/USDT"
    assert order["side"] == "buy"
    assert order["amount"] == 0.01

    fill_event = asyncio.run(bus.queue.get())
    assert fill_event.type == EventType.FILL
    assert fill_event.data["symbol"] == "BTC/USDT"
    assert fill_event.data["qty"] == 0.01


def test_execute_accepts_legacy_signal_payload():
    broker = MockBroker(balance={"free": {"ETH": 5}})
    bus = EventBus()
    manager = ExecutionManager(broker, bus, OrderRouter(broker))

    order = asyncio.run(manager.execute({"symbol": "ETH/USDT", "signal": "SELL", "size": 2}))

    assert order["symbol"] == "ETH/USDT"
    assert order["side"] == "sell"
    assert order["amount"] == 2


def test_execute_scales_buy_order_to_available_quote_balance():
    broker = MockBroker(
        balance={"free": {"USDT": 250}},
        markets={"BTC/USDT": {"active": True, "limits": {"cost": {"min": 10}}}},
    )
    bus = EventBus()
    manager = ExecutionManager(broker, bus, OrderRouter(broker))

    order = asyncio.run(
        manager.execute(symbol="BTC/USDT", side="buy", amount=5, price=100)
    )

    assert order["amount"] == 2.45


def test_execute_skips_inactive_market():
    broker = MockBroker(
        balance={"free": {"USDT": 1000}},
        markets={"MKR/USDT": {"active": False}},
    )
    bus = EventBus()
    manager = ExecutionManager(broker, bus, OrderRouter(broker))

    order = asyncio.run(
        manager.execute(symbol="MKR/USDT", side="buy", amount=1, price=100)
    )

    assert order is None
    assert broker.orders == []
