import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from broker.ccxt_broker import CCXTBroker


class FakeSession:
    def __init__(self, connector=None):
        self.connector = connector
        self.closed = False

    async def close(self):
        self.closed = True


class FakeExchange:
    def __init__(self, cfg):
        self.cfg = cfg
        self.closed = False
        self.sandbox_mode = None
        self.has = {
            "fetchTicker": True,
            "fetchTickers": True,
            "fetchOrderBook": True,
            "fetchOHLCV": True,
            "fetchTrades": True,
            "fetchMyTrades": True,
            "fetchStatus": True,
            "fetchOrders": True,
            "fetchOpenOrders": True,
            "fetchClosedOrders": False,
            "fetchOrder": True,
            "fetchBalance": True,
            "cancelOrder": True,
            "cancelAllOrders": True,
            "createOrder": True,
            "withdraw": True,
            "fetchDepositAddress": True,
        }
        self.markets = {}
        self.currencies = {"USDT": {"code": "USDT"}}

    def set_sandbox_mode(self, enabled):
        self.sandbox_mode = enabled

    async def load_time_difference(self):
        return 123

    async def load_markets(self):
        self.markets = {
            "BTC/USDT": {"symbol": "BTC/USDT", "active": True},
            "ETH/USDT": {"symbol": "ETH/USDT", "active": True},
        }
        return self.markets

    async def fetch_ticker(self, symbol):
        return {"symbol": symbol, "last": 101.5}

    async def fetch_tickers(self, symbols=None):
        return {symbol: {"symbol": symbol, "last": index + 1} for index, symbol in enumerate(symbols or [])}

    async def fetch_order_book(self, symbol, limit=100):
        return {"symbol": symbol, "limit": limit, "bids": [[100, 1]], "asks": [[101, 2]]}

    async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        return [[1, 2, 3, 4, 5, 6] for _ in range(limit)]

    async def fetch_trades(self, symbol, limit=None):
        return [{"symbol": symbol, "limit": limit}]

    async def fetch_my_trades(self, symbol=None, limit=None):
        return [{"symbol": symbol, "limit": limit, "private": True}]

    async def fetch_status(self):
        return {"status": "ok"}

    async def create_order(self, symbol, order_type, side, amount, price, params):
        return {
            "id": "ord-1",
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": params,
        }

    async def cancel_order(self, order_id, symbol=None):
        return {"id": order_id, "symbol": symbol, "status": "canceled"}

    async def cancel_all_orders(self, symbol=None):
        return [{"symbol": symbol, "status": "canceled"}]

    async def fetch_balance(self):
        return {"free": {"USDT": 1000}}

    async def fetch_order(self, order_id, symbol=None):
        return {"id": order_id, "symbol": symbol}

    async def fetch_orders(self, symbol=None, limit=None):
        return [{"symbol": symbol, "limit": limit}]

    async def fetch_open_orders(self, symbol=None, limit=None):
        return [{"symbol": symbol, "limit": limit, "status": "open"}]

    async def withdraw(self, code, amount, address, tag=None, params=None):
        return {"code": code, "amount": amount, "address": address, "tag": tag, "params": params or {}}

    async def fetch_deposit_address(self, code, params=None):
        return {"code": code, "address": "abc", "params": params or {}}

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.4f}"

    def price_to_precision(self, symbol, price):
        return f"{price:.2f}"

    async def close(self):
        self.closed = True


class UnsupportedPrivateExchange(FakeExchange):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.has["fetchClosedOrders"] = False
        self.has["fetchDepositAddress"] = False


@pytest.fixture
def broker_module(monkeypatch):
    import broker.ccxt_broker as broker_mod

    monkeypatch.setattr(broker_mod.aiohttp, "TCPConnector", lambda family=None: {"family": family})
    monkeypatch.setattr(broker_mod.aiohttp, "ClientSession", lambda connector=None: FakeSession(connector=connector))
    monkeypatch.setattr(broker_mod.ccxt, "fakeexchange", FakeExchange, raising=False)
    monkeypatch.setattr(broker_mod.ccxt, "unsupportedexchange", UnsupportedPrivateExchange, raising=False)
    return broker_mod


def make_config(**overrides):
    base = {
        "exchange": "fakeexchange",
        "api_key": "key",
        "secret": "secret",
        "password": "passphrase",
        "uid": "uid-1",
        "mode": "paper",
        "sandbox": False,
        "timeout": 15000,
        "options": {"recvWindow": 9999},
        "params": {"clientOrderId": "abc-123"},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_ccxt_broker_connects_and_loads_symbols(broker_module):
    async def scenario():
        broker = CCXTBroker(make_config())

        await broker.connect()

        assert broker._connected is True
        assert broker.symbols == ["BTC/USDT", "ETH/USDT"]
        assert broker.exchange.sandbox_mode is True
        assert broker.exchange.cfg["password"] == "passphrase"
        assert broker.exchange.cfg["uid"] == "uid-1"
        assert broker.exchange.cfg["options"]["recvWindow"] == 9999

        await broker.close()

    asyncio.run(scenario())


def test_ccxt_broker_exposes_common_market_and_account_methods(broker_module):
    async def scenario():
        broker = CCXTBroker(make_config())

        assert await broker.fetch_symbols() == ["BTC/USDT", "ETH/USDT"]
        assert (await broker.fetch_ticker("BTC/USDT"))["symbol"] == "BTC/USDT"
        assert "BTC/USDT" in await broker.fetch_tickers(["BTC/USDT"])
        assert (await broker.fetch_orderbook("BTC/USDT"))["bids"]
        assert len(await broker.fetch_ohlcv("BTC/USDT", limit=3)) == 3
        assert (await broker.fetch_balance())["free"]["USDT"] == 1000
        assert (await broker.fetch_status())["status"] == "ok"
        assert (await broker.fetch_orders("BTC/USDT", limit=10))[0]["limit"] == 10
        assert (await broker.fetch_open_orders("BTC/USDT", limit=5))[0]["status"] == "open"
        assert await broker.fetch_closed_orders("BTC/USDT", limit=5) == []

        await broker.close()

    asyncio.run(scenario())


def test_ccxt_broker_normalizes_order_precision_and_params(broker_module):
    async def scenario():
        broker = CCXTBroker(make_config())

        order = await broker.create_order(
            symbol="BTC/USDT",
            side="BUY",
            amount=1.234567,
            type="limit",
            price=101.987,
            params={"timeInForce": "GTC"},
        )

        assert order["side"] == "buy"
        assert order["amount"] == 1.2346
        assert order["price"] == 101.99
        assert order["params"]["clientOrderId"] == "abc-123"
        assert order["params"]["timeInForce"] == "GTC"

        await broker.close()

    asyncio.run(scenario())


def test_ccxt_broker_returns_safe_defaults_for_unsupported_optional_methods(broker_module):
    async def scenario():
        broker = CCXTBroker(make_config(exchange="unsupportedexchange"))

        assert await broker.fetch_closed_orders("BTC/USDT") == []

        with pytest.raises(NotImplementedError):
            await broker.fetch_deposit_address("USDT")

        await broker.close()

    asyncio.run(scenario())
