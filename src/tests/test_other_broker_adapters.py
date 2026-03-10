import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import broker.paper_broker as paper_module
from broker.alpaca_broker import AlpacaBroker
from broker.oanda_broker import OandaBroker
from broker.paper_broker import PaperBroker
from market_data.ticker_buffer import TickerBuffer


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self.payload


class FakeOandaSession:
    def __init__(self):
        self.closed = False

    def request(self, method, url, headers=None, params=None, json=None):
        if url.endswith("/pricing"):
            return FakeResponse(
                {
                    "prices": [
                        {
                            "instrument": "EUR_USD",
                            "bids": [{"price": "1.1000", "liquidity": 100000}],
                            "asks": [{"price": "1.1002", "liquidity": 100000}],
                        }
                    ]
                }
            )
        if "/candles" in url:
            return FakeResponse(
                {
                    "candles": [
                        {"complete": True, "time": "t1", "mid": {"o": "1.0", "h": "2.0", "l": "0.5", "c": "1.5"}, "volume": 10},
                        {"complete": True, "time": "t2", "mid": {"o": "1.5", "h": "2.5", "l": "1.0", "c": "2.0"}, "volume": 12},
                    ]
                }
            )
        if url.endswith("/summary"):
            return FakeResponse({"account": {"currency": "USD", "balance": "1000", "NAV": "1100", "marginUsed": "100"}})
        if url.endswith("/instruments"):
            return FakeResponse({"instruments": [{"name": "EUR_USD"}, {"name": "GBP_USD"}]})
        if url.endswith("/orders") and method == "GET":
            return FakeResponse({"orders": [{"id": "1", "instrument": "EUR_USD", "state": "PENDING"}]})
        if url.endswith("/orders") and method == "POST":
            return FakeResponse({"orderCreateTransaction": {"id": "2"}})
        if url.endswith("/openPositions"):
            return FakeResponse(
                {
                    "positions": [
                        {"instrument": "EUR_USD", "long": {"units": "3", "averagePrice": "1.2"}, "short": {"units": "0"}}
                    ]
                }
            )
        if "/cancel" in url:
            return FakeResponse({"orderCancelTransaction": {"id": "1"}})
        if "/orders/" in url:
            return FakeResponse({"order": {"id": "1", "instrument": "EUR_USD"}})
        if url.endswith("/trades"):
            return FakeResponse({"trades": [{"instrument": "EUR_USD"}]})
        raise AssertionError(f"Unhandled Oanda URL: {method} {url}")

    async def close(self):
        self.closed = True


class FakeAlpacaREST:
    def __init__(self, api_key, secret, base_url, api_version="v2"):
        self.api_key = api_key
        self.secret = secret
        self.base_url = base_url

    def get_account(self):
        return SimpleNamespace(status="ACTIVE", cash="5000", equity="5200", buying_power="7000")

    def get_latest_trade(self, symbol):
        return SimpleNamespace(price=201.5)

    def get_latest_quote(self, symbol):
        return SimpleNamespace(bid_price=201.0, ask_price=202.0)

    def get_bars(self, symbol, timeframe, limit=100):
        return [
            SimpleNamespace(t="t1", o=1.0, h=2.0, l=0.5, c=1.5, v=10),
            SimpleNamespace(t="t2", o=1.5, h=2.5, l=1.0, c=2.0, v=11),
        ]

    def list_assets(self, status="active"):
        return [SimpleNamespace(symbol="AAPL", tradable=True), SimpleNamespace(symbol="TSLA", tradable=True)]

    def submit_order(self, **kwargs):
        return SimpleNamespace(
            id="alp-1",
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            type=kwargs["type"],
            status="accepted",
            qty=str(kwargs["qty"]),
            filled_qty="0",
            limit_price=str(kwargs.get("limit_price", 0)),
            filled_avg_price="0",
        )

    def cancel_order(self, order_id):
        return {"id": order_id, "status": "canceled"}

    def cancel_all_orders(self):
        return [{"status": "canceled"}]

    def get_order(self, order_id):
        return SimpleNamespace(id=order_id, symbol="AAPL", side="buy", type="market", status="filled", qty="2", filled_qty="2", filled_avg_price="200")

    def list_orders(self, status="all", limit=None):
        orders = [
            SimpleNamespace(id="1", symbol="AAPL", side="buy", type="market", status="new", qty="2", filled_qty="0", filled_avg_price="0"),
            SimpleNamespace(id="2", symbol="TSLA", side="sell", type="limit", status="filled", qty="1", filled_qty="1", limit_price="300", filled_avg_price="300"),
        ]
        return orders[:limit] if limit else orders

    def list_positions(self):
        return [SimpleNamespace(symbol="AAPL", qty="2", avg_entry_price="199", market_value="402")]

    def close(self):
        return None


def test_oanda_broker_normalizes_common_methods(monkeypatch):
    import broker.oanda_broker as oanda_module

    monkeypatch.setattr(oanda_module.aiohttp, "ClientSession", FakeOandaSession)

    async def scenario():
        broker = OandaBroker(SimpleNamespace(api_key="token", account_id="acct-1", mode="practice"))
        assert (await broker.fetch_ticker("EUR/USD"))["ask"] == 1.1002
        assert (await broker.fetch_orderbook("EUR/USD"))["bids"][0][0] == 1.1
        assert len(await broker.fetch_ohlcv("EUR/USD", timeframe="1h", limit=2)) == 2
        assert (await broker.fetch_balance())["equity"] == 1100.0
        assert await broker.fetch_symbols() == ["EUR_USD", "GBP_USD"]
        assert (await broker.fetch_positions())[0]["symbol"] == "EUR_USD"
        assert len(await broker.fetch_open_orders("EUR/USD")) == 1
        assert len(await broker.fetch_closed_orders("EUR/USD")) == 0
        await broker.close()

    asyncio.run(scenario())


