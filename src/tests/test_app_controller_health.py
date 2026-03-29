import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.app_controller import AppController


def test_run_startup_health_check_pushes_notification_once_for_same_result():
    notifications = []
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.app_controller.health")
    controller.symbols = ["BTC/USDT"]
    controller.time_frame = "1h"
    controller.health_check_report = []
    controller.health_check_summary = "Not run"
    controller._startup_health_notification_signature = None
    controller.terminal = SimpleNamespace(
        _push_notification=lambda *args, **kwargs: notifications.append((args, kwargs))
    )

    async def fetch_status():
        return {"broker": "paper", "status": "ok"}

    async def fetch_orderbook(_symbol, limit=10):
        return {"bids": [[1.0, 1.0]], "asks": [[1.1, 1.0]]}

    async def fetch_positions():
        return []

    async def fetch_open_orders(symbol=None, limit=10):
        return []

    async def fetch_ohlcv(symbol, timeframe="1h", limit=50):
        return [[1, 1, 1, 1, 1, 1]]

    controller.broker = SimpleNamespace(
        fetch_status=fetch_status,
        fetch_ohlcv=fetch_ohlcv,
        fetch_orderbook=fetch_orderbook,
        fetch_positions=fetch_positions,
        fetch_open_orders=fetch_open_orders,
    )
    controller.get_broker_capabilities = lambda: {
        "connectivity": True,
        "ticker": True,
        "candles": True,
        "orderbook": True,
        "open_orders": True,
        "positions": True,
        "trading": True,
        "order_tracking": True,
    }
    controller._broker_is_connected = lambda broker=None: True

    async def fetch_balances(_broker=None):
        return {"free": {"USD": 1000.0}}

    async def fetch_ticker(symbol):
        return {"symbol": symbol, "last": 100.0}

    controller._fetch_balances = fetch_balances
    controller._safe_fetch_ticker = fetch_ticker

    asyncio.run(controller.run_startup_health_check())
    asyncio.run(controller.run_startup_health_check())

    assert "pass" in controller.health_check_summary
    assert len(notifications) == 1
    assert notifications[0][0][0] == "Startup health check"
