import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QComboBox, QDockWidget, QMainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.terminal import Terminal


class _SettingsRecorder:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class _MenuTerminal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = SimpleNamespace(language_code="en", set_language=lambda _code: None, symbols=[])
        self.show_bid_ask_lines = True
        self.current_connection_status = "connecting"
        self.language_actions = {}
        self.timeframe_buttons = {}
        self.autotrading_enabled = False
        self.connection_indicator = None
        self.symbol_label = None
        self.open_symbol_button = None
        self.screenshot_button = None
        self.system_status_button = None
        self.kill_switch_button = None
        self.session_mode_badge = None
        self.license_badge = None
        self.trading_activity_label = None
        self.favorite_symbols = set()
        self.detached_tool_windows = {}

    def _tr(self, key, **kwargs):
        return key

    def apply_language(self):
        return Terminal.apply_language(self)

    def _update_autotrade_button(self):
        return None

    def _set_active_timeframe_button(self, _timeframe):
        return None

    def _current_chart_symbol(self):
        return "BTC/USDT"

    def __getattr__(self, name):
        if name.startswith("_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _bind(fake, *names):
    for name in names:
        method = getattr(Terminal, name)
        setattr(fake, name, lambda *args, _method=method, **kwargs: _method(fake, *args, **kwargs))


def test_create_menu_bar_adds_workspace_notifications_palette_and_favorite_actions():
    _app()
    terminal = _MenuTerminal()

    Terminal._create_menu_bar(terminal)

    workspace_actions = terminal.workspace_menu.actions()
    assert terminal.action_workspace_trading in workspace_actions
    assert terminal.action_workspace_research in workspace_actions
    assert terminal.action_workspace_risk in workspace_actions
    assert terminal.action_workspace_review in workspace_actions
    assert terminal.action_save_workspace_layout in workspace_actions
    assert terminal.action_restore_workspace_layout in workspace_actions
    assert terminal.action_notifications in terminal.review_menu.actions()
    assert terminal.action_notifications in terminal.tools_menu.actions()
    assert terminal.action_command_palette in terminal.tools_menu.actions()
    assert terminal.action_favorite_symbol in terminal.charts_menu.actions()


def test_push_notification_dedupes_repeated_messages():
    fake = SimpleNamespace(
        _notification_records=[],
        _notification_dedupe_cache={},
        _runtime_notification_state={},
        detached_tool_windows={},
        action_notifications=None,
        _is_qt_object_alive=lambda _obj: False,
    )
    _bind(fake, "_ensure_notification_state", "_refresh_notification_action_text", "_push_notification")

    Terminal._push_notification(fake, "API disconnected", "Broker API is unavailable.", level="ERROR", source="broker", dedupe_seconds=60.0)
    Terminal._push_notification(fake, "API disconnected", "Broker API is unavailable.", level="ERROR", source="broker", dedupe_seconds=60.0)

    assert len(fake._notification_records) == 1
    assert fake._notification_records[0]["title"] == "API disconnected"


def test_manual_trade_default_payload_uses_saved_template_values():
    fake = SimpleNamespace(
        controller=SimpleNamespace(symbols=["EUR/USD"]),
        symbol="EUR/USD",
        current_timeframe="1h",
        _current_chart_symbol=lambda: "EUR/USD",
        _load_manual_trade_template=lambda: {
            "order_type": "stop_limit",
            "quantity_mode": "lots",
            "amount": 0.5,
            "stop_price": 1.102,
        },
        _safe_float=lambda value, default=None: Terminal._safe_float(SimpleNamespace(), value, default),
        _manual_trade_quantity_context=lambda symbol: {
            "symbol": symbol,
            "supports_lots": True,
            "default_mode": "lots",
            "lot_units": 100000.0,
        },
        _normalize_manual_trade_quantity_mode=lambda value: value,
    )

    payload = Terminal._manual_trade_default_payload(fake, {"symbol": "EUR/USD"})

    assert payload["order_type"] == "stop_limit"
    assert payload["quantity_mode"] == "lots"
    assert payload["amount"] == 0.5
    assert payload["stop_price"] == 1.102


def test_apply_workspace_preset_toggles_docks_and_opens_matching_tools():
    _app()
    fake = QMainWindow()
    fake.settings = _SettingsRecorder()
    fake.favorite_symbols = set()
    fake.detached_tool_windows = {}
    fake.system_console = SimpleNamespace(log=lambda *args, **kwargs: None)
    fake._is_qt_object_alive = lambda obj: obj is not None
    fake._queue_terminal_layout_fit = lambda: None
    fake._save_workspace_layout = lambda slot="last": True
    fake._push_notification = lambda *args, **kwargs: None
    opened = []
    fake._open_tool_window_by_key = lambda key: opened.append(key)
    for attr_name in (
        "market_watch_dock",
        "positions_dock",
        "trade_log_dock",
        "orderbook_dock",
        "risk_heatmap_dock",
        "system_status_dock",
        "system_console_dock",
    ):
        dock = QDockWidget(attr_name, fake)
        dock.show()
        setattr(fake, attr_name, dock)

    Terminal._apply_workspace_preset(fake, "risk")

    assert fake.market_watch_dock.isHidden()
    assert not fake.positions_dock.isHidden()
    assert not fake.orderbook_dock.isHidden()
    assert not fake.risk_heatmap_dock.isHidden()
    assert not fake.system_status_dock.isHidden()
    assert not fake.system_console_dock.isHidden()
    assert opened == ["portfolio_exposure", "position_analysis"]


def test_command_palette_entries_include_operator_actions():
    fake = SimpleNamespace(
        controller=SimpleNamespace(symbols=[]),
        _open_manual_trade=lambda *args, **kwargs: None,
        _open_notification_center=lambda: None,
        _open_performance=lambda: None,
        _show_portfolio_exposure=lambda: None,
        _open_position_analysis_window=lambda: None,
        _open_trade_checklist_window=lambda: None,
        _open_trade_journal_review_window=lambda: None,
        _open_recommendations_window=lambda: None,
        _open_market_chat_window=lambda: None,
        _open_quant_pm_window=lambda: None,
        _open_strategy_assignment_window=lambda: None,
        _optimize_strategy=lambda: None,
        _show_backtest_window=lambda: None,
        _apply_workspace_preset=lambda _name: None,
        _save_current_workspace_layout=lambda: None,
        _restore_saved_workspace_layout=lambda: None,
        _toggle_current_symbol_favorite=lambda: None,
        _refresh_markets=lambda: None,
        _refresh_active_chart_data=lambda: None,
        _refresh_active_orderbook=lambda: None,
        _reload_balance=lambda: None,
    )

    entries = Terminal._command_palette_entries(fake, "workspace")
    titles = {entry["title"] for entry in entries}

    assert "Trading Workspace" in titles
    assert "Research Workspace" in titles
    assert "Risk Workspace" in titles
    assert "Review Workspace" in titles


def test_chart_context_action_supports_market_ticket_prefill():
    captured = {}
    fake = SimpleNamespace(
        _current_chart_symbol=lambda: "BTC/USDT",
        _open_manual_trade=lambda prefill=None: captured.setdefault("prefill", dict(prefill or {})),
    )

    Terminal._handle_chart_trade_context_action(
        fake,
        {"action": "buy_market_ticket", "symbol": "BTC/USDT", "timeframe": "1h", "price": 100.0},
    )

    assert captured["prefill"]["symbol"] == "BTC/USDT"
    assert captured["prefill"]["side"] == "buy"
    assert captured["prefill"]["order_type"] == "market"
