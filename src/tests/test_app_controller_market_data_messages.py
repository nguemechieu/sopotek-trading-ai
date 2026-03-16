import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.app_controller import AppController


class _SignalRecorder:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _BufferRecorder:
    def __init__(self):
        self.calls = []

    def update(self, symbol, row):
        self.calls.append((symbol, dict(row)))


def _make_controller(candles):
    logs = []
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.market_data_messages")
    controller.time_frame = "1h"
    controller.terminal = SimpleNamespace(
        system_console=SimpleNamespace(log=lambda message, level="INFO": logs.append((message, level)))
    )
    controller.candle_buffers = {}
    controller.candle_buffer = _BufferRecorder()
    controller.candle_signal = _SignalRecorder()
    controller._market_data_shortfall_notices = {}
    controller._resolve_history_limit = lambda limit=None: int(limit or 200)

    async def fake_fetch(symbol, timeframe="1h", limit=200):
        return candles

    controller._safe_fetch_ohlcv = fake_fetch
    return controller, logs


def test_request_candle_data_warns_when_history_is_short():
    candles = [
        [1, 100.0, 101.0, 99.0, 100.5, 10.0],
        [2, 100.5, 101.5, 100.0, 101.0, 12.0],
        [3, 101.0, 102.0, 100.5, 101.2, 11.0],
    ]
    controller, logs = _make_controller(candles)

    df = asyncio.run(controller.request_candle_data("XLM/USDC", timeframe="1h", limit=120))

    assert df is not None
    assert any("Not enough data for XLM/USDC (1h): received 3 of 120 requested candles." in message for message, _ in logs)
    assert logs[-1][1] == "WARN"
    assert controller.candle_signal.calls


def test_request_candle_data_warns_when_no_history_is_available():
    controller, logs = _make_controller([])

    df = asyncio.run(controller.request_candle_data("XLM/USDC", timeframe="1h", limit=120))

    assert df is None
    assert logs == [
        (
            "Not enough data for XLM/USDC (1h): no candles were returned. Try another timeframe, load more history, or wait for more market data.",
            "WARN",
        )
    ]
    assert controller.candle_signal.calls == []


def test_extract_balance_equity_value_reads_nested_nav():
    controller = AppController.__new__(AppController)

    equity = controller._extract_balance_equity_value(
        {
            "raw": {
                "NAV": "12500.25",
            }
        }
    )

    assert equity == 12500.25


def test_update_balance_records_equity_and_emits_signal():
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.app_controller.performance")
    controller.broker = SimpleNamespace(fetch_balance=lambda: None)
    controller.balance = {}
    controller.balances = {}
    controller.equity_signal = _SignalRecorder()
    behavior_guard_updates = []
    controller._update_behavior_guard_equity = lambda balances: behavior_guard_updates.append(dict(balances))
    recorded_equity = []
    controller.performance_engine = SimpleNamespace(
        equity_curve=[],
        update_equity=lambda value: recorded_equity.append(float(value)),
    )

    async def fake_fetch_balance():
        return {"raw": {"NAV": "10250.50"}}

    controller.broker.fetch_balance = fake_fetch_balance

    asyncio.run(controller.update_balance())

    assert controller.balances == {"raw": {"NAV": "10250.50"}}
    assert controller.balance == {"raw": {"NAV": "10250.50"}}
    assert recorded_equity == [10250.5]
    assert controller.equity_signal.calls == [(10250.5,)]
    assert behavior_guard_updates == [{"raw": {"NAV": "10250.50"}}]
