import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.terminal import Terminal


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_populate_positions_table_adds_close_action_widgets():
    _app()
    table = QTableWidget()
    close_all_button = QPushButton()
    fake = SimpleNamespace(
        positions_table=table,
        positions_close_all_button=close_all_button,
        controller=SimpleNamespace(broker=object()),
        _normalize_position_entry=lambda raw: Terminal._normalize_position_entry(SimpleNamespace(_lookup_symbol_mid_price=lambda _symbol: None), raw),
        _action_button_style=lambda: "",
    )
    fake._build_position_close_button = lambda position, compact=False: Terminal._build_position_close_button(fake, position, compact=compact)
    fake._confirm_close_position = lambda position: None

    Terminal._populate_positions_table(
        fake,
        [
            {
                "symbol": "EUR/USD",
                "side": "long",
                "amount": 2.0,
                "entry_price": 1.1,
                "mark_price": 1.2,
                "pnl": 10.0,
            }
        ],
    )

    assert table.rowCount() == 1
    assert table.cellWidget(0, 7) is not None
    assert isinstance(table.cellWidget(0, 7), QPushButton)
    assert close_all_button.isEnabled() is True


def test_close_position_async_calls_controller_and_refreshes_views():
    refreshed = {"positions": 0, "analysis": 0, "messages": []}

    async def fake_close_market_chat_position(symbol, amount=None):
        refreshed["symbol"] = symbol
        refreshed["amount"] = amount
        return {"status": "submitted"}

    fake = SimpleNamespace(
        controller=SimpleNamespace(close_market_chat_position=fake_close_market_chat_position),
        system_console=SimpleNamespace(log=lambda *_args, **_kwargs: None),
        logger=SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        _schedule_positions_refresh=lambda: refreshed.__setitem__("positions", refreshed["positions"] + 1),
        _refresh_position_analysis_window=lambda: refreshed.__setitem__("analysis", refreshed["analysis"] + 1),
        _show_async_message=lambda title, text, icon=None: refreshed["messages"].append((title, text)),
    )

    asyncio.run(Terminal._close_position_async(fake, "EUR/USD", amount=1.5, show_dialog=True))

    assert refreshed["symbol"] == "EUR/USD"
    assert refreshed["amount"] == 1.5
    assert refreshed["positions"] == 1
    assert refreshed["analysis"] == 1
    assert refreshed["messages"]


def test_validate_manual_trade_amount_converts_micro_lots_to_oanda_units():
    fake = SimpleNamespace()
    fake.controller = SimpleNamespace(
        trade_quantity_context=lambda symbol: {
            "symbol": str(symbol).upper(),
            "supports_lots": True,
            "default_mode": "lots",
            "lot_units": 100000.0,
        }
    )
    fake._manual_trade_quantity_context = lambda symbol: Terminal._manual_trade_quantity_context(fake, symbol)
    fake._normalize_manual_trade_quantity_mode = lambda value: Terminal._normalize_manual_trade_quantity_mode(fake, value)
    fake._manual_trade_format_context = lambda _symbol: {
        "min_amount": 1.0,
        "amount_formatter": lambda value: value,
    }
    fake._normalize_manual_trade_amount = (
        lambda symbol, amount, quantity_mode="units": Terminal._normalize_manual_trade_amount(
            fake, symbol, amount, quantity_mode=quantity_mode
        )
    )

    amount, error = Terminal._validate_manual_trade_amount(fake, "EUR/USD", 0.01, quantity_mode="lots")

    assert error is None
    assert amount == 1000.0


def test_update_risk_heatmap_uses_live_position_snapshot():
    class _RiskMap:
        def __init__(self):
            self.image = None
            self.levels = None

        def setImage(self, image, autoLevels=False, levels=None):
            self.image = image
            self.levels = levels

    state = {}
    fake = SimpleNamespace(
        risk_map=_RiskMap(),
        _latest_positions_snapshot=[
            {
                "symbol": "EUR/USD",
                "side": "long",
                "amount": 1000.0,
                "entry_price": 1.10,
                "mark_price": 1.11,
                "value": 1110.0,
            }
        ],
        _normalize_position_entry=lambda raw: Terminal._normalize_position_entry(
            SimpleNamespace(_lookup_symbol_mid_price=lambda _symbol: None), raw
        ),
        _portfolio_positions_snapshot=lambda: [],
        _set_risk_heatmap_status=lambda message, tone="muted": state.update({"message": message, "tone": tone}),
    )
    fake._risk_heatmap_positions_snapshot = lambda: Terminal._risk_heatmap_positions_snapshot(fake)

    Terminal._update_risk_heatmap(fake)

    assert fake.risk_map.image is not None
    assert fake.risk_map.image.shape == (1, 1)
    assert "Live risk snapshot across 1 position" in state["message"]
    assert state["tone"] == "positive"
