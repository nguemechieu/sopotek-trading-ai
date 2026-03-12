import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.app_controller import AppController


def _make_controller():
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.market_chat")
    controller.symbols = ["BTC/USDT", "ETH/USDT"]
    controller.time_frame = "1h"
    controller.terminal = None
    controller.broker = None

    async def fake_ticker(symbol):
        return {
            "symbol": symbol,
            "price": 105.0,
            "last": 105.0,
            "bid": 104.9,
            "ask": 105.1,
        }

    async def fake_ohlcv(symbol, timeframe="1h", limit=120):
        controller._last_requested_symbol = symbol
        controller._last_requested_timeframe = timeframe
        rows = []
        for index in range(60):
            close = 100.0 + index
            rows.append([index, close - 1.0, close + 1.0, close - 2.0, close, 10.0 + index])
        return rows

    controller._safe_fetch_ticker = fake_ticker
    controller._safe_fetch_ohlcv = fake_ohlcv
    controller.get_market_stream_status = lambda: "Running"
    controller._last_requested_symbol = None
    controller._last_requested_timeframe = None
    return controller


def test_handle_market_chat_action_returns_native_snapshot_for_symbol_request():
    controller = _make_controller()

    reply = asyncio.run(controller.handle_market_chat_action("BTC/USDT"))

    assert "BTC/USDT snapshot (1h)" in reply
    assert "Trend:" in reply
    assert "RSI14:" in reply
    assert "What do you want me to do" not in reply


def test_handle_market_chat_action_uses_requested_timeframe_for_market_snapshot():
    controller = _make_controller()

    reply = asyncio.run(controller.handle_market_chat_action("price btc/usdt 4h"))

    assert "BTC/USDT snapshot (4h)" in reply
    assert controller._last_requested_timeframe == "4h"


def test_handle_market_chat_action_supports_broker_market_symbols_not_in_loaded_list():
    controller = _make_controller()
    controller.broker = SimpleNamespace(
        symbols=["AAPL", "EUR/JPY"],
        exchange=SimpleNamespace(markets={"AAPL": {}, "EUR/JPY": {}, "XAU-USD": {}}),
    )

    reply = asyncio.run(controller.handle_market_chat_action("price eur/jpy"))

    assert "EUR/JPY snapshot (1h)" in reply
    assert controller._last_requested_symbol == "EUR/JPY"


def test_handle_market_chat_action_supports_single_ticker_symbols():
    controller = _make_controller()
    controller.broker = SimpleNamespace(
        symbols=["AAPL"],
        exchange=SimpleNamespace(markets={"AAPL": {}}),
    )

    reply = asyncio.run(controller.handle_market_chat_action("analyze aapl"))

    assert "AAPL snapshot (1h)" in reply
    assert controller._last_requested_symbol == "AAPL"
