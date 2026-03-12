import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from broker.ccxt_broker import CCXTBroker
from event_bus.event_bus import EventBus
from market_data.websocket.coinbase_web_socket import CoinbaseWebSocket


class FakeSession:
    def __init__(self, connector=None):
        self.connector = connector
        self.closed = False

    async def close(self):
        self.closed = True


class FakeCoinbaseExchange:
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
            "fetchClosedOrders": True,
            "fetchOrder": True,
            "fetchBalance": True,
            "cancelOrder": True,
            "cancelAllOrders": True,
            "createOrder": True,
        }
        self.markets = {}
        self.currencies = {"USD": {"code": "USD"}}

    def set_sandbox_mode(self, enabled):
        self.sandbox_mode = enabled

    async def load_time_difference(self):
        return 0

    async def load_markets(self):
        self.markets = {
            "BTC/USD": {"symbol": "BTC/USD", "active": True},
            "ETH/USD": {"symbol": "ETH/USD", "active": True},
        }
        return self.markets

    async def fetch_ticker(self, symbol):
        return {"symbol": symbol, "last": 65000.0, "bid": 64999.0, "ask": 65001.0}

    async def fetch_tickers(self, symbols=None):
        return {symbol: {"symbol": symbol, "last": 1 + idx} for idx, symbol in enumerate(symbols or [])}

    async def fetch_order_book(self, symbol, limit=100):
        return {"symbol": symbol, "bids": [[64999.0, 1.0]], "asks": [[65001.0, 1.5]], "limit": limit}

    async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        return [[1710000000000 + i, 1, 2, 0.5, 1.5, 10] for i in range(limit)]

    async def fetch_trades(self, symbol, limit=None):
        return [{"symbol": symbol, "limit": limit}]

    async def fetch_my_trades(self, symbol=None, limit=None):
        return [{"symbol": symbol, "limit": limit, "private": True}]

    async def fetch_status(self):
        return {"status": "ok"}

    async def create_order(self, symbol, order_type, side, amount, price, params):
        return {
            "id": "cb-1",
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "open",
            "params": params,
        }

    async def cancel_order(self, order_id, symbol=None):
        return {"id": order_id, "symbol": symbol, "status": "canceled"}

    async def cancel_all_orders(self, symbol=None):
        return [{"symbol": symbol, "status": "canceled"}]

    async def fetch_balance(self):
        return {"free": {"USD": 500.0, "BTC": 0.25}}

    async def fetch_order(self, order_id, symbol=None):
        return {"id": order_id, "symbol": symbol, "status": "filled", "filled": 0.01, "price": 65000.0}

    async def fetch_orders(self, symbol=None, limit=None):
        return [{"id": "cb-1", "symbol": symbol, "limit": limit}]

    async def fetch_open_orders(self, symbol=None, limit=None):
        return [{"id": "cb-1", "symbol": symbol, "limit": limit, "status": "open"}]

    async def fetch_closed_orders(self, symbol=None, limit=None):
        return [{"id": "cb-2", "symbol": symbol, "limit": limit, "status": "closed"}]

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.8f}"

    def price_to_precision(self, symbol, price):
        return f"{price:.2f}"

    async def close(self):
        self.closed = True


class FakeSocket:
    def __init__(self, messages):
        self._messages = list(messages)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, payload):
        self.sent = payload

    async def recv(self):
        if not self._messages:
            raise asyncio.CancelledError()
        return self._messages.pop(0)