def test_alpaca_broker_normalizes_common_methods(monkeypatch):
    import broker.alpaca_broker as alpaca_module

    monkeypatch.setattr(alpaca_module, "tradeapi", SimpleNamespace(REST=FakeAlpacaREST))

    async def scenario():
        broker = AlpacaBroker(SimpleNamespace(api_key="key", secret="secret", mode="paper", sandbox=False))
        assert (await broker.fetch_ticker("AAPL"))["bid"] == 201.0
        assert (await broker.fetch_orderbook("AAPL"))["asks"][0][0] == 202.0
        assert len(await broker.fetch_ohlcv("AAPL", timeframe="1h", limit=2)) == 2
        assert "AAPL" in await broker.fetch_symbols()
        assert (await broker.fetch_balance())["cash"] == 5000.0
        assert (await broker.fetch_positions())[0]["symbol"] == "AAPL"
        order = await broker.create_order("AAPL", "buy", 2, type="limit", price=200)
        assert order["symbol"] == "AAPL"
        assert len(await broker.fetch_closed_orders(limit=5)) == 1
        await broker.close()

    asyncio.run(scenario())


def test_paper_broker_exposes_normalized_api(monkeypatch):
    class DummyController:
        def __init__(self):
            self.logger = None
            self.paper_balance = 1000.0
            self.symbols = ["BTC/USDT"]
            self.candle_buffers = {}
            self.ticker_buffer = TickerBuffer()
            self.ticker_stream = SimpleNamespace(get=lambda symbol: None)
            self.time_frame = "1h"
            self.broker = None

            self.ticker_buffer.update(
                "BTC/USDT",
                {"symbol": "BTC/USDT", "price": 100.0, "bid": 99.9, "ask": 100.1},
            )

    async def fake_market_data_broker(self, symbol=None):
        return None

    monkeypatch.setattr(PaperBroker, "_ensure_market_data_broker", fake_market_data_broker)

    async def scenario():
        controller = DummyController()
        broker = PaperBroker(controller)
        controller.broker = broker
        await broker.connect()
        ticker = await broker.fetch_ticker("BTC/USDT")
        assert ticker["last"] == 100.0
        orderbook = await broker.fetch_orderbook("BTC/USDT")
        assert orderbook["bids"][0][0] == 100.0
        order = await broker.create_order("BTC/USDT", "buy", 1, type="market")
        assert order["status"] == "filled"
        assert (await broker.fetch_balance())["free"]["USDT"] == 900.0
        assert (await broker.fetch_positions())[0]["symbol"] == "BTC/USDT"
        await broker.close()

    asyncio.run(scenario())


def test_paper_broker_bootstraps_public_market_data(monkeypatch):
    class FakeMarketDataBroker:
        def __init__(self, config):
            self.config = config
            self.closed = False

        async def connect(self):
            return True

        async def close(self):
            self.closed = True

        async def fetch_ticker(self, symbol):
            return {"symbol": symbol, "last": 123.4, "bid": 123.3, "ask": 123.5}

        async def fetch_orderbook(self, symbol, limit=50):
            return {"symbol": symbol, "bids": [[123.3, 5.0]], "asks": [[123.5, 4.0]]}

        async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
            return [["t1", 120.0, 125.0, 119.0, 123.4, 42.0]]

        async def fetch_symbols(self):
            return ["BTC/USDT", "ETH/USDT"]

    class DummyController:
        def __init__(self):
            self.logger = None
            self.paper_balance = 1000.0
            self.symbols = ["BTC/USDT"]
            self.candle_buffers = {}
            self.ticker_buffer = TickerBuffer()
            self.ticker_stream = SimpleNamespace(get=lambda symbol: None, update=lambda symbol, ticker: None)
            self.time_frame = "1h"
            self.broker = None
            self.config = SimpleNamespace(
                broker=SimpleNamespace(params={"paper_data_exchange": "binanceus"})
            )

    monkeypatch.setattr(paper_module, "CCXTBroker", FakeMarketDataBroker)

    async def scenario():
        controller = DummyController()
        broker = PaperBroker(controller)
        controller.broker = broker
        market_data_config = broker._build_market_data_config()
        assert market_data_config.mode == "live"
        assert market_data_config.sandbox is False
        await broker.connect()

        ticker = await broker.fetch_ticker("BTC/USDT")
        assert ticker["last"] == 123.4
        assert controller.ticker_buffer.latest("BTC/USDT")["last"] == 123.4

        orderbook = await broker.fetch_orderbook("BTC/USDT")
        assert orderbook["asks"][0][0] == 123.5

        candles = await broker.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=1)
        assert candles[0][4] == 123.4

        symbols = await broker.fetch_symbols()
        assert "ETH/USDT" in symbols

        await broker.close()
        assert broker.market_data_broker is None

    asyncio.run(scenario())