def test_coinbase_ccxt_broker_supports_market_data_and_order_methods(monkeypatch):
    import broker.ccxt_broker as broker_mod

    monkeypatch.setattr(
        broker_mod.aiohttp,
        "TCPConnector",
        lambda family=None, resolver=None, ttl_dns_cache=None: {
            "family": family,
            "resolver": resolver,
            "ttl_dns_cache": ttl_dns_cache,
        },
    )
    monkeypatch.setattr(broker_mod.aiohttp, "ThreadedResolver", lambda: "threaded-resolver")
    monkeypatch.setattr(broker_mod.aiohttp, "ClientSession", lambda connector=None, **kwargs: FakeSession(connector=connector, **kwargs))
    monkeypatch.setattr(broker_mod.ccxt, "coinbase", FakeCoinbaseExchange, raising=False)

    async def scenario():
        config = SimpleNamespace(
            exchange="coinbase",
            api_key="key",
            secret="secret",
            password="passphrase",
            uid=None,
            mode="live",
            sandbox=False,
            timeout=15000,
            options={},
            params={"clientOrderId": "coinbase-client"},
        )
        broker = CCXTBroker(config)

        await broker.connect()

        assert broker.session.connector["resolver"] == "threaded-resolver"
        assert "BTC/USD" in await broker.fetch_symbols()
        assert (await broker.fetch_ticker("BTC/USD"))["bid"] == 64999.0
        assert len(await broker.fetch_ohlcv("BTC/USD", limit=3)) == 3
        assert (await broker.fetch_orderbook("BTC/USD"))["asks"][0][0] == 65001.0
        assert (await broker.fetch_balance())["free"]["USD"] == 500.0
        assert (await broker.fetch_open_orders("BTC/USD", limit=5))[0]["status"] == "open"

        order = await broker.create_order(
            symbol="BTC/USD",
            side="buy",
            amount=0.010000123,
            type="limit",
            price=65000.129,
            params={"timeInForce": "GTC"},
        )
        assert order["amount"] == 0.01000012
        assert order["price"] == 65000.13
        assert order["params"]["clientOrderId"] == "coinbase-client"
        assert order["params"]["timeInForce"] == "GTC"

        stop_limit_order = await broker.create_order(
            symbol="BTC/USD",
            side="buy",
            amount=0.01,
            type="stop_limit",
            price=64950.12,
            stop_price=65010.0,
        )
        assert stop_limit_order["type"] == "stop_limit"
        assert stop_limit_order["stop_price"] == 65010.0
        assert stop_limit_order["params"]["stopPrice"] == 65010.0

        await broker.close()

    asyncio.run(scenario())


def test_coinbase_ccxt_broker_normalizes_private_key_newlines(monkeypatch):
    import broker.ccxt_broker as broker_mod

    monkeypatch.setattr(
        broker_mod.aiohttp,
        "TCPConnector",
        lambda family=None, resolver=None, ttl_dns_cache=None: {
            "family": family,
            "resolver": resolver,
            "ttl_dns_cache": ttl_dns_cache,
        },
    )
    monkeypatch.setattr(broker_mod.aiohttp, "ThreadedResolver", lambda: "threaded-resolver")
    monkeypatch.setattr(broker_mod.aiohttp, "ClientSession", lambda connector=None, **kwargs: FakeSession(connector=connector, **kwargs))
    monkeypatch.setattr(broker_mod.ccxt, "coinbase", FakeCoinbaseExchange, raising=False)

    async def scenario():
        config = SimpleNamespace(
            exchange="coinbase",
            api_key="organizations/test/apiKeys/key-1",
            secret="-----BEGIN EC PRIVATE KEY-----\\nline-1\\nline-2\\n-----END EC PRIVATE KEY-----\\n",
            password=None,
            uid=None,
            mode="live",
            sandbox=False,
            timeout=15000,
            options={},
            params={},
        )
        broker = CCXTBroker(config)

        await broker.connect()

        assert broker.secret == "-----BEGIN EC PRIVATE KEY-----\nline-1\nline-2\n-----END EC PRIVATE KEY-----\n"
        assert broker.exchange.cfg["secret"] == broker.secret

        await broker.close()

    asyncio.run(scenario())


def test_coinbase_websocket_normalizes_product_ids_to_app_symbols(monkeypatch):
    import market_data.websocket.coinbase_web_socket as ws_mod

    payload = json.dumps(
        {
            "type": "ticker",
            "product_id": "BTC-USD",
            "price": "65000.10",
            "best_bid": "64999.50",
            "best_ask": "65000.50",
            "volume_24h": "120.5",
            "time": "2026-03-10T10:00:00Z",
        }
    )
    monkeypatch.setattr(ws_mod.websockets, "connect", lambda url: FakeSocket([payload]))

    async def scenario():
        bus = EventBus()
        client = CoinbaseWebSocket(symbols=["BTC-USD"], event_bus=bus)

        try:
            await client.connect()
        except asyncio.CancelledError:
            pass

        event = await bus.queue.get()
        assert event.data["symbol"] == "BTC/USD"
        assert event.data["bid"] == 64999.5
        assert event.data["ask"] == 65000.5

    asyncio.run(scenario())
