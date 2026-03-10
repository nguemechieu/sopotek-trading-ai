import asyncio
import random
import sys
import traceback

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QSettings, QDateTime, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QTextCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QDockWidget,
    QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox,
    QTabWidget, QToolBar, QFileDialog, QDialog, QGridLayout, QDoubleSpinBox, QMessageBox, QFormLayout, QInputDialog, QColorDialog,
    QFrame,
    QHBoxLayout, QSizePolicy, QTextEdit, QTextBrowser
)
from shiboken6 import isValid

from backtesting.backtest_engine import BacktestEngine
from backtesting.report_generator import ReportGenerator
from backtesting.simulator import Simulator
from frontend.console.system_console import SystemConsole
from frontend.ui.chart.chart_widget import ChartWidget
from frontend.ui.i18n import iter_supported_languages
from frontend.ui.panels.orderbook_panel import OrderBookPanel

def global_exception_hook(exctype, value, tb):    # Suppress noisy shutdown interrupts (e.g., Ctrl+C/app exit).`n    if exctype in (KeyboardInterrupt, SystemExit):`n        return`n`n    print("UNCAUGHT EXCEPTION:")`n
   traceback.print_exception(exctype, value, tb)

def candles_to_df(df):
    raise NotImplementedError




class Terminal(QMainWindow):
    logout_requested = Signal()
    ai_signal = Signal(dict)
    autotrade_toggle = Signal(bool)
    def __init__(self, controller):

        super().__init__(controller)

        sys.excepthook = global_exception_hook

        self.controller = controller
        self.logger = controller.logger

        self.settings = QSettings("Sopotek", "TradingPlatform")

        self.symbols_table = QTableWidget()

        self.risk_map = None
        self.auto_button = QPushButton()

        self.historical_data = controller.historical_data

        self.confidence_data = []

        if controller.symbols:
            index = random.randint(0, len(controller.symbols) - 1)
            self.symbol = controller.symbols[index]
        else:
            self.symbol = "BTC/USDT"

        self.MAX_LOG_ROWS = getattr(controller,"symbols" )
        self.current_timeframe = getattr(controller,"time_frame")
        self.autotrading_enabled = False

        self.training_status = {}
        self.show_bid_ask_lines = True
        self._ui_shutting_down = False

        self.candle_up_color = self.settings.value("chart/candle_up_color", "#26a69a")
        self.candle_down_color = self.settings.value("chart/candle_down_color", "#ef5350")

        self.heartbeat = QLabel("●")
        self.heartbeat.setStyleSheet("color: green")

        self._setup_core()
        self._setup_ui()
        self._setup_panels()
        self._connect_signals()
        self._setup_spinner()

        if hasattr(self.controller, "language_changed"):
            self.controller.language_changed.connect(lambda _code: self.apply_language())

        self.controller.symbols_signal.connect(self._update_symbols)

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_terminal)
        self.refresh_timer.start(1000)

        self.orderbook_timer = QTimer()
        self.orderbook_timer.timeout.connect(self._request_active_orderbook)
        self.orderbook_timer.start(1500)

        self.ai_signal.connect(self._update_ai_signal)


    def _setup_core(self):

        self.order_type = self.controller.order_type
        self.setWindowTitle("Sopotek AI Trading Terminal")
        self.resize(1700, 950)

        self.connection_indicator = QLabel("● CONNECTING")
        self.connection_indicator.setStyleSheet(
            "color: orange; font-weight: bold;"
        )

        self.timeframe_buttons = {}
        self.toolbar = None
        self.toolbar_timeframe_label = None
        self.symbol_picker = None
        self.detached_tool_windows = {}
        self._last_chart_request_key = None
        self.current_connection_status = "connecting"
        self.language_actions = {}

    def _tr(self, key, **kwargs):
        if hasattr(self.controller, "tr"):
            return self.controller.tr(key, **kwargs)
        return key

    def _is_qt_object_alive(self, obj):
        try:
            return obj is not None and isValid(obj)
        except Exception:
            return False

    def _chart_tabs_ready(self):
        return (not self._ui_shutting_down) and self._is_qt_object_alive(
            getattr(self, "chart_tabs", None)
        )

    def _iter_chart_widgets(self):
        if not self._chart_tabs_ready():
            return []

        charts = []
        try:
            count = self.chart_tabs.count()
        except RuntimeError:
            return []

        for index in range(count):
            try:
                chart = self.chart_tabs.widget(index)
            except RuntimeError:
                break
            if isinstance(chart, ChartWidget):
                charts.append(chart)
        return charts

    def _current_chart_widget(self):
        if not self._chart_tabs_ready():
            return None
        try:
            chart = self.chart_tabs.currentWidget()
        except RuntimeError:
            return None
        if isinstance(chart, ChartWidget):
            return chart
        return None

    def _safe_disconnect(self, signal, slot):
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def _disconnect_controller_signals(self):
        controller = getattr(self, "controller", None)
        if controller is None:
            return

        for signal_name, slot in (
            ("candle_signal", self._update_chart),
            ("equity_signal", self._update_equity),
            ("trade_signal", self._update_trade_log),
            ("ticker_signal", self._update_ticker),
            ("orderbook_signal", self._update_orderbook),
            ("strategy_debug_signal", self._handle_strategy_debug),
            ("training_status_signal", self._update_training_status),
            ("symbols_signal", self._update_symbols),
        ):
            signal = getattr(controller, signal_name, None)
            if signal is not None:
                self._safe_disconnect(signal, slot)

        ai_monitor = getattr(controller, "ai_signal_monitor", None)
        if ai_monitor is not None:
            self._safe_disconnect(ai_monitor, self._update_ai_signal)

    def _timeframe_button_style(self):
        return """
            QPushButton {
                background-color: #162033;
                color: #c7d2e0;
                border: 1px solid #25314a;
                border-radius: 9px;
                padding: 6px 12px;
                font-weight: 600;
                min-width: 44px;
            }
            QPushButton:hover {
                background-color: #1d2940;
                border-color: #3c537f;
            }
            QPushButton:checked {
                background-color: #2a7fff;
                color: white;
                border-color: #65a3ff;
            }
        """

    def _action_button_style(self):
        return """
            QPushButton {
                background-color: #162033;
                color: #d7dfeb;
                border: 1px solid #2d3a56;
                border-radius: 12px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1c2940;
                border-color: #4f638d;
            }
        """

    def _set_active_timeframe_button(self, active_tf):
        for tf, button in self.timeframe_buttons.items():
            button.setChecked(tf == active_tf)

        if self.toolbar_timeframe_label is not None:
            self.toolbar_timeframe_label.setText(
                self._tr("terminal.toolbar.timeframe_active", timeframe=active_tf)
            )

    def _update_autotrade_button(self):
        if self.autotrading_enabled:
            self.auto_button.setText(self._tr("terminal.autotrade.on"))
            self.auto_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #123524;
                    color: #d7ffe9;
                    border: 1px solid #28a86b;
                    border-radius: 14px;
                    padding: 9px 16px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #184630;
                }
                """
            )
        else:
            self.auto_button.setText(self._tr("terminal.autotrade.off"))
            self.auto_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #34161a;
                    color: #ffd9de;
                    border: 1px solid #b45b68;
                    border-radius: 14px;
                    padding: 9px 16px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #442026;
                }
                """
            )

    def _setup_ui(self):

        self.chart_tabs = QTabWidget()
        self.chart_tabs.setTabsClosable(True)

        self.chart_tabs.tabCloseRequested.connect(
            lambda i: self.chart_tabs.removeTab(i)
        )
        self.chart_tabs.currentChanged.connect(self._on_chart_tab_changed)

        self.setCentralWidget(self.chart_tabs)

        self._create_menu_bar()
        self._create_toolbar()

        self._create_chart_tab(
            self.symbol,
            self.controller.time_frame
        )

        self._restore_settings()
        self.apply_language()

    # ==========================================================
    # MENU
    # ==========================================================

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("")
        self.action_generate_report = QAction(self)
        self.action_generate_report.triggered.connect(self._generate_report)
        self.file_menu.addAction(self.action_generate_report)
        self.action_export_trades = QAction(self)
        self.action_export_trades.triggered.connect(self._export_trades)
        self.file_menu.addAction(self.action_export_trades)
        self.file_menu.addSeparator()
        self.action_exit = QAction(self)
        self.action_exit.triggered.connect(self.close)
        self.file_menu.addAction(self.action_exit)

        self.trading_menu = menu_bar.addMenu("")
        self.action_start_trading = QAction(self)
        self.action_start_trading.triggered.connect(self._toggle_autotrading)
        self.action_start_trading.setShortcut("Ctrl+T")
        self.trading_menu.addAction(self.action_start_trading)
        self.action_stop_trading = QAction(self)
        self.trading_menu.addAction(self.action_stop_trading)
        self.action_manual_trade = QAction(self)
        self.action_manual_trade.triggered.connect(self._open_manual_trade)
        self.trading_menu.addAction(self.action_manual_trade)
        self.trading_menu.addSeparator()
        self.action_close_all = QAction(self)
        self.trading_menu.addAction(self.action_close_all)
        self.action_cancel_orders = QAction(self)
        self.trading_menu.addAction(self.action_cancel_orders)

        self.backtest_menu = menu_bar.addMenu("")
        self.action_run_backtest = QAction(self)
        self.action_run_backtest.triggered.connect(
            lambda: asyncio.get_event_loop().create_task(self.run_backtest_clicked())
        )
        self.action_run_backtest.setShortcut("Ctrl+B")
        self.backtest_menu.addAction(self.action_run_backtest)
        self.action_optimize_strategy = QAction(self)
        self.action_optimize_strategy.triggered.connect(self._optimize_strategy)
        self.backtest_menu.addAction(self.action_optimize_strategy)

        self.charts_menu = menu_bar.addMenu("")
        self.action_new_chart = QAction(self)
        self.action_new_chart.setShortcut("Ctrl+N")
        self.action_new_chart.triggered.connect(self._add_new_chart)
        self.charts_menu.addAction(self.action_new_chart)
        self.action_multi_chart = QAction(self)
        self.action_multi_chart.triggered.connect(self._multi_chart_layout)
        self.charts_menu.addAction(self.action_multi_chart)
        self.action_candle_colors = QAction(self)
        self.action_candle_colors.triggered.connect(self._choose_candle_colors)
        self.charts_menu.addAction(self.action_candle_colors)
        self.action_add_indicator = QAction(self)
        self.action_add_indicator.triggered.connect(self._add_indicator_to_current_chart)
        self.charts_menu.addAction(self.action_add_indicator)
        self.toggle_bid_ask_lines_action = QAction(self)
        self.toggle_bid_ask_lines_action.setCheckable(True)
        self.toggle_bid_ask_lines_action.setChecked(self.show_bid_ask_lines)
        self.toggle_bid_ask_lines_action.triggered.connect(self._toggle_bid_ask_lines)
        self.charts_menu.addAction(self.toggle_bid_ask_lines_action)

        self.data_menu = menu_bar.addMenu("")
        self.action_refresh_markets = QAction(self)
        self.action_refresh_markets.triggered.connect(self._refresh_markets)
        self.data_menu.addAction(self.action_refresh_markets)
        self.action_refresh_chart = QAction(self)
        self.action_refresh_chart.triggered.connect(self._refresh_active_chart_data)
        self.data_menu.addAction(self.action_refresh_chart)
        self.action_refresh_orderbook = QAction(self)
        self.action_refresh_orderbook.triggered.connect(self._refresh_active_orderbook)
        self.data_menu.addAction(self.action_refresh_orderbook)
        self.data_menu.addSeparator()
        self.action_reload_balance = QAction(self)
        self.action_reload_balance.triggered.connect(self._reload_balance)
        self.data_menu.addAction(self.action_reload_balance)

        self.settings_menu = menu_bar.addMenu("")
        self.action_app_settings = QAction(self)
        self.action_app_settings.triggered.connect(self._open_settings)
        self.settings_menu.addAction(self.action_app_settings)
        self.action_portfolio_view = QAction(self)
        self.action_portfolio_view.triggered.connect(self._show_portfolio_exposure)
        self.settings_menu.addAction(self.action_portfolio_view)

        self.language_menu = menu_bar.addMenu("")
        self.language_actions = {}
        for code, label in iter_supported_languages():
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, lang=code: self.controller.set_language(lang))
            self.language_menu.addAction(action)
            self.language_actions[code] = action

        self.tools_menu = menu_bar.addMenu("")
        self.action_ml_monitor = QAction(self)
        self.action_ml_monitor.triggered.connect(self._open_ml_monitor)
        self.tools_menu.addAction(self.action_ml_monitor)
        self.action_logs = QAction(self)
        self.action_logs.triggered.connect(self._open_logs)
        self.tools_menu.addAction(self.action_logs)
        self.action_performance = QAction(self)
        self.action_performance.triggered.connect(self._open_performance)
        self.tools_menu.addAction(self.action_performance)

        self.help_menu = menu_bar.addMenu("")
        self.action_documentation = QAction(self)
        self.action_documentation.triggered.connect(self._open_docs)
        self.help_menu.addAction(self.action_documentation)
        self.action_api_docs = QAction(self)
        self.action_api_docs.triggered.connect(self._open_api_docs)
        self.help_menu.addAction(self.action_api_docs)
        self.help_menu.addSeparator()
        self.action_about = QAction(self)
        self.action_about.triggered.connect(self._show_about)
        self.help_menu.addAction(self.action_about)

        self.apply_language()

    def update_connection_status(self, status: str):
        self.current_connection_status = status

        if status == "connected":
            self.connection_indicator.setText("● CONNECTED")
            self.connection_indicator.setStyleSheet(
                "color: green; font-weight: bold;"
            )
        elif status == "disconnected":
            self.connection_indicator.setText("● DISCONNECTED")
            self.connection_indicator.setStyleSheet(
                "color: red; font-weight: bold;"
            )
        else:
            self.connection_indicator.setText("● CONNECTING")
            self.connection_indicator.setStyleSheet(
                "color: orange; font-weight: bold;"
            )

    def apply_language(self):
        self.setWindowTitle(self._tr("terminal.window_title"))

        if hasattr(self, "file_menu"):
            self.file_menu.setTitle(self._tr("terminal.menu.file"))
            self.trading_menu.setTitle(self._tr("terminal.menu.trading"))
            self.backtest_menu.setTitle(self._tr("terminal.menu.backtesting"))
            self.charts_menu.setTitle(self._tr("terminal.menu.charts"))
            self.data_menu.setTitle(self._tr("terminal.menu.data"))
            self.settings_menu.setTitle(self._tr("terminal.menu.settings"))
            self.language_menu.setTitle(self._tr("terminal.menu.language"))
            self.tools_menu.setTitle(self._tr("terminal.menu.tools"))
            self.help_menu.setTitle(self._tr("terminal.menu.help"))

            self.action_generate_report.setText(self._tr("terminal.action.generate_report"))
            self.action_export_trades.setText(self._tr("terminal.action.export_trades"))
            self.action_exit.setText(self._tr("terminal.action.exit"))
            self.action_start_trading.setText(self._tr("terminal.action.start_auto"))
            self.action_stop_trading.setText(self._tr("terminal.action.stop_auto"))
            self.action_manual_trade.setText(self._tr("terminal.action.manual_trade"))
            self.action_close_all.setText(self._tr("terminal.action.close_all"))
            self.action_cancel_orders.setText(self._tr("terminal.action.cancel_all"))
            self.action_run_backtest.setText(self._tr("terminal.action.run_backtest"))
            self.action_optimize_strategy.setText(self._tr("terminal.action.optimize"))
            self.action_new_chart.setText(self._tr("terminal.action.new_chart"))
            self.action_multi_chart.setText(self._tr("terminal.action.multi_chart"))
            self.action_candle_colors.setText(self._tr("terminal.action.candle_colors"))
            self.action_add_indicator.setText(self._tr("terminal.action.add_indicator"))
            self.toggle_bid_ask_lines_action.setText(self._tr("terminal.action.toggle_bid_ask"))
            self.action_refresh_markets.setText(self._tr("terminal.action.refresh_markets"))
            self.action_refresh_chart.setText(self._tr("terminal.action.refresh_chart"))
            self.action_refresh_orderbook.setText(self._tr("terminal.action.refresh_orderbook"))
            self.action_reload_balance.setText(self._tr("terminal.action.reload_balance"))
            self.action_app_settings.setText(self._tr("terminal.action.app_settings"))
            self.action_portfolio_view.setText(self._tr("terminal.action.portfolio"))
            self.action_ml_monitor.setText(self._tr("terminal.action.ml_monitor"))
            self.action_logs.setText(self._tr("terminal.action.logs"))
            self.action_performance.setText(self._tr("terminal.action.performance"))
            self.action_documentation.setText(self._tr("terminal.action.documentation"))
            self.action_api_docs.setText(self._tr("terminal.action.api_reference"))
            self.action_about.setText(self._tr("terminal.action.about"))

            active_language = getattr(self.controller, "language_code", "en")
            for code, action in self.language_actions.items():
                action.blockSignals(True)
                action.setChecked(code == active_language)
                action.blockSignals(False)

        if getattr(self, "symbol_label", None) is not None:
            self.symbol_label.setText(self._tr("terminal.toolbar.symbol"))
        if getattr(self, "open_symbol_button", None) is not None:
            self.open_symbol_button.setText(self._tr("terminal.toolbar.open_symbol"))
        if getattr(self, "screenshot_button", None) is not None:
            self.screenshot_button.setText(self._tr("terminal.toolbar.screenshot"))

        self._set_active_timeframe_button(getattr(self, "current_timeframe", "1h"))
        self._update_autotrade_button()

        status_key = {
            "connected": "terminal.status.connected",
            "disconnected": "terminal.status.disconnected",
        }.get(self.current_connection_status, "terminal.status.connecting")
        if getattr(self, "connection_indicator", None) is not None:
            self.connection_indicator.setText(f"* {self._tr(status_key)}")

    # ==========================================================
    # TOOLBAR
    # ==========================================================

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("QToolBar { spacing: 8px; padding: 6px; }")
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        symbol_box = QFrame()
        symbol_box.setStyleSheet(
            "QFrame { background-color: #101827; border: 1px solid #24324a; border-radius: 14px; }"
        )
        symbol_layout = QHBoxLayout(symbol_box)
        symbol_layout.setContentsMargins(10, 6, 10, 6)
        symbol_layout.setSpacing(8)

        self.symbol_label = QLabel(self._tr("terminal.toolbar.symbol"))
        self.symbol_label.setStyleSheet("color: #9fb0c7; font-weight: 700;")
        symbol_layout.addWidget(self.symbol_label)

        self.symbol_picker = QComboBox()
        self.symbol_picker.setMinimumWidth(170)
        self.symbol_picker.setStyleSheet(
            """
            QComboBox {
                background-color: #162033;
                color: #d7dfeb;
                border: 1px solid #2d3a56;
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 600;
            }
            QComboBox::drop-down {
                border: 0;
                width: 24px;
            }
            """
        )
        for sym in self.controller.symbols:
            self.symbol_picker.addItem(sym)
        self.symbol_picker.setCurrentText(self.symbol)
        self.symbol_picker.activated.connect(lambda _=None: self._open_symbol_from_picker())
        symbol_layout.addWidget(self.symbol_picker)

        self.open_symbol_button = QPushButton(self._tr("terminal.toolbar.open_symbol"))
        self.open_symbol_button.setStyleSheet(self._action_button_style())
        self.open_symbol_button.clicked.connect(self._open_symbol_from_picker)
        symbol_layout.addWidget(self.open_symbol_button)

        toolbar.addWidget(symbol_box)

        timeframe_box = QFrame()
        timeframe_box.setStyleSheet(
            "QFrame { background-color: #0f1726; border: 1px solid #24324a; border-radius: 16px; }"
        )
        timeframe_layout = QHBoxLayout(timeframe_box)
        timeframe_layout.setContentsMargins(10, 6, 10, 6)
        timeframe_layout.setSpacing(6)

        self.toolbar_timeframe_label = QLabel(self._tr("terminal.toolbar.timeframe"))
        self.toolbar_timeframe_label.setStyleSheet("color: #9fb0c7; font-weight: 700; padding-right: 6px;")
        timeframe_layout.addWidget(self.toolbar_timeframe_label)

        for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mn"]:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setStyleSheet(self._timeframe_button_style())
            btn.clicked.connect(lambda _, t=tf: self._set_timeframe(t))
            timeframe_layout.addWidget(btn)
            self.timeframe_buttons[tf] = btn

        toolbar.addWidget(timeframe_box)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        actions_box = QFrame()
        actions_box.setStyleSheet(
            "QFrame { background-color: #0f1726; border: 1px solid #24324a; border-radius: 16px; }"
        )
        actions_layout = QHBoxLayout(actions_box)
        actions_layout.setContentsMargins(8, 6, 8, 6)
        actions_layout.setSpacing(8)

        self.auto_button = QPushButton()
        self.auto_button.clicked.connect(self._toggle_autotrading)
        actions_layout.addWidget(self.auto_button)

        self.screenshot_button = QPushButton(self._tr("terminal.toolbar.screenshot"))
        self.screenshot_button.setStyleSheet(self._action_button_style())
        self.screenshot_button.clicked.connect(self.take_screen_shot)
        actions_layout.addWidget(self.screenshot_button)

        toolbar.addWidget(actions_box)

        self._set_active_timeframe_button(self.current_timeframe)
        self._update_autotrade_button()
        return

        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        toolbar.addWidget(self.connection_indicator)

        self.heartbeat.setText("●")
        toolbar.addWidget(self.heartbeat)

        for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mn"]:
            btn = QPushButton(tf)
            btn.clicked.connect(lambda _, t=tf: self._set_timeframe(t))


            toolbar.addWidget(btn)
            toolbar.addSeparator()


            self.timeframe_buttons[tf] = btn

        toolbar.addSeparator()
        self.auto_button = QPushButton("AutoTrading OFF")
        self.auto_button.clicked.connect(self._toggle_autotrading)

        toolbar.addWidget(self.auto_button)



        screenshot_btn = QPushButton("Screenshot")
        screenshot_btn.clicked.connect(self.take_screen_shot)
        toolbar.addWidget(screenshot_btn)

    # ==========================================================
    # AUTOTRADING
    # ==========================================================

    def _toggle_autotrading(self):

     self.autotrading_enabled = not self.autotrading_enabled

     if self.autotrading_enabled:

        if not self.controller.trading_system:
            self.logger.error("Trading system is not initialized yet")
            QMessageBox.warning(
                self,
                self._tr("terminal.warning.trading_not_ready_title"),
                self._tr("terminal.warning.trading_not_ready_body"),
            )
            self.autotrading_enabled = False
            self._update_autotrade_button()
            self.autotrade_toggle.emit(False)
            return

        self._update_autotrade_button()

        loop = asyncio.get_event_loop()
        loop.create_task(self.controller.trading_system.start())
        self.autotrade_toggle.emit(True)

     else:

        self._update_autotrade_button()

        if self.controller.trading_system:
            asyncio.create_task(self.controller.trading_system.stop())

        self.autotrade_toggle.emit(False)

    # ==========================================================
    # CHARTS
    # ==========================================================

    def _create_chart_tab(self, symbol, timeframe):
        chart = ChartWidget(
            symbol,
            timeframe,
            self.controller,
            candle_up_color=self.candle_up_color,
            candle_down_color=self.candle_down_color,
        )
        chart.set_bid_ask_lines_visible(self.show_bid_ask_lines)

        row = self.symbols_table.rowCount()
        self.symbols_table.insertRow(row)

        self.symbols_table.setItem(row, 0, QTableWidgetItem(symbol))
        self.symbols_table.setItem(row, 1, QTableWidgetItem("-"))
        self.symbols_table.setItem(row, 2, QTableWidgetItem("-"))
        self.symbols_table.setItem(row, 3, QTableWidgetItem("? Training..."))
        self.chart_tabs.addTab(chart, f"{symbol} ({timeframe})")
        chart.link_all_charts(self.chart_tabs.count())
        self.chart_tabs.setCurrentWidget(chart)
        if self.symbol_picker is not None:
            self.symbol_picker.setCurrentText(symbol)
        self._request_active_orderbook()

    def _on_chart_tab_changed(self, index):
        if not self._chart_tabs_ready():
            return

        try:
            chart = self.chart_tabs.widget(index)
        except RuntimeError:
            return
        if not isinstance(chart, ChartWidget):
            return

        self.current_timeframe = chart.timeframe
        if self.symbol_picker is not None:
            self.symbol_picker.setCurrentText(chart.symbol)

        request_key = (chart.symbol, chart.timeframe)
        if request_key == self._last_chart_request_key:
            self._request_active_orderbook()
            asyncio.get_event_loop().create_task(
                self._reload_chart_data(chart.symbol, chart.timeframe)
            )
            return

        self._last_chart_request_key = request_key

        if hasattr(self.controller, "request_candle_data"):
            asyncio.get_event_loop().create_task(
                self.controller.request_candle_data(
                    symbol=chart.symbol,
                    timeframe=chart.timeframe,
                    limit=300,
                )
            )
        self._request_active_orderbook()

        asyncio.get_event_loop().create_task(
            self._reload_chart_data(chart.symbol, chart.timeframe)
        )

    def _add_new_chart(self):
        symbol, ok = QInputDialog.getText(
            self,
            self._tr("terminal.dialog.new_chart_title"),
            self._tr("terminal.dialog.new_chart_prompt"),
        )
        if ok and symbol:
            self._open_symbol_chart(symbol.upper(), self.current_timeframe)

    def _find_chart_tab(self, symbol, timeframe):
        if not self._chart_tabs_ready():
            return -1

        for i in range(self.chart_tabs.count()):
            chart = self.chart_tabs.widget(i)
            if isinstance(chart, ChartWidget) and chart.symbol == symbol and chart.timeframe == timeframe:
                return i
        return -1

    def _open_symbol_chart(self, symbol, timeframe=None):
        target_symbol = (symbol or "").strip().upper()
        if not target_symbol:
            return

        target_timeframe = timeframe or self.current_timeframe
        existing_index = self._find_chart_tab(target_symbol, target_timeframe)
        if existing_index >= 0:
            self.chart_tabs.setCurrentIndex(existing_index)
            return

        self.training_status[target_symbol] = "TRAINING"
        self._create_chart_tab(target_symbol, target_timeframe)

    def _open_symbol_from_picker(self):
        if self.symbol_picker is None:
            return

        self._open_symbol_chart(self.symbol_picker.currentText(), self.current_timeframe)

    def _set_timeframe(self, tf="1h"):

        self.current_timeframe = tf
        self._set_active_timeframe_button(tf)

        if not self._chart_tabs_ready():
            return

        index = self.chart_tabs.currentIndex()
        chart = self.chart_tabs.widget(index)

        if not isinstance(chart, ChartWidget):
            return

        chart.timeframe = tf

        self.chart_tabs.setTabText(
            index,
            f"{chart.symbol} ({tf})"
        )

        # Request fresh candles for selected timeframe.
        if hasattr(self.controller, "request_candle_data"):
            asyncio.get_event_loop().create_task(
                self.controller.request_candle_data(symbol=chart.symbol, timeframe=tf, limit=300)
            )
        self._request_active_orderbook()

        asyncio.get_event_loop().create_task(
            self._reload_chart_data(chart.symbol, tf)
        )

    def _toggle_bid_ask_lines(self, checked):
        self.show_bid_ask_lines = bool(checked)

        for chart in self._iter_chart_widgets():
            chart.set_bid_ask_lines_visible(self.show_bid_ask_lines)

    # ==========================================================
    # UPDATE METHODS
    # ==========================================================
    def _update_chart(self, symbol, df):
        if self._ui_shutting_down:
            return

        df = candles_to_df(df)

        for chart in self._iter_chart_widgets():
            if chart.symbol == symbol:
                chart.update_candles(df)

        self.heartbeat.setStyleSheet("color: green;")

    def _update_equity(self, equity):
        self.equity_label.setText(f"Equity: {equity:.2f}")
        self.equity_curve.setData(self.controller.performance_engine.equity_history)

    def _update_trade_log(self, trade):

        row = self.trade_log.rowCount()

        if row >= self.MAX_LOG_ROWS:
            self.trade_log.removeRow(0)
            row -= 1

        self.trade_log.insertRow(row)
        self.trade_log.setItem(row, 0, QTableWidgetItem(str(trade.get("symbol", ""))))
        self.trade_log.setItem(row, 1, QTableWidgetItem(str(trade.get("side", ""))))
        self.trade_log.setItem(row, 2, QTableWidgetItem(str(trade.get("price", ""))))
        self.trade_log.setItem(row, 3, QTableWidgetItem(str(trade.get("size", ""))))
        self.trade_log.setItem(row, 4, QTableWidgetItem(str(trade.get("sl", ""))))
        self.trade_log.setItem(row, 5, QTableWidgetItem(str(trade.get("tp", ""))))
        self.trade_log.setItem(row, 6, QTableWidgetItem(str(trade.get("rt", ""))))
        self.symbols_table.horizontalHeader().setStretchLastSection(True)
        self.trade_log.horizontalHeader().setStretchLastSection(True)

    def _update_ticker(self, symbol, bid, ask):
        if self._ui_shutting_down:
            return

        # Ensure symbol appears in the table even if symbols were not pre-populated.
        target_row = None

        for row in range(self.symbols_table.rowCount()):
            item = self.symbols_table.item(row, 0)

            if item and item.text() == symbol:
                target_row = row
                break

        if target_row is None:
            target_row = self.symbols_table.rowCount()
            self.symbols_table.insertRow(target_row)
            self.symbols_table.setItem(target_row, 0, QTableWidgetItem(str(symbol)))
            self.symbols_table.setItem(target_row, 3, QTableWidgetItem("Live"))

        self.symbols_table.setItem(target_row, 1, QTableWidgetItem(str(bid)))
        self.symbols_table.setItem(target_row, 2, QTableWidgetItem(str(ask)))

        try:
            mid = (float(bid) + float(ask)) / 2
        except Exception:
            mid = 0.0

        self.tick_prices.append(mid)

        if len(self.tick_prices) > 200:
            self.tick_prices.pop(0)

        self.tick_chart_curve.setData(self.tick_prices)

        # Push live price lines to matching chart tabs.
        for chart in self._iter_chart_widgets():
            if chart.symbol == symbol:
                chart.update_price_lines(bid=bid, ask=ask, last=mid)

    # ==========================================================
    # PANELS
    # ==========================================================

    def _create_market_watch_panel(self):
        dock = QDockWidget("Market Watch", self)
        self.symbols_table = QTableWidget()
        self.symbols_table.setColumnCount(4)
        self.symbols_table.setHorizontalHeaderLabels(
            ["Symbol", "Bid", "Ask", "AI Training"]
        )
        dock.setWidget(self.symbols_table)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        self.tick_chart = pg.PlotWidget()
        self.tick_chart_curve = self.tick_chart.plot(pen="y")
        self.tick_prices = []

        tick_dock = QDockWidget("Tick Chart", self)
        tick_dock.setWidget(self.tick_chart)
        self.addDockWidget(Qt.LeftDockWidgetArea, tick_dock)

    def _create_positions_panel(self):
        dock = QDockWidget("Positions", self)
        self.positions_table = QTableWidget()
        dock.setWidget(self.positions_table)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    def _create_orderbook_panel(self):
        dock = QDockWidget("Orderbook", self)
        self.orderbook_panel = OrderBookPanel()
        dock.setWidget(self.orderbook_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _create_trade_log_panel(self):
        dock = QDockWidget("Trade Log", self)
        self.trade_log = QTableWidget()
        self.trade_log.setColumnCount(9)
        self.trade_log.setHorizontalHeaderLabels(
            ["Symbol", "Price", "Size", "OrderType", "Side", "SL", "TP", "TimeStamp", "Pnl"])
        dock.setWidget(self.trade_log)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _create_equity_panel(self):

        dock = QDockWidget("Equity Curve", self)

        container = QWidget()
        layout = QVBoxLayout()

        self.equity_label = QLabel("Equity: 0")
        layout.addWidget(self.equity_label)

        self.equity_chart = pg.PlotWidget()
        self.equity_curve = self.equity_chart.plot(pen="g")

        layout.addWidget(self.equity_chart)

        container.setLayout(layout)

        dock.setWidget(container)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _create_performance_panel(self):
        dock = QDockWidget("Performance", self)
        container = QWidget()
        layout = QVBoxLayout()

        self.equity_label = QLabel("Equity: 0")
        layout.addWidget(self.equity_label)

        container.setLayout(layout)
        dock.setWidget(container)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _create_strategy_comparison(self):
        dock = QDockWidget("Strategy Comparison", self)
        self.strategy_table = QTableWidget()
        dock.setWidget(self.strategy_table)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    # ==========================================================
    # BACKTEST
    # ==========================================================

    async def run_backtest_clicked(self):

     try:
      if self.controller.orchestrator:
        # Initialize backtest engine
        self.backtest_engine = BacktestEngine(
            strategy=self.controller.orchestrator,
            data=self.historical_data,
            initial_capital=self.controller.initial_capital,
            slippage=self.controller.slippage,
            commission=self.controller.commission
        )

        # Buttons
        start_btn = QPushButton("Start Backtest")
        stop_btn = QPushButton("Stop Backtest")

        start_btn.clicked.connect(self.start_backtest)
        stop_btn.clicked.connect(self.stop_backtest)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(start_btn)
        layout.addWidget(stop_btn)

        # Backtest widget
        backtest_widget = QWidget()
        backtest_widget.setLayout(layout)

        # Dock widget
        self.backtest_dock = QDockWidget("Backtest Results", self)
        self.backtest_dock.setWidget(backtest_widget)

        self.addDockWidget(Qt.RightDockWidgetArea, self.backtest_dock)
      else:

          raise RuntimeError(
              "Please start trading first"
          )

     except Exception as e:

        self.system_console.log(
            f"Backtest initialization error: {e.__str__()}",
            "ERROR"
        )






    # ==========================================================
    # REPORT
    # ==========================================================

    def _generate_report(self):
        generator = ReportGenerator(
            trades=self.controller.performance_engine.trades,
            equity_history=self.controller.performance_engine.equity_history
        )
        generator.export_pdf()
        generator.export_excel()
        self.system_console.log("Report Generated", "INFO")

    # ==========================================================
    # SCREENSHOT
    # ==========================================================

    def take_screen_shot(self):
        pixmap = self.grab()
        timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        filename = f"Sopotek_Screenshot_{timestamp}.png"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", filename, "PNG Files (*.png)"
        )

        if path:
            pixmap.save(path, "PNG")
            self.system_console.log("Screenshot saved", "INFO")




    #######################################################
    # Start BackTesting
    #######################################################
    def start_backtest(self):
      self.results= engine.run()









    # ==========================================================
    # SETTINGS
    # ==========================================================

    def closeEvent(self, event):
        self._ui_shutting_down = True

        # Stop periodic timers to prevent callbacks while widgets are tearing down.
        try:
            if hasattr(self, "refresh_timer") and self.refresh_timer is not None:
                self.refresh_timer.stop()
            if hasattr(self, "orderbook_timer") and self.orderbook_timer is not None:
                self.orderbook_timer.stop()
            if hasattr(self, "spinner_timer") and self.spinner_timer is not None:
                self.spinner_timer.stop()
        except Exception:
            pass

        try:
            self._disconnect_controller_signals()
            self._safe_disconnect(self.ai_signal, self._update_ai_signal)
        except Exception:
            pass

        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("chart/candle_up_color", self.candle_up_color)
        self.settings.setValue("chart/candle_down_color", self.candle_down_color)
        super().closeEvent(event)

    def _restore_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

        self._apply_candle_colors_to_all_charts()

    def _apply_candle_colors_to_all_charts(self):
        for chart in self._iter_chart_widgets():
            chart.set_candle_colors(self.candle_up_color, self.candle_down_color)

    def _choose_candle_colors(self):
        up = QColorDialog.getColor(QColor(self.candle_up_color), self, "Select Bullish Candle Color")
        if not up.isValid():
            return

        down = QColorDialog.getColor(QColor(self.candle_down_color), self, "Select Bearish Candle Color")
        if not down.isValid():
            return

        self.candle_up_color = up.name()
        self.candle_down_color = down.name()

        self.settings.setValue("chart/candle_up_color", self.candle_up_color)
        self.settings.setValue("chart/candle_down_color", self.candle_down_color)

        self._apply_candle_colors_to_all_charts()

    def _add_indicator_to_current_chart(self):
        index = self.chart_tabs.currentIndex()
        chart = self.chart_tabs.widget(index)

        if not isinstance(chart, ChartWidget):
            QMessageBox.warning(self, "Chart", "Select a chart tab first.")
            return

        options = [
            "SMA",
            "EMA",
            "WMA",
            "VWAP",
            "Bollinger Bands",
            "Donchian Channel",
            "Keltner Channel",
            "Fractal",
            "ZigZag",
        ]
        indicator, ok = QInputDialog.getItem(
            self,
            "Add Indicator",
            "Indicator:",
            options,
            0,
            False,
        )
        if not ok or not indicator:
            return

        period, ok = QInputDialog.getInt(
            self,
            "Indicator Period",
            "Period:",
            20,
            2,
            500,
            1,
        )
        if not ok:
            return

        key = chart.add_indicator(indicator, period)
        if key is None:
            QMessageBox.warning(self, "Indicator", "Unsupported indicator.")
            return

        # Force redraw using existing candle cache for this symbol/timeframe.
        asyncio.get_event_loop().create_task(self._reload_chart_data(chart.symbol, chart.timeframe))

    def _update_orderbook(self, symbol, bids, asks):
        if self._ui_shutting_down:
            return

        active_symbol = self._current_chart_symbol()

        if hasattr(self, "orderbook_panel") and active_symbol == symbol:
            self.orderbook_panel.update_orderbook(bids, asks)

        for chart in self._iter_chart_widgets():
            if chart.symbol == symbol:
                chart.update_orderbook_heatmap(bids, asks)

    def _create_strategy_debug_panel(self):

        dock = QDockWidget("Strategy Debug", self)

        self.debug_table = QTableWidget()
        self.debug_table.setColumnCount(7)
        self.debug_table.setHorizontalHeaderLabels([
            "Index", "Signal", "RSI",
            "EMA Fast", "EMA Slow",
            "ML Prob", "Reason"
        ])

        dock.setWidget(self.debug_table)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _handle_strategy_debug(self, debug):
        if self._ui_shutting_down:
            return

        if debug is None:
            print("DEBUG IS NONE")
            return

        row = self.debug_table.rowCount()
        self.debug_table.insertRow(row)

        self.debug_table.setItem(row, 0, QTableWidgetItem(str(debug["index"])))
        self.debug_table.setItem(row, 1, QTableWidgetItem(debug["signal"]))
        self.debug_table.setItem(row, 2, QTableWidgetItem(str(debug["rsi"])))
        self.debug_table.setItem(row, 3, QTableWidgetItem(str(debug["ema_fast"])))
        self.debug_table.setItem(row, 4, QTableWidgetItem(str(debug["ema_slow"])))
        self.debug_table.setItem(row, 5, QTableWidgetItem(str(debug["ml_probability"])))
        self.debug_table.setItem(row, 6, QTableWidgetItem(debug["reason"]))

        # Add to chart
        for chart in self._iter_chart_widgets():
            if chart.symbol == debug["symbol"]:
                chart.add_strategy_signal(
                    debug["index"],
                    debug.get("price", debug["ema_fast"]),
                    debug["signal"]
                )

    def _update_training_status(self, symbol, status):

        for row in range(self.symbols_table.rowCount()):
            if self.symbols_table.item(row, 0).text() == symbol:

                if status == "training":
                    item = QTableWidgetItem("⏳ Training...")
                    item.setForeground(QColor("yellow"))
                    icon = self._spinner_frames[self._spinner_index % 2]
                    self._spinner_index += 1

                    item = QTableWidgetItem(f"{icon} Training...")
                    item.setForeground(QColor("yellow"))

                elif status == "ready":
                    item = QTableWidgetItem("🟢 Ready")
                    item.setForeground(QColor("yellow"))

                elif status == "error":
                    item = QTableWidgetItem("🔴 Error")
                    item.setForeground(QColor("red"))
                else:
                    item = QTableWidgetItem(status)

                self.symbols_table.setItem(row, 3, item)
                break

    def _rotate_spinner(self):

     try:

        # Lightweight spinner update: only touch existing rows that are in training state.
        if not hasattr(self, "symbols_table") or self.symbols_table is None:
            return

        self._spinner_index += 1
        icon = self._spinner_frames[self._spinner_index % len(self._spinner_frames)]

        rows = self.symbols_table.rowCount()

        for row in range(rows):
            status_item = self.symbols_table.item(row, 3)

            if not status_item:
                continue

            text = status_item.text() or ""

            if "Training" in text or "?" in text or "?" in text:
                status_item.setText(f"{icon} Training...")
                status_item.setForeground(QColor("yellow"))

     except Exception as e:

        self.logger.error(e)

    def _connect_signals(self):

        self.controller.candle_signal.connect(self._update_chart)
        self.controller.equity_signal.connect(self._update_equity)
        self.controller.trade_signal.connect(self._update_trade_log)
        self.controller.ticker_signal.connect(self._update_ticker)

        self.controller.orderbook_signal.connect(
            self._update_orderbook
        )

        if hasattr(self.controller, "ai_signal_monitor"):
            self.controller.ai_signal_monitor.connect(self._update_ai_signal)

        self.controller.strategy_debug_signal.connect(self._handle_strategy_debug)

        self.controller.training_status_signal.connect(
            self._update_training_status
        )

    def _setup_panels(self):

        self.system_console = SystemConsole()

        console_dock = QDockWidget("System Console", self)
        console_dock.setWidget(self.system_console)

        self.addDockWidget(
            Qt.BottomDockWidgetArea,
            console_dock
        )

        self._create_market_watch_panel()
        self._create_orderbook_panel()
        self._create_positions_panel()
        self._create_trade_log_panel()
        self._create_equity_panel()
        self._create_performance_panel()
        self._create_strategy_comparison()
        self._create_strategy_debug_panel()
        self._create_system_status_panel()
        self._create_risk_heatmap()
        self._create_ai_signal_panel()

    def _current_chart_symbol(self):
        chart = self._current_chart_widget()
        if chart is not None:
            return chart.symbol
        return getattr(self, "symbol", None)

    def _request_active_orderbook(self):
        if self._ui_shutting_down:
            return

        symbol = self._current_chart_symbol()
        if not symbol or not hasattr(self.controller, "request_orderbook"):
            return

        asyncio.get_event_loop().create_task(
            self.controller.request_orderbook(symbol=symbol, limit=20)
        )

    def _setup_spinner(self):

        self._spinner_frames = ["⏳", "⌛"]
        self._spinner_index = 0

        self.spinner_timer = QTimer()
        self.spinner_timer.timeout.connect(self._rotate_spinner)

        self.spinner_timer.start(500)

    def _update_symbols(self, exchange, symbols):

        self.symbols_table.setRowCount(0)
        self.symbols_table.setAccessibleName(exchange)
        if self.symbol_picker is not None:
            current_symbol = self.symbol_picker.currentText()
            self.symbol_picker.blockSignals(True)
            self.symbol_picker.clear()
            self.symbol_picker.addItems(symbols)
            if current_symbol in symbols:
                self.symbol_picker.setCurrentText(current_symbol)
            elif symbols:
                self.symbol_picker.setCurrentIndex(0)
            self.symbol_picker.blockSignals(False)

        for symbol in symbols:
            row = self.symbols_table.rowCount()
            self.symbols_table.insertRow(row)

            self.symbols_table.setItem(row, 0, QTableWidgetItem(symbol))
            self.symbols_table.setItem(row, 1, QTableWidgetItem("-"))
            self.symbols_table.setItem(row, 2, QTableWidgetItem("-"))
            self.symbols_table.setItem(row, 3, QTableWidgetItem("⏳"))

    def _open_manual_trade(self):
        pass

    def _optimize_strategy(self):
        self._open_text_window(
            "strategy_optimization",
            "Strategy Optimization",
            """
            <h2>Strategy Optimization</h2>
            <p>This workspace is reserved for parameter sweeps and strategy comparison.</p>
            <p>Current chart timeframe: <b>{}</b></p>
            <p>Loaded symbols: <b>{}</b></p>
            <p>Optimization controls can be added here next without changing the main terminal layout.</p>
            """.format(self.current_timeframe, len(getattr(self.controller, "symbols", []))),
            width=680,
            height=420,
        )

    def _get_or_create_tool_window(self, key, title, width=900, height=560):
        window = self.detached_tool_windows.get(key)

        if window is not None:
            window.showNormal()
            window.raise_()
            window.activateWindow()
            return window

        window = QMainWindow(self)
        window.setWindowFlag(Qt.WindowType.Window, True)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.setWindowTitle(title)
        window.resize(width, height)
        window.destroyed.connect(
            lambda *_: self.detached_tool_windows.pop(key, None)
        )

        self.detached_tool_windows[key] = window
        return window

    def _clone_table_widget(self, source, target):
        target.clear()
        target.setColumnCount(source.columnCount())
        target.setRowCount(source.rowCount())

        headers = []
        for col in range(source.columnCount()):
            header_item = source.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else f"Column {col + 1}")
        target.setHorizontalHeaderLabels(headers)

        for row in range(source.rowCount()):
            for col in range(source.columnCount()):
                source_item = source.item(row, col)
                if source_item is None:
                    continue
                target.setItem(row, col, source_item.clone())

        target.resizeColumnsToContents()
        target.horizontalHeader().setStretchLastSection(True)

    def _sync_logs_window(self, editor):
        source_text = self.system_console.console.toPlainText()
        if editor.toPlainText() == source_text:
            return

        editor.setPlainText(source_text)
        editor.moveCursor(QTextCursor.MoveOperation.End)

    def _open_logs(self):
        window = self._get_or_create_tool_window(
            "system_logs",
            "System Logs",
            width=980,
            height=620,
        )

        editor = getattr(window, "_logs_editor", None)
        if editor is None:
            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setStyleSheet(self.system_console.console.styleSheet())
            window.setCentralWidget(editor)
            window._logs_editor = editor

            sync_timer = QTimer(window)
            sync_timer.timeout.connect(lambda: self._sync_logs_window(editor))
            sync_timer.start(700)
            window._sync_timer = sync_timer

        self._sync_logs_window(editor)
        window.show()
        window.raise_()
        window.activateWindow()

    def _open_ml_monitor(self):
        window = self._get_or_create_tool_window(
            "ml_monitor",
            "ML Signal Monitor",
            width=880,
            height=520,
        )

        table = getattr(window, "_monitor_table", None)
        if table is None:
            table = QTableWidget()
            table.setAlternatingRowColors(True)
            window.setCentralWidget(table)
            window._monitor_table = table

            sync_timer = QTimer(window)
            sync_timer.timeout.connect(
                lambda: self._clone_table_widget(self.ai_table, table)
            )
            sync_timer.start(900)
            window._sync_timer = sync_timer

        self._clone_table_widget(self.ai_table, table)
        window.show()
        window.raise_()
        window.activateWindow()

    def _open_text_window(self, key, title, html, width=760, height=520):
        window = self._get_or_create_tool_window(key, title, width=width, height=height)

        browser = getattr(window, "_browser", None)
        if browser is None:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setStyleSheet(
                "QTextBrowser { background-color: #0b1220; color: #e6edf7; padding: 16px; }"
            )
            window.setCentralWidget(browser)
            window._browser = browser

        browser.setHtml(html)
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def _format_backtest_timestamp(self, value):
        if value in (None, ""):
            return "-"

        try:
            numeric = float(value)
            if numeric > 1e12:
                numeric /= 1000.0
            return QDateTime.fromSecsSinceEpoch(int(numeric)).toString("yyyy-MM-dd HH:mm")
        except Exception:
            return str(value)

    def _format_backtest_range(self, dataset):
        if dataset is None or not hasattr(dataset, "__len__") or len(dataset) == 0:
            return "-"

        try:
            start_value = dataset.iloc[0]["timestamp"]
            end_value = dataset.iloc[-1]["timestamp"]
        except Exception:
            try:
                start_value = dataset[0][0]
                end_value = dataset[-1][0]
            except Exception:
                return "-"

        return f"{self._format_backtest_timestamp(start_value)} -> {self._format_backtest_timestamp(end_value)}"

    def _append_backtest_journal(self, message, level="INFO"):
        lines = list(getattr(self, "_backtest_journal_lines", []) or [])
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        lines.append(f"[{timestamp}] {level.upper()}: {message}")
        self._backtest_journal_lines = lines[-300:]
        self._refresh_backtest_window()

    def _populate_backtest_results_table(self, table, trades_df):
        headers = ["Time", "Symbol", "Side", "Type", "Price", "Amount", "PnL", "Equity", "Reason"]
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        if trades_df is None or getattr(trades_df, "empty", True):
            table.setRowCount(0)
            return

        table.setRowCount(len(trades_df))

        for row_index, (_idx, row) in enumerate(trades_df.iterrows()):
            values = [
                self._format_backtest_timestamp(row.get("timestamp")),
                row.get("symbol", "-"),
                row.get("side", "-"),
                row.get("type", "-"),
                f"{float(row.get('price', 0) or 0):.6f}",
                f"{float(row.get('amount', 0) or 0):.6f}",
                f"{float(row.get('pnl', 0) or 0):.2f}",
                f"{float(row.get('equity', 0) or 0):.2f}",
                row.get("reason", ""),
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

    def _build_backtest_report_text(self, context, report, trades_df):
        symbol = context.get("symbol", "-")
        timeframe = context.get("timeframe", "-")
        strategy_name = context.get("strategy_name") or getattr(getattr(self.controller, "config", None), "strategy", "Default")
        candle_count = len(context.get("data")) if hasattr(context.get("data"), "__len__") else 0
        initial_deposit = float(getattr(self.controller, "initial_capital", 10000) or 10000)
        spread_pct = float(getattr(self.controller, "spread_pct", 0.0) or 0.0)
        equity_curve = getattr(getattr(self, "backtest_engine", None), "equity_curve", []) or []

        report = report or {}
        total_profit = float(report.get("total_profit", 0.0) or 0.0)
        total_trades = int(report.get("total_trades", 0) or 0)
        closed_trades = int(report.get("closed_trades", 0) or 0)
        win_rate = float(report.get("win_rate", 0.0) or 0.0) * 100.0
        avg_profit = float(report.get("avg_profit", 0.0) or 0.0)
        max_drawdown = float(report.get("max_drawdown", 0.0) or 0.0)
        final_equity = float(report.get("final_equity", initial_deposit) or initial_deposit)

        gross_profit = 0.0
        gross_loss = 0.0
        if trades_df is not None and not getattr(trades_df, "empty", True) and "pnl" in trades_df:
            pnl_series = trades_df["pnl"].fillna(0).astype(float)
            gross_profit = float(pnl_series[pnl_series > 0].sum())
            gross_loss = float(pnl_series[pnl_series < 0].sum())

        profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else (gross_profit if gross_profit > 0 else 0.0)
        bars = len(equity_curve) if equity_curve else candle_count

        lines = [
            "Strategy Tester Report",
            "",
            f"Expert: {strategy_name}",
            f"Symbol: {symbol}",
            f"Period: {timeframe}",
            "Model: Bar-close simulation",
            f"Spread: {spread_pct:.4f}%",
            f"Initial Deposit: {initial_deposit:.2f}",
            f"Bars in Test: {bars}",
            f"Range: {self._format_backtest_range(context.get('data'))}",
            "",
            f"Total Net Profit: {total_profit:.2f}",
            f"Gross Profit: {gross_profit:.2f}",
            f"Gross Loss: {gross_loss:.2f}",
            f"Profit Factor: {profit_factor:.2f}",
            f"Expected Payoff: {avg_profit:.2f}",
            f"Max Drawdown: {max_drawdown:.2f}",
            f"Total Trades: {total_trades}",
            f"Closed Trades: {closed_trades}",
            f"Win Rate: {win_rate:.2f}%",
            f"Final Equity: {final_equity:.2f}",
        ]
        return "\n".join(lines)

    def _show_backtest_window(self):
        window = self._get_or_create_tool_window(
            "backtesting_workspace",
            "Strategy Tester",
            width=1180,
            height=760,
        )

        if getattr(window, "_backtest_container", None) is None:
            container = QWidget()
            layout = QVBoxLayout(container)

            status = QLabel("Strategy tester ready.")
            status.setStyleSheet("color: #e6edf7; font-weight: 700; font-size: 14px;")
            layout.addWidget(status)

            summary = QLabel("-")
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #9fb0c7;")
            layout.addWidget(summary)

            settings_frame = QFrame()
            settings_frame.setStyleSheet(
                "QFrame { background-color: #101b2d; border: 1px solid #24344f; border-radius: 10px; }"
                "QLabel { color: #d7dfeb; }"
            )
            settings_layout = QGridLayout(settings_frame)
            settings_layout.setContentsMargins(14, 12, 14, 12)
            settings_layout.setHorizontalSpacing(16)
            settings_layout.setVerticalSpacing(8)

            setting_names = [
                "Expert",
                "Symbol",
                "Period",
                "Model",
                "Spread",
                "Initial Deposit",
                "Bars",
                "Range",
            ]
            setting_labels = {}
            for index, name in enumerate(setting_names):
                title = QLabel(name)
                title.setStyleSheet("color: #8fa3bf; font-weight: 700;")
                value = QLabel("-")
                value.setStyleSheet("color: #f4f8ff; font-weight: 600;")
                row = index // 4
                col = (index % 4) * 2
                settings_layout.addWidget(title, row, col)
                settings_layout.addWidget(value, row, col + 1)
                setting_labels[name] = value
            layout.addWidget(settings_frame)

            controls = QHBoxLayout()
            start_btn = QPushButton("Start Backtest")
            stop_btn = QPushButton("Stop Backtest")
            report_btn = QPushButton("Generate Report")
            start_btn.clicked.connect(self.start_backtest)
            stop_btn.clicked.connect(self.stop_backtest)
            report_btn.clicked.connect(self._generate_report)
            controls.addWidget(start_btn)
            controls.addWidget(stop_btn)
            controls.addWidget(report_btn)
            controls.addStretch()
            layout.addLayout(controls)

            metrics_frame = QFrame()
            metrics_frame.setStyleSheet(
                "QFrame { background-color: #0f1727; border: 1px solid #24344f; border-radius: 10px; }"
            )
            metrics_layout = QGridLayout(metrics_frame)
            metrics_layout.setContentsMargins(12, 10, 12, 10)
            metrics_layout.setHorizontalSpacing(18)
            metrics_layout.setVerticalSpacing(6)

            metric_names = [
                "Total Net Profit",
                "Trades",
                "Win Rate",
                "Max Drawdown",
                "Final Equity",
            ]
            metric_labels = {}
            for index, name in enumerate(metric_names):
                title = QLabel(name)
                title.setStyleSheet("color: #8fa3bf; font-weight: 700;")
                value = QLabel("-")
                value.setStyleSheet("color: #f5fbff; font-weight: 700; font-size: 16px;")
                metrics_layout.addWidget(title, 0, index)
                metrics_layout.addWidget(value, 1, index)
                metric_labels[name] = value
            layout.addWidget(metrics_frame)

            tabs = QTabWidget()

            results_table = QTableWidget()
            results_table.setAlternatingRowColors(True)
            tabs.addTab(results_table, "Results")

            graph_tab = QWidget()
            graph_layout = QVBoxLayout(graph_tab)
            graph_layout.setContentsMargins(8, 8, 8, 8)
            graph_plot = pg.PlotWidget()
            graph_plot.setBackground("#0b1220")
            graph_plot.showGrid(x=True, y=True, alpha=0.2)
            graph_plot.setLabel("left", "Equity")
            graph_plot.setLabel("bottom", "Bar")
            graph_curve = graph_plot.plot(pen=pg.mkPen("#2a7fff", width=2))
            graph_layout.addWidget(graph_plot)
            tabs.addTab(graph_tab, "Graph")

            report_text = QTextEdit()
            report_text.setReadOnly(True)
            report_text.setStyleSheet(
                "QTextEdit { background-color: #0b1220; color: #d7dfeb; font-family: Consolas; }"
            )
            tabs.addTab(report_text, "Report")

            journal_text = QTextEdit()
            journal_text.setReadOnly(True)
            journal_text.setStyleSheet(
                "QTextEdit { background-color: #0b1220; color: #d7dfeb; font-family: Consolas; }"
            )
            tabs.addTab(journal_text, "Journal")

            layout.addWidget(tabs)

            window.setCentralWidget(container)
            window._backtest_container = container
            window._backtest_status = status
            window._backtest_summary = summary
            window._backtest_setting_labels = setting_labels
            window._backtest_metric_labels = metric_labels
            window._backtest_tabs = tabs
            window._backtest_results = results_table
            window._backtest_graph_curve = graph_curve
            window._backtest_report = report_text
            window._backtest_journal = journal_text

        self._refresh_backtest_window(window)
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def _refresh_backtest_window(self, window=None, message=None):
        window = window or self.detached_tool_windows.get("backtesting_workspace")
        if window is None:
            return

        status = getattr(window, "_backtest_status", None)
        summary = getattr(window, "_backtest_summary", None)
        results = getattr(window, "_backtest_results", None)
        settings = getattr(window, "_backtest_setting_labels", None)
        metrics = getattr(window, "_backtest_metric_labels", None)
        graph_curve = getattr(window, "_backtest_graph_curve", None)
        report_view = getattr(window, "_backtest_report", None)
        journal_view = getattr(window, "_backtest_journal", None)
        if (
            status is None
            or summary is None
            or results is None
            or settings is None
            or metrics is None
            or graph_curve is None
            or report_view is None
            or journal_view is None
        ):
            return

        backtest_context = getattr(self, "_backtest_context", {}) or {}
        dataset = backtest_context.get("data")
        candle_count = len(dataset) if hasattr(dataset, "__len__") else 0
        has_engine = hasattr(self, "backtest_engine")
        symbol = backtest_context.get("symbol", "-")
        timeframe = backtest_context.get("timeframe", "-")
        strategy_name = backtest_context.get("strategy_name") or getattr(getattr(self.controller, "config", None), "strategy", "Default")
        spread_pct = float(getattr(self.controller, "spread_pct", 0.0) or 0.0)
        initial_deposit = float(getattr(self.controller, "initial_capital", 10000) or 10000)
        range_text = self._format_backtest_range(dataset)

        status.setText(message or ("Strategy tester ready." if has_engine else "Backtest engine not initialized."))
        summary.setText(
            f"Expert: {strategy_name} | Symbol: {symbol} | Period: {timeframe} | Bars: {candle_count}"
        )

        settings["Expert"].setText(str(strategy_name))
        settings["Symbol"].setText(str(symbol))
        settings["Period"].setText(str(timeframe))
        settings["Model"].setText("Bar-close simulation")
        settings["Spread"].setText(f"{spread_pct:.4f}%")
        settings["Initial Deposit"].setText(f"{initial_deposit:.2f}")
        settings["Bars"].setText(str(candle_count))
        settings["Range"].setText(range_text)

        results_df = getattr(self, "results", None)
        report = getattr(self, "backtest_report", None)
        equity_curve = getattr(getattr(self, "backtest_engine", None), "equity_curve", []) or []

        if results_df is None:
            self._populate_backtest_results_table(results, None)
            graph_curve.setData([])
            metrics["Total Net Profit"].setText("-")
            metrics["Trades"].setText("-")
            metrics["Win Rate"].setText("-")
            metrics["Max Drawdown"].setText("-")
            metrics["Final Equity"].setText("-")
            report_view.setPlainText("No backtest results yet.")
            journal_view.setPlainText("\n".join(getattr(self, "_backtest_journal_lines", []) or []))
            journal_view.moveCursor(QTextCursor.MoveOperation.End)
            return

        try:
            self._populate_backtest_results_table(results, results_df)

            if not isinstance(report, dict):
                report = ReportGenerator(
                    trades=results_df,
                    equity_history=equity_curve,
                ).generate()

            metrics["Total Net Profit"].setText(f"{float(report.get('total_profit', 0.0) or 0.0):.2f}")
            metrics["Trades"].setText(str(int(report.get("total_trades", 0) or 0)))
            metrics["Win Rate"].setText(f"{float(report.get('win_rate', 0.0) or 0.0) * 100.0:.2f}%")
            metrics["Max Drawdown"].setText(f"{float(report.get('max_drawdown', 0.0) or 0.0):.2f}")
            metrics["Final Equity"].setText(f"{float(report.get('final_equity', initial_deposit) or initial_deposit):.2f}")

            graph_curve.setData(equity_curve)
            report_view.setPlainText(self._build_backtest_report_text(backtest_context, report, results_df))
            journal_view.setPlainText("\n".join(getattr(self, "_backtest_journal_lines", []) or []))
            journal_view.moveCursor(QTextCursor.MoveOperation.End)
        except Exception as exc:
            report_view.setPlainText(f"Unable to render backtest results: {exc}")

    def _show_risk_settings_window(self):
        risk_engine = getattr(self.controller, "risk_engine", None)
        if risk_engine is None:
            QMessageBox.warning(self, "Risk Engine Missing", "Trading/risk engine is not initialized yet.")
            return None

        window = self._get_or_create_tool_window(
            "risk_settings",
            "Risk Settings",
            width=460,
            height=340,
        )

        if getattr(window, "_risk_container", None) is None:
            container = QWidget()
            layout = QVBoxLayout(container)
            form = QFormLayout()

            max_portfolio = QDoubleSpinBox()
            max_portfolio.setRange(0, 1)
            max_portfolio.setSingleStep(0.01)

            max_trade = QDoubleSpinBox()
            max_trade.setRange(0, 1)
            max_trade.setSingleStep(0.01)

            max_position = QDoubleSpinBox()
            max_position.setRange(0, 1)
            max_position.setSingleStep(0.01)

            max_gross = QDoubleSpinBox()
            max_gross.setRange(0, 5)
            max_gross.setSingleStep(0.1)

            form.addRow("Max Portfolio Risk:", max_portfolio)
            form.addRow("Max Risk Per Trade:", max_trade)
            form.addRow("Max Position Size:", max_position)
            form.addRow("Max Gross Exposure:", max_gross)
            layout.addLayout(form)

            status = QLabel("-")
            status.setStyleSheet("color: #9fb0c7;")
            layout.addWidget(status)

            save_btn = QPushButton("Save Risk Settings")
            save_btn.clicked.connect(lambda: self._apply_risk_settings(window))
            layout.addWidget(save_btn)

            window.setCentralWidget(container)
            window._risk_container = container
            window._risk_max_portfolio = max_portfolio
            window._risk_max_trade = max_trade
            window._risk_max_position = max_position
            window._risk_max_gross = max_gross
            window._risk_status = status

        window._risk_max_portfolio.setValue(getattr(risk_engine, "max_portfolio_risk", 0.2))
        window._risk_max_trade.setValue(getattr(risk_engine, "max_risk_per_trade", 0.02))
        window._risk_max_position.setValue(getattr(risk_engine, "max_position_size_pct", 0.05))
        window._risk_max_gross.setValue(getattr(risk_engine, "max_gross_exposure_pct", 1.0))
        window._risk_status.setText("Adjust limits and click Save Risk Settings.")

        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def _apply_risk_settings(self, window):
        try:
            risk_engine = getattr(self.controller, "risk_engine", None)
            if risk_engine is None:
                return

            risk_engine.max_portfolio_risk = window._risk_max_portfolio.value()
            risk_engine.max_risk_per_trade = window._risk_max_trade.value()
            risk_engine.max_position_size_pct = window._risk_max_position.value()
            risk_engine.max_gross_exposure_pct = window._risk_max_gross.value()

            window._risk_status.setText("Risk settings saved.")
            self.system_console.log("Risk settings updated successfully.")
        except Exception as exc:
            self.logger.error(f"Risk settings error: {exc}")

    def _populate_portfolio_exposure_table(self, table):
        positions = []
        portfolio = getattr(self.controller, "portfolio", None)
        if portfolio is None:
            return

        if hasattr(portfolio, "get_positions"):
            try:
                positions = portfolio.get_positions() or []
            except Exception:
                positions = []
        elif hasattr(portfolio, "positions"):
            raw_positions = getattr(portfolio, "positions", {})
            if isinstance(raw_positions, dict):
                positions = list(raw_positions.values())

        table.setRowCount(len(positions))
        total_value = 0.0
        for pos in positions:
            try:
                total_value += float(pos.get("value", 0))
            except Exception:
                continue

        for row, pos in enumerate(positions):
            symbol = pos.get("symbol", "-")
            size = pos.get("size", pos.get("amount", "-"))
            value = float(pos.get("value", 0) or 0)
            pct = (value / total_value * 100) if total_value else 0

            table.setItem(row, 0, QTableWidgetItem(str(symbol)))
            table.setItem(row, 1, QTableWidgetItem(str(size)))
            table.setItem(row, 2, QTableWidgetItem(f"{value:.2f}"))
            table.setItem(row, 3, QTableWidgetItem(f"{pct:.2f}%"))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

    def _show_portfolio_exposure_window(self):
        window = self._get_or_create_tool_window(
            "portfolio_exposure",
            "Portfolio Exposure",
            width=760,
            height=460,
        )

        table = getattr(window, "_exposure_table", None)
        if table is None:
            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(
                ["Symbol", "Size", "Value (USD)", "Portfolio %"]
            )
            window.setCentralWidget(table)
            window._exposure_table = table

            sync_timer = QTimer(window)
            sync_timer.timeout.connect(
                lambda: self._populate_portfolio_exposure_table(table)
            )
            sync_timer.start(1200)
            window._sync_timer = sync_timer

        self._populate_portfolio_exposure_table(table)
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def _show_about(self):
        self._open_text_window(
            "about_window",
            "About Sopotek Trading",
            """
            <h2>Sopotek Trading Platform</h2>
            <p><b>Purpose:</b> AI-assisted multi-broker trading workstation for live trading, paper trading, analytics, and historical testing.</p>
            <p><b>Main capabilities:</b> live charts, AI signal monitoring, orderbook analysis, risk controls, backtesting, strategy optimization, and broker abstraction across crypto, stocks, forex, paper, and Stellar.</p>
            <p><b>Best use:</b> start in paper mode, validate charts and signals, confirm balances and risk limits, then move into live trading only after the setup looks stable.</p>
            <p><b>Core stack:</b> PySide6, pyqtgraph, pandas, technical-analysis indicators, broker adapters, and async market-data pipelines.</p>
            <p><b>Designed for:</b> fast iteration without losing visibility into risk, execution status, or model behavior.</p>
            """,
            width=700,
            height=520,
        )

    def _close_all_positions(self):
        pass

    def _export_trades(self):
        pass

    def _cancel_all_orders(self):
        pass

    def _open_docs(self):
        self._open_text_window(
            "help_documentation",
            "Documentation",
            """
            <h2>Documentation</h2>
            <h3>1. What This App Does</h3>
            <p>Sopotek is a trading workstation that combines broker access, live charting, AI-driven signal monitoring, orderbook views, execution controls, risk settings, historical backtesting, and strategy optimization.</p>

            <h3>2. Quick Start</h3>
            <p><b>Step 1:</b> Open the dashboard and choose a broker type, exchange, mode, strategy, and risk budget.</p>
            <p><b>Step 2:</b> Use paper mode first whenever you are testing a new broker, strategy, or market.</p>
            <p><b>Step 3:</b> Launch the terminal, open a symbol tab from the toolbar, and confirm candles are loading.</p>
            <p><b>Step 4:</b> Review system status, balances, training states, and application settings before turning on AI trading.</p>
            <p><b>Step 5:</b> Use backtesting and optimization before trusting a strategy in live conditions.</p>

            <h3>3. Main Layout</h3>
            <p><b>Toolbar:</b> symbol picker, timeframe controls, AI trading toggle, and chart actions.</p>
            <p><b>Chart tabs:</b> one tab per symbol and timeframe, with candlesticks, indicators, and bid/ask overlays.</p>
            <p><b>Orderbook:</b> bid/ask ladders plus depth view for the active chart symbol.</p>
            <p><b>AI Signal Monitor:</b> latest model decisions, confidence, regime, and volatility readout.</p>
            <p><b>Strategy Debug:</b> indicator values and strategy reasoning for generated signals.</p>
            <p><b>System Status:</b> connection state, websocket state, balances, and session health summary.</p>
            <p><b>Logs:</b> runtime messages, broker responses, and error diagnostics.</p>

            <h3>4. Charts</h3>
            <p>Use the symbol selector in the toolbar to open a new chart tab. If the symbol already exists, the app focuses the existing tab instead of duplicating it.</p>
            <p>Timeframe buttons reload candles for the active tab. Indicators can be added from the <b>Charts</b> menu. Bid and ask dashed price lines can be toggled from <b>Charts -&gt; Show Bid/Ask Lines</b>.</p>
            <p>The candlestick chart is intentionally the largest area and can be resized where splitters are available.</p>

            <h3>5. AI Trading</h3>
            <p>The AI trading button enables the automated worker loop. It does not guarantee that orders will be sent every cycle; signals still pass through broker checks, balance checks, market-status checks, and exchange minimum filters.</p>
            <p>If AI trading is on but no trades occur, check the logs, AI Signal Monitor, Strategy Debug, and account balances first.</p>

            <h3>6. Orders and Safety</h3>
            <p>The execution path checks available balances before sending orders, trims amounts when necessary, and skips symbols on cooldown after exchange rejections such as closed markets, insufficient balance, or minimum notional failures.</p>
            <p>For live sessions, always confirm that you have enough quote currency for buys and enough base currency for sells.</p>

            <h3>7. Backtesting</h3>
            <p>Open a chart that already has candles loaded, then use <b>Backtesting -&gt; Run Backtest</b>. This initializes the backtest with the active chart symbol, timeframe, and strategy context.</p>
            <p>In the backtesting workspace, click <b>Start Backtest</b> to run the historical simulation and <b>Generate Report</b> to export PDF and spreadsheet results.</p>
            <p>If backtesting says no data is available, reload the chart candles first.</p>

            <h3>8. Strategy Optimization</h3>
            <p>Use <b>Backtesting -&gt; Strategy Optimization</b> to run a parameter sweep over core strategy settings such as RSI, EMA fast, EMA slow, and ATR periods.</p>
            <p>The optimization table ranks results by performance metrics. Use <b>Apply Best Params</b> to push the top result into the active strategy object.</p>
            <p>Optimization depends on historical candle data being available for the active chart.</p>

            <h3>9. Settings and Risk Controls</h3>
            <p>The <b>Settings</b> menu is the main configuration area for trading defaults, chart behavior, refresh intervals, backtesting capital, and all risk limits.</p>
            <p>Portfolio exposure is also available from <b>Settings</b> so you can keep configuration and risk context in one place.</p>

            <h3>10. Tools Windows</h3>
            <p>The <b>Tools</b> menu opens detached utility windows so you can keep charts large while monitoring logs, AI signals, and performance analytics in parallel.</p>

            <h3>11. Supported Broker Concepts</h3>
            <p><b>Crypto:</b> CCXT-compatible exchanges and Stellar.</p>
            <p><b>Forex:</b> Oanda.</p>
            <p><b>Stocks:</b> Alpaca.</p>
            <p><b>Paper:</b> local simulated execution path.</p>

            <h3>12. Stellar Notes</h3>
            <p>For Stellar, use the public key in the dashboard API field and the secret seed in the secret field. Market data currently uses polling via Horizon rather than websocket streaming.</p>
            <p>Non-native assets may require issuer-aware configuration if the code is ambiguous.</p>

            <h3>13. Troubleshooting</h3>
            <p><b>No candles:</b> confirm the symbol exists on the broker and try changing timeframe.</p>
            <p><b>No orderbook:</b> open a chart tab first and wait for the orderbook refresh timer to update the active symbol.</p>
            <p><b>No AI signals:</b> verify that the strategy can compute features from the loaded candles and that AI trading is enabled when required.</p>
            <p><b>Orders rejected:</b> check exchange minimums, market status, insufficient balance, and broker-specific rules in the logs.</p>
            <p><b>Backtest/optimization blank:</b> make sure the active chart already has historical data loaded.</p>

            <h3>14. Recommended Workflow</h3>
            <p>Use this order: dashboard setup -> paper session -> verify charts and signals -> run backtest -> run optimization -> confirm application and risk settings -> move to live trading.</p>

            <h3>15. Where To Look Next</h3>
            <p>For broker-specific and integration-level details, open <b>Help -&gt; API Reference</b>.</p>
            """,
            width=940,
            height=760,
        )

    def _open_api_docs(self):
        self._open_text_window(
            "api_reference",
            "API Reference",
            """
            <h2>API Reference</h2>
            <h3>Broker Layer</h3>
            <p>The app uses a normalized broker interface so the terminal can work across multiple providers with the same core methods.</p>
            <p><b>Common market-data methods:</b> fetch_ticker, fetch_orderbook, fetch_ohlcv, fetch_trades, fetch_symbols, fetch_markets, fetch_status.</p>
            <p><b>Common trading methods:</b> create_order, cancel_order, cancel_all_orders.</p>
            <p><b>Common account methods:</b> fetch_balance, fetch_positions, fetch_orders, fetch_open_orders, fetch_closed_orders, fetch_order.</p>

            <h3>Broker Types in This App</h3>
            <p><b>CCXTBroker:</b> crypto exchanges using the CCXT unified API.</p>
            <p><b>OandaBroker:</b> forex account and market access.</p>
            <p><b>AlpacaBroker:</b> stock and equity trading access.</p>
            <p><b>PaperBroker:</b> local simulation for testing flows safely.</p>
            <p><b>StellarBroker:</b> Horizon-backed Stellar market data, balances, offers, and signed offer submission.</p>

            <h3>Configuration Fields</h3>
            <p><b>type:</b> crypto, forex, stocks, or paper.</p>
            <p><b>exchange:</b> provider name such as binanceus, coinbase, oanda, alpaca, paper, or stellar.</p>
            <p><b>mode:</b> live or paper.</p>
            <p><b>api_key / secret:</b> broker credentials. For Stellar this maps to public key and secret seed.</p>
            <p><b>account_id:</b> required for Oanda.</p>
            <p><b>password / passphrase:</b> required on some exchanges.</p>
            <p><b>sandbox:</b> enables testnet or practice behavior where supported.</p>
            <p><b>options / params:</b> broker-specific advanced settings.</p>

            <h3>Execution Notes</h3>
            <p>Execution passes through a router and execution manager. Before orders are sent, the app checks balances, market state, minimums, and cooldown status.</p>
            <p>Exchange-specific rejections are logged and may place the symbol on cooldown to reduce error spam.</p>

            <h3>Backtesting and Optimization Internals</h3>
            <p><b>BacktestEngine:</b> replays candle windows through the active strategy and simulator.</p>
            <p><b>Simulator:</b> executes simplified buy/sell flows for historical testing.</p>
            <p><b>ReportGenerator:</b> creates summary metrics plus PDF/spreadsheet exports.</p>
            <p><b>StrategyOptimizer:</b> runs parameter sweeps and ranks results by performance.</p>

            <h3>Live Data Notes</h3>
            <p>Some brokers use websocket market data; others fall back to polling. Stellar currently uses polling via Horizon.</p>

            <h3>External References</h3>
            <p><a href="https://docs.ccxt.com">CCXT Documentation</a></p>
            <p><a href="https://github.com/ccxt/ccxt/wiki/manual">CCXT Manual</a></p>
            <p><a href="https://developers.stellar.org/docs/data/apis/horizon/api-reference">Stellar Horizon API Reference</a></p>
            <p><a href="https://stellar-sdk.readthedocs.io/en/latest/index.html">stellar-sdk Python Documentation</a></p>
            <p><a href="https://alpaca.markets/docs/">Alpaca API Docs</a></p>
            <p><a href="https://developer.oanda.com/rest-live-v20/introduction/">Oanda v20 API Docs</a></p>
            """,
            width=900,
            height=720,
        )

    def _multi_chart_layout(self):

        try:

            # Create container widget
            container = QWidget(self)

            # Grid layout
            layout = QGridLayout(container)

            # Example symbols (or take from controller)
            symbols = self.controller.symbols[:4]

            # Create 2x2 grid of charts
            positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

            for symbol, position in zip(symbols, positions):
                chart = ChartWidget(
                    symbol,
                    self.current_timeframe,
                    self.controller,
                    candle_up_color=self.candle_up_color,
                    candle_down_color=self.candle_down_color,
                )

                layout.addWidget(chart, *position)

            container.setLayout(layout)

            # Set as central widget
            self.setCentralWidget(container)

        except Exception as e:

            self.logger.error(f"Multi chart layout error: {e}")

    def _open_performance(self):
        window = self._get_or_create_tool_window(
            "performance_analytics",
            "Performance Analytics",
            width=980,
            height=640,
        )

        if getattr(window, "_performance_container", None) is None:
            container = QWidget()
            layout = QVBoxLayout(container)

            stats_grid = QGridLayout()
            stats_grid.setHorizontalSpacing(16)
            stats_grid.setVerticalSpacing(8)

            metric_names = [
                "Equity",
                "Samples",
                "Trades",
                "Cumulative Return",
                "Volatility",
                "Sharpe Ratio",
                "Sortino Ratio",
                "Max Drawdown",
            ]

            metric_labels = {}
            for index, name in enumerate(metric_names):
                title = QLabel(name)
                title.setStyleSheet("color: #8fa3bf; font-weight: 700;")
                value = QLabel("-")
                value.setStyleSheet("color: #e6edf7; font-weight: 600;")
                stats_grid.addWidget(title, index // 2, (index % 2) * 2)
                stats_grid.addWidget(value, index // 2, (index % 2) * 2 + 1)
                metric_labels[name] = value

            layout.addLayout(stats_grid)

            plot = pg.PlotWidget()
            plot.setBackground("#0b1220")
            plot.showGrid(x=True, y=True, alpha=0.2)
            curve = plot.plot(pen=pg.mkPen("#2a7fff", width=2))
            layout.addWidget(plot)

            window.setCentralWidget(container)
            window._performance_container = container
            window._performance_labels = metric_labels
            window._performance_curve = curve

            sync_timer = QTimer(window)
            sync_timer.timeout.connect(lambda: self._refresh_performance_window(window))
            sync_timer.start(1000)
            window._sync_timer = sync_timer

        self._refresh_performance_window(window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _performance_series(self):
        perf = getattr(self.controller, "performance_engine", None)
        if perf is None:
            return []

        for attr in ("equity_history", "equity_curve"):
            series = getattr(perf, attr, None)
            if isinstance(series, list):
                return series

        return []

    def _format_performance_value(self, value, percent=False):
        if value is None:
            return "-"

        try:
            numeric = float(value)
        except Exception:
            return str(value)

        if percent:
            return f"{numeric * 100:.2f}%"
        return f"{numeric:.4f}"

    def _refresh_performance_window(self, window):
        labels = getattr(window, "_performance_labels", None)
        curve = getattr(window, "_performance_curve", None)
        if labels is None or curve is None:
            return

        equity_series = self._performance_series()
        perf = getattr(self.controller, "performance_engine", None)

        report = {}
        if perf is not None and hasattr(perf, "report"):
            try:
                report = perf.report() or {}
            except Exception:
                report = {}

        latest_equity = equity_series[-1] if equity_series else 0.0
        labels["Equity"].setText(self._format_performance_value(latest_equity))
        labels["Samples"].setText(str(len(equity_series)))
        labels["Trades"].setText(str(self.trade_log.rowCount()))
        labels["Cumulative Return"].setText(
            self._format_performance_value(report.get("cumulative_return"), percent=True)
        )
        labels["Volatility"].setText(
            self._format_performance_value(report.get("volatility"), percent=True)
        )
        labels["Sharpe Ratio"].setText(
            self._format_performance_value(report.get("sharpe_ratio"))
        )
        labels["Sortino Ratio"].setText(
            self._format_performance_value(report.get("sortino_ratio"))
        )
        labels["Max Drawdown"].setText(
            self._format_performance_value(report.get("max_drawdown"), percent=True)
        )

        curve.setData(equity_series)

    def _open_risk_settings(self):
        self._show_risk_settings_window()

    def save_settings(self):
        dialog = QDialog(self)
        save_btn = QPushButton("Save")
        layout = QVBoxLayout()
        max_portfolio_risk = QDoubleSpinBox()
        max_portfolio_risk.setRange(0, 1)
        max_portfolio_risk.setSingleStep(0.01)
        max_risk_per_trade = QDoubleSpinBox()
        max_risk_per_trade.setRange(0, 5)
        max_risk_per_trade.setSingleStep(0.01)
        max_position_size = QDoubleSpinBox()
        max_position_size.setRange(0, 5)
        max_position_size.setSingleStep(0.01)
        max_gross_exposure = QDoubleSpinBox()
        max_gross_exposure.setRange(0, 5)
        max_gross_exposure.setSingleStep(0.01)

        try:

            self.controller.risk_engine.max_portfolio_risk = max_portfolio_risk.value()
            self.controller.risk_engine.max_risk_per_trade = max_risk_per_trade.value()
            self.controller.risk_engine.max_position_size_pct = max_position_size.value()
            self.controller.risk_engine.max_gross_exposure_pct = max_gross_exposure.value()

            QMessageBox.information(
                dialog,
                "Risk Settings",
                "Risk settings updated successfully."
            )

            dialog.close()

        except Exception as e:

            self.logger.error(f"Risk settings error: {e}")

        save_btn.clicked.connect(self.save_settings)

        layout.addWidget(save_btn)

        dialog.setLayout(layout)

        dialog.exec()

    def _show_portfolio_exposure(self):
        try:
            self._show_portfolio_exposure_window()
        except Exception as e:
            self.logger.error(f"Portfolio exposure error: {e}")

    async def _reload_chart_data(self, symbol, timeframe):

        try:

            buffers = self.controller.candle_buffers.get(symbol)

            if not buffers:
                return

            df = buffers.get(timeframe)

            if df is None:
                return

            self._update_chart(symbol, df)

        except Exception as e:

            self.logger.error(f"Timeframe reload failed: {e}")



    def _format_balance_text(self, balance):
        """Render balances like: XLM:100, USDT:100."""
        if not isinstance(balance, dict) or not balance:
            return "-"

        # Common CCXT shape: {"free": {...}, "used": {...}, "total": {...}}
        if isinstance(balance.get("total"), dict):
            source = balance.get("total") or {}
        elif isinstance(balance.get("free"), dict):
            source = balance.get("free") or {}
        else:
            # Flat dict fallback; skip known non-asset keys
            skip = {"free", "used", "total", "info", "raw", "equity", "cash", "currency"}
            source = {k: v for k, v in balance.items() if k not in skip}

        parts = []
        for sym, val in source.items():
            try:
                num = float(val)
            except Exception:
                continue
            if num == 0:
                continue
            parts.append(f"{sym}:{num:g}")

        if not parts:
            return "-"

        parts.sort()
        return ", ".join(parts)

    def _compact_balance_text(self, balance, max_items=4):
        full_text = self._format_balance_text(balance)
        if full_text == "-":
            return "-", "-"

        parts = [part.strip() for part in full_text.split(",") if part.strip()]
        compact = ", ".join(parts[:max_items])
        if len(parts) > max_items:
            compact = f"{compact} +{len(parts) - max_items} more"

        return compact, full_text

    def _elide_text(self, value, max_length=42):
        text = str(value)
        if len(text) <= max_length:
            return text
        return f"{text[: max_length - 1]}..."

    def _set_status_value(self, field, value, tooltip=None):
        label = self.status_labels.get(field)
        if label is None:
            return

        display = self._elide_text(value)
        label.setText(display)
        label.setToolTip(tooltip or str(value))

    def _refresh_terminal(self):

        try:

            controller = self.controller

            equity = getattr(controller.portfolio, "get_equity", lambda: 0)()
            balance = getattr(controller, "balances", {})
            spread = getattr(controller, "spread_pct", 0)
            positions = getattr(controller.portfolio, "positions", {})
            symbols = getattr(controller, "symbols", [])
            exchange = getattr(controller.broker, "exchange_name", "Unknown")

            free = balance.get("free", 0) if isinstance(balance, dict) else 0
            used = balance.get("used", 0) if isinstance(balance, dict) else 0

            balance_summary, balance_tooltip = self._compact_balance_text(balance)
            free_summary, free_tooltip = self._compact_balance_text(
                free if isinstance(free, dict) else {"USDT": free}
            )
            used_summary, used_tooltip = self._compact_balance_text(
                used if isinstance(used, dict) else {"USDT": used}
            )

            self._set_status_value("Exchange", exchange)

            self._set_status_value("Symbols Loaded", len(symbols))

            self._set_status_value("Equity", f"{equity:.4f}")

            self._set_status_value("Balance", balance_summary, balance_tooltip)

            self._set_status_value("Free Margin", free_summary, free_tooltip)

            self._set_status_value("Used Margin", used_summary, used_tooltip)

            self._set_status_value("Spread %", f"{spread:.4f}")

            self._set_status_value("Open Positions", len(positions))

            market_stream_status = "Stopped"
            if hasattr(controller, "get_market_stream_status"):
                market_stream_status = controller.get_market_stream_status()

            self._set_status_value("Websocket", market_stream_status)

            self._set_status_value("AITrading", "ON" if self.autotrading_enabled else "OFF")

            self._set_status_value("Timeframe", self.current_timeframe)

            self._update_risk_heatmap()

        except Exception as e:

            self.logger.error(e)


    def _refresh_markets(self):

        self.symbols_table.setRowCount(0)

        for symbol in self.controller.symbols:

            row = self.symbols_table.rowCount()
            self.symbols_table.insertRow(row)

            self.symbols_table.setItem(row, 0, QTableWidgetItem(symbol))
            self.symbols_table.setItem(row, 1, QTableWidgetItem("-"))
            self.symbols_table.setItem(row, 2, QTableWidgetItem("-"))
            self.symbols_table.setItem(row, 3, QTableWidgetItem("⏳"))

    def _create_system_status_panel(self):

        dock = QDockWidget("System Status", self)
        dock.setMinimumWidth(250)
        dock.setMaximumWidth(320)

        container = QWidget()
        layout = QGridLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        self.status_labels = {}

        fields = [
            "Exchange",

            "Symbols Loaded",
            "Equity",
            "Balance",
            "Free Margin",
            "Used Margin",
            "Spread %",
            "Open Positions",
            "Websocket",
            "AITrading",
            "Timeframe"
        ]

        for row, field in enumerate(fields):
            title = QLabel(field)
            title.setStyleSheet("color: #8fa3bf; font-weight: 700;")
            value = QLabel("-")
            value.setWordWrap(True)
            value.setStyleSheet("color: #e6edf7; font-weight: 600;")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            layout.addWidget(title, row, 0)
            layout.addWidget(value, row, 1)

            self.status_labels[field] = value

        container.setLayout(layout)

        dock.setWidget(container)

        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _create_ai_signal_panel(self):

        dock = QDockWidget("AI Signal Monitor", self)

        self.ai_table = QTableWidget()
        self.ai_table.setColumnCount(6)

        self.ai_table.setHorizontalHeaderLabels([
            "Symbol",
            "Signal",
            "Confidence",
            "Regime",
            "Volatility",
            "Time"
        ])

        dock.setWidget(self.ai_table)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _update_ai_signal(self, data):

        row = self.ai_table.rowCount()
        self.ai_table.insertRow(row)

        self.ai_table.setItem(row, 0, QTableWidgetItem(data["symbol"]))
        self.ai_table.setItem(row, 1, QTableWidgetItem(data["signal"]))
        self.ai_table.setItem(row, 2, QTableWidgetItem(f'{data["confidence"]:.2f}'))
        self.ai_table.setItem(row, 3, QTableWidgetItem(data["regime"]))
        self.ai_table.setItem(row, 4, QTableWidgetItem(str(data["volatility"])))
        self.ai_table.setItem(row, 5, QTableWidgetItem(str(data["timestamp"])))

    def _create_regime_panel(self):

        dock = QDockWidget("Market Regime", self)

        container = QWidget()
        layout = QVBoxLayout()

        self.regime_label = QLabel("Regime: UNKNOWN")
        self.regime_label.setStyleSheet("font-size: 18px;")

        layout.addWidget(self.regime_label)

        container.setLayout(layout)

        dock.setWidget(container)

        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _update_regime(self, regime):

        colors = {
            "TREND_UP": "green",
            "TREND_DOWN": "red",
            "RANGE": "yellow",
            "HIGH_VOL": "orange"
        }

        color = colors.get(regime, "white")

        self.regime_label.setText(f"Regime: {regime}")
        self.regime_label.setStyleSheet(
            f"font-size:18px;color:{color}"
        )

    def _create_portfolio_exposure_graph(self):

        dock = QDockWidget("Portfolio Exposure", self)

        self.exposure_chart = pg.PlotWidget()

        self.exposure_bars = pg.BarGraphItem(
            x=[],
            height=[],
            width=0.6
        )

        self.exposure_chart.addItem(self.exposure_bars)

        dock.setWidget(self.exposure_chart)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _create_model_confidence(self):

        dock = QDockWidget("Model Confidence", self)

        self.confidence_plot = pg.PlotWidget()

        self.confidence_curve = self.confidence_plot.plot(
            pen="cyan"
        )



        dock.setWidget(self.confidence_plot)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _update_confidence(self, confidence):

        self.confidence_data.append(confidence)

        if len(self.confidence_data) > 200:
            self.confidence_data.pop(0)

        self.confidence_curve.setData(self.confidence_data)

    def _update_portfolio_exposure(self):

        positions = self.controller.portfolio.positions

        if not positions:
            return

        symbols = []
        values = []

        for pos in positions.values():

            symbols.append(pos["symbol"])
            values.append(pos["value"])

        x = list(range(len(symbols)))

        self.exposure_bars.setOpts(
            x=x,
            height=values
        )

    def _create_risk_heatmap(self):

        dock = QDockWidget("Risk Heatmap", self)

        self.risk_map = pg.ImageItem()

        plot = pg.PlotWidget()
        plot.addItem(self.risk_map)

        dock.setWidget(plot)

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _update_risk_heatmap(self):

        if self.risk_map is None:
            return

        portfolio = getattr(self.controller, "portfolio", None)
        positions = getattr(portfolio, "positions", {}) if portfolio is not None else {}

        if not positions:
            self.risk_map.setImage(np.zeros((1, 1), dtype=float), autoLevels=False, levels=(0.0, 1.0))
            return

        risks = []

        for pos in positions.values():
            if not isinstance(pos, dict):
                continue

            risk = pos.get("risk")
            if risk is None:
                size = float(pos.get("size", pos.get("amount", 0)) or 0)
                entry = float(pos.get("entry_price", pos.get("price", 0)) or 0)
                risk = abs(size * entry)

            try:
                risk_value = abs(float(risk))
            except Exception:
                continue

            if risk_value > 0:
                risks.append(risk_value)

        if not risks:
            self.risk_map.setImage(np.zeros((1, 1), dtype=float), autoLevels=False, levels=(0.0, 1.0))
            return

        data = np.array(risks, dtype=float).reshape(1, len(risks))
        max_value = float(np.max(data))

        if max_value <= 0:
            normalized = np.zeros_like(data)
        else:
            normalized = data / max_value

        self.risk_map.setImage(normalized, autoLevels=False, levels=(0.0, 1.0))




# ==========================================================
# TERMINAL HOTFIX OVERRIDES
# ==========================================================
# These overrides stabilize runtime paths without requiring a full terminal rewrite.


def candles_to_df(df):
    """Normalize candles into a pandas DataFrame when possible."""
    try:
        import pandas as pd
    except Exception:
        pd = None

    if df is None:
        return pd.DataFrame() if pd else []

    if pd is not None:
        if isinstance(df, pd.DataFrame):
            return df
        try:
            frame = pd.DataFrame(df)
            if not frame.empty and frame.shape[1] >= 6:
                frame = frame.iloc[:, :6]
                frame.columns = ["timestamp", "open", "high", "low", "close", "volume"]
            return frame
        except Exception:
            return df

    return df


async def _hotfix_prepare_backtest_context(self):
    chart = self.chart_tabs.currentWidget()
    if chart is None and hasattr(self.chart_tabs, "count") and self.chart_tabs.count() > 0:
        chart = self.chart_tabs.widget(0)

    symbol = getattr(chart, "symbol", None) or getattr(self, "symbol", None)
    timeframe = getattr(chart, "timeframe", None) or getattr(self, "current_timeframe", "1h")
    if not symbol:
        raise RuntimeError("Select a chart before starting a backtest")

    strategy_source = None
    trading_system = getattr(self.controller, "trading_system", None)
    if trading_system is not None:
        strategy_source = getattr(trading_system, "strategy", None)
    if strategy_source is None:
        from strategy.strategy_registry import StrategyRegistry
        strategy_source = StrategyRegistry()

    buffers = getattr(self.controller, "candle_buffers", {})
    frame = None
    if hasattr(buffers, "get"):
        frame = (buffers.get(symbol) or {}).get(timeframe)
    if frame is None and hasattr(self.controller, "request_candle_data"):
        await self.controller.request_candle_data(symbol=symbol, timeframe=timeframe, limit=500)
        frame = (getattr(self.controller, "candle_buffers", {}).get(symbol) or {}).get(timeframe)
    if frame is None or getattr(frame, "empty", False):
        raise RuntimeError(f"No candle history available for {symbol} {timeframe}")

    strategy_name = getattr(getattr(self.controller, "config", None), "strategy", None)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "data": frame.copy() if hasattr(frame, "copy") else frame,
        "strategy": strategy_source,
        "strategy_name": strategy_name,
    }


async def _hotfix_run_backtest_clicked(self):
    try:
        context = await _hotfix_prepare_backtest_context(self)

        self.backtest_engine = BacktestEngine(
            strategy=context["strategy"],
            simulator=Simulator(
                initial_balance=getattr(self.controller, "initial_capital", 10000)
            ),
        )
        self._backtest_context = context
        self.results = None
        self.backtest_report = None
        self._backtest_journal_lines = []
        self._append_backtest_journal(
            f"Initialized strategy tester for {context['symbol']} {context['timeframe']} using {context.get('strategy_name') or 'Default'}."
        )
        self._show_backtest_window()
        self._refresh_backtest_window(message="Backtest engine initialized.")

    except Exception as e:
        self.system_console.log(f"Backtest initialization error: {e}")
        self._append_backtest_journal(f"Initialization failed: {e}", "ERROR")
        self._show_backtest_window()
        self._refresh_backtest_window(message=f"Backtest initialization error: {e}")


def _hotfix_start_backtest(self):
    try:
        if not hasattr(self, "backtest_engine"):
            self.system_console.log("Backtest engine not initialized.")
            self._append_backtest_journal("Backtest engine not initialized.", "ERROR")
            self._refresh_backtest_window(message="Backtest engine not initialized.")
            return

        backtest_context = getattr(self, "_backtest_context", {}) or {}
        symbol = backtest_context.get("symbol", "BACKTEST")
        strategy_name = backtest_context.get("strategy_name")
        data = candles_to_df(backtest_context.get("data"))
        if data is None or not hasattr(data, "__len__") or len(data) == 0:
            self.system_console.log("No historical data available for backtesting.")
            self._append_backtest_journal("No historical data available for backtesting.", "ERROR")
            self._refresh_backtest_window(message="No historical data available for backtesting.")
            return

        self._append_backtest_journal(
            f"Starting backtest for {symbol} on {backtest_context.get('timeframe', '-')}.",
            "INFO",
        )
        self.results = self.backtest_engine.run(data, symbol=symbol, strategy_name=strategy_name)
        self.backtest_report = ReportGenerator(
            trades=self.results,
            equity_history=getattr(self.backtest_engine, "equity_curve", []),
        ).generate()
        self.system_console.log("Backtest completed.", "INFO")
        total_trades = len(self.results) if hasattr(self.results, "__len__") else 0
        self._append_backtest_journal(
            f"Backtest completed with {total_trades} trade rows and final equity {float(self.backtest_report.get('final_equity', 0.0) or 0.0):.2f}.",
            "INFO",
        )
        self._refresh_backtest_window(message="Backtest completed.")

    except Exception as e:
        self.system_console.log(f"Backtest failed: {e}", "ERROR")
        self._append_backtest_journal(f"Backtest failed: {e}", "ERROR")
        self._refresh_backtest_window(message=f"Backtest failed: {e}")


def _hotfix_stop_backtest(self):
    self.system_console.log("Backtest stop requested.", "INFO")
    self._append_backtest_journal("Backtest stop requested.", "WARN")
    self._refresh_backtest_window(message="Backtest stop requested.")


def _hotfix_generate_report(self):
    try:
        trades = getattr(self, "results", None)
        if trades is None:
            raise RuntimeError("Run a backtest before generating a report")

        generator = ReportGenerator(
            trades=trades,
            equity_history=getattr(self.backtest_engine, "equity_curve", []),
        )
        pdf_path = generator.export_pdf()
        excel_path = generator.export_excel()
        self.backtest_report = generator.generate()
        self.system_console.log(f"Backtest report generated: {pdf_path} | {excel_path}", "INFO")
        self._append_backtest_journal(
            f"Report exported to {pdf_path} and {excel_path}.",
            "INFO",
        )
        self._refresh_backtest_window(message="Backtest report generated.")
    except Exception as e:
        self.system_console.log(f"Report generation failed: {e}")
        self._append_backtest_journal(f"Report generation failed: {e}", "ERROR")


def _hotfix_show_optimization_window(self):
    window = self._get_or_create_tool_window(
        "strategy_optimization",
        "Strategy Optimization",
        width=980,
        height=640,
    )

    if getattr(window, "_optimization_container", None) is None:
        container = QWidget()
        layout = QVBoxLayout(container)

        status = QLabel("Optimization workspace ready.")
        status.setStyleSheet("color: #e6edf7; font-weight: 700;")
        layout.addWidget(status)

        controls = QHBoxLayout()
        run_btn = QPushButton("Run Optimization")
        apply_btn = QPushButton("Apply Best Params")
        run_btn.clicked.connect(lambda: asyncio.get_event_loop().create_task(self._run_strategy_optimization()))
        apply_btn.clicked.connect(self._apply_best_optimization_params)
        controls.addWidget(run_btn)
        controls.addWidget(apply_btn)
        controls.addStretch()
        layout.addLayout(controls)

        summary = QLabel("-")
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #9fb0c7;")
        layout.addWidget(summary)

        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels(
            [
                "RSI",
                "EMA Fast",
                "EMA Slow",
                "ATR",
                "Profit",
                "Sharpe",
                "Win Rate",
                "Final Equity",
            ]
        )
        layout.addWidget(table)

        window.setCentralWidget(container)
        window._optimization_container = container
        window._optimization_status = status
        window._optimization_summary = summary
        window._optimization_table = table

    self._refresh_optimization_window(window)
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def _hotfix_refresh_optimization_window(self, window=None, message=None):
    window = window or self.detached_tool_windows.get("strategy_optimization")
    if window is None:
        return

    status = getattr(window, "_optimization_status", None)
    summary = getattr(window, "_optimization_summary", None)
    table = getattr(window, "_optimization_table", None)
    if status is None or summary is None or table is None:
        return

    context = getattr(self, "_optimization_context", {}) or {}
    symbol = context.get("symbol", "-")
    timeframe = context.get("timeframe", "-")
    strategy_name = context.get("strategy_name", None) or getattr(getattr(self.controller, "config", None), "strategy", "Default")
    dataset = context.get("data")
    candle_count = len(dataset) if hasattr(dataset, "__len__") else 0

    status.setText(message or "Optimization workspace ready.")
    summary.setText(f"Symbol: {symbol} | Timeframe: {timeframe} | Strategy: {strategy_name} | Candles: {candle_count}")

    results = getattr(self, "optimization_results", None)
    if results is None or getattr(results, "empty", True):
        table.setRowCount(0)
        return

    display = results.head(25).reset_index(drop=True)
    table.setRowCount(len(display))

    columns = [
        ("rsi_period", "{:g}"),
        ("ema_fast", "{:g}"),
        ("ema_slow", "{:g}"),
        ("atr_period", "{:g}"),
        ("total_profit", "{:.2f}"),
        ("sharpe_ratio", "{:.3f}"),
        ("win_rate", "{:.2%}"),
        ("final_equity", "{:.2f}"),
    ]

    for row_idx, (_, row) in enumerate(display.iterrows()):
        for col_idx, (column, fmt) in enumerate(columns):
            value = row.get(column, "")
            try:
                text = fmt.format(float(value))
            except Exception:
                text = str(value)
            table.setItem(row_idx, col_idx, QTableWidgetItem(text))

    table.resizeColumnsToContents()


async def _hotfix_run_strategy_optimization(self):
    try:
        from backtesting.optimizer import StrategyOptimizer

        context = await _hotfix_prepare_backtest_context(self)
        data = candles_to_df(context.get("data"))
        if data is None or not hasattr(data, "__len__") or len(data) == 0:
            raise RuntimeError("No historical data available for optimization")

        optimizer = StrategyOptimizer(
            strategy=context["strategy"],
            initial_balance=getattr(self.controller, "initial_capital", 10000),
        )
        self._optimization_context = context
        self.optimization_results = optimizer.optimize(
            data,
            symbol=context["symbol"],
            strategy_name=context.get("strategy_name"),
        )
        self.optimization_best = None
        if self.optimization_results is not None and not self.optimization_results.empty:
            self.optimization_best = self.optimization_results.iloc[0].to_dict()

        self.system_console.log("Strategy optimization completed.", "INFO")
        self._hotfix_show_optimization_window()
        self._refresh_optimization_window(message="Strategy optimization completed.")

    except Exception as e:
        self.system_console.log(f"Strategy optimization failed: {e}", "ERROR")
        self._hotfix_show_optimization_window()
        self._refresh_optimization_window(message=f"Strategy optimization failed: {e}")


def _hotfix_apply_best_optimization_params(self):
    try:
        best = getattr(self, "optimization_best", None)
        if not isinstance(best, dict):
            raise RuntimeError("Run optimization before applying parameters")

        context = getattr(self, "_optimization_context", {}) or {}
        strategy_source = context.get("strategy")
        strategy_name = context.get("strategy_name")

        if strategy_source is None:
            raise RuntimeError("No strategy context available")

        if hasattr(strategy_source, "_resolve_strategy"):
            target = strategy_source._resolve_strategy(strategy_name)
        else:
            target = strategy_source

        applied = []
        for key in ["rsi_period", "ema_fast", "ema_slow", "atr_period"]:
            if key in best and hasattr(target, key):
                setattr(target, key, int(best[key]))
                applied.append(f"{key}={int(best[key])}")

        if not applied:
            raise RuntimeError("No compatible strategy parameters were available to apply")

        self.system_console.log(f"Applied optimized params: {', '.join(applied)}", "INFO")
        self._refresh_optimization_window(message="Applied best optimization parameters.")

    except Exception as e:
        self.system_console.log(f"Apply optimization failed: {e}", "ERROR")
        self._refresh_optimization_window(message=f"Apply optimization failed: {e}")


def _hotfix_optimize_strategy(self):
    self._hotfix_show_optimization_window()
    asyncio.get_event_loop().create_task(self._run_strategy_optimization())


async def _hotfix_reload_chart_data(self, symbol, timeframe):
    try:
        df = None

        # Preferred cache shape: candle_buffers[symbol][timeframe]
        buffers = getattr(self.controller, "candle_buffers", None)
        if hasattr(buffers, "get"):
            symbol_bucket = buffers.get(symbol)
            if hasattr(symbol_bucket, "get"):
                df = symbol_bucket.get(timeframe)

        # Fallback to legacy candle_buffer store.
        if df is None:
            legacy = getattr(self.controller, "candle_buffer", None)
            if hasattr(legacy, "get"):
                symbol_bucket = legacy.get(symbol)
                if hasattr(symbol_bucket, "get"):
                    df = symbol_bucket.get(timeframe)
                elif symbol_bucket is not None:
                    df = symbol_bucket

                if df is None:
                    df = legacy.get(timeframe)

        if df is None:
            return

        self._update_chart(symbol, df)

    except Exception as e:
        self.logger.error(f"Timeframe reload failed: {e}")


def _hotfix_open_risk_settings(self):
    self._show_settings_window()


def _hotfix_save_settings(self):
    try:
        self._show_settings_window()
    except Exception as e:
        self.logger.error(f"Risk settings error: {e}")


def _hotfix_settings_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _hotfix_settings_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def _hotfix_settings_int(value, default):
    try:
        return int(float(value))
    except Exception:
        return default


def _hotfix_get_live_risk_engine(self):
    trading_system = getattr(self.controller, "trading_system", None)
    risk_engine = getattr(trading_system, "risk_engine", None)
    if risk_engine is not None:
        return risk_engine
    return getattr(self.controller, "risk_engine", None)


def _hotfix_update_color_button(button, color):
    if button is None:
        return
    button.setText(color)
    button.setStyleSheet(
        """
        QPushButton {
            background-color: %s;
            color: white;
            border: 1px solid #31415f;
            border-radius: 8px;
            padding: 6px 10px;
            font-weight: 700;
        }
        """
        % color
    )


def _hotfix_pick_settings_color(window, attr_name, button, title):
    current = getattr(window, attr_name, "#26a69a")
    picked = QColorDialog.getColor(QColor(current), window, title)
    if not picked.isValid():
        return
    color = picked.name()
    setattr(window, attr_name, color)
    _hotfix_update_color_button(button, color)


def _hotfix_collect_settings_values(self, window=None):
    if window is None:
        window = self.detached_tool_windows.get("application_settings")
    if window is None:
        return None

    return {
        "timeframe": window._settings_timeframe.currentText(),
        "order_type": window._settings_order_type.currentText(),
        "history_limit": int(window._settings_history_limit.value()),
        "initial_capital": float(window._settings_initial_capital.value()),
        "refresh_interval_ms": int(window._settings_refresh_ms.value()),
        "orderbook_interval_ms": int(window._settings_orderbook_ms.value()),
        "show_bid_ask_lines": window._settings_bid_ask_mode.currentData(),
        "candle_up_color": getattr(window, "_settings_up_color", self.candle_up_color),
        "candle_down_color": getattr(window, "_settings_down_color", self.candle_down_color),
        "max_portfolio_risk": float(window._settings_max_portfolio.value()),
        "max_risk_per_trade": float(window._settings_max_trade.value()),
        "max_position_size_pct": float(window._settings_max_position.value()),
        "max_gross_exposure_pct": float(window._settings_max_gross.value()),
    }


def _hotfix_apply_settings_values(self, values, persist=True, reload_chart=False):
    if not isinstance(values, dict):
        return

    timeframe = values.get("timeframe", getattr(self, "current_timeframe", "1h"))
    order_type = values.get("order_type", getattr(self, "order_type", "limit"))
    history_limit = max(100, int(values.get("history_limit", getattr(self.controller, "limit", 1000))))
    initial_capital = max(0.0, float(values.get("initial_capital", getattr(self.controller, "initial_capital", 10000))))
    refresh_interval_ms = max(250, int(values.get("refresh_interval_ms", 1000)))
    orderbook_interval_ms = max(250, int(values.get("orderbook_interval_ms", 1500)))
    show_bid_ask_lines = bool(values.get("show_bid_ask_lines", getattr(self, "show_bid_ask_lines", True)))
    candle_up_color = values.get("candle_up_color", getattr(self, "candle_up_color", "#26a69a"))
    candle_down_color = values.get("candle_down_color", getattr(self, "candle_down_color", "#ef5350"))

    self.current_timeframe = timeframe
    self.order_type = order_type
    self.controller.time_frame = timeframe
    self.controller.order_type = order_type
    self.controller.limit = history_limit
    self.controller.initial_capital = initial_capital
    self.controller.max_portfolio_risk = float(values.get("max_portfolio_risk", getattr(self.controller, "max_portfolio_risk", 0.2)))
    self.controller.max_risk_per_trade = float(values.get("max_risk_per_trade", getattr(self.controller, "max_risk_per_trade", 0.02)))
    self.controller.max_position_size_pct = float(values.get("max_position_size_pct", getattr(self.controller, "max_position_size_pct", 0.05)))
    self.controller.max_gross_exposure_pct = float(values.get("max_gross_exposure_pct", getattr(self.controller, "max_gross_exposure_pct", 1.0)))

    self.candle_up_color = candle_up_color
    self.candle_down_color = candle_down_color
    self.show_bid_ask_lines = show_bid_ask_lines

    if hasattr(self.controller, "candle_buffer") and hasattr(self.controller.candle_buffer, "max_length"):
        self.controller.candle_buffer.max_length = history_limit
    if hasattr(self.controller, "ticker_buffer") and hasattr(self.controller.ticker_buffer, "max_length"):
        self.controller.ticker_buffer.max_length = history_limit

    trading_system = getattr(self.controller, "trading_system", None)
    if trading_system is not None:
        setattr(trading_system, "time_frame", timeframe)
        setattr(trading_system, "limit", history_limit)

    risk_engine = _hotfix_get_live_risk_engine(self)
    if risk_engine is not None:
        risk_engine.account_equity = initial_capital
        risk_engine.max_portfolio_risk = self.controller.max_portfolio_risk
        risk_engine.max_risk_per_trade = self.controller.max_risk_per_trade
        risk_engine.max_position_size_pct = self.controller.max_position_size_pct
        risk_engine.max_gross_exposure_pct = self.controller.max_gross_exposure_pct

    self._set_active_timeframe_button(timeframe)
    self._apply_candle_colors_to_all_charts()

    toggle_action = getattr(self, "toggle_bid_ask_lines_action", None)
    if toggle_action is not None:
        blocked = toggle_action.blockSignals(True)
        toggle_action.setChecked(show_bid_ask_lines)
        toggle_action.blockSignals(blocked)

    for index in range(self.chart_tabs.count()):
        chart = self.chart_tabs.widget(index)
        if not isinstance(chart, ChartWidget):
            continue
        chart.set_candle_colors(candle_up_color, candle_down_color)
        chart.set_bid_ask_lines_visible(show_bid_ask_lines)

    if hasattr(self, "refresh_timer") and self.refresh_timer is not None:
        self.refresh_timer.start(refresh_interval_ms)
    if hasattr(self, "orderbook_timer") and self.orderbook_timer is not None:
        self.orderbook_timer.start(orderbook_interval_ms)

    if self.chart_tabs.count() > 0:
        current_index = self.chart_tabs.currentIndex()
        current_chart = self.chart_tabs.widget(current_index)
        if isinstance(current_chart, ChartWidget):
            current_chart.timeframe = timeframe
            self.chart_tabs.setTabText(current_index, f"{current_chart.symbol} ({timeframe})")
            if reload_chart and hasattr(self.controller, "request_candle_data"):
                asyncio.get_event_loop().create_task(
                    self.controller.request_candle_data(
                        symbol=current_chart.symbol,
                        timeframe=timeframe,
                        limit=min(history_limit, 1000),
                    )
                )
                asyncio.get_event_loop().create_task(
                    self._reload_chart_data(current_chart.symbol, timeframe)
                )
                self._request_active_orderbook()

    if persist:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("chart/candle_up_color", candle_up_color)
        self.settings.setValue("chart/candle_down_color", candle_down_color)
        self.settings.setValue("terminal/current_timeframe", timeframe)
        self.settings.setValue("terminal/order_type", order_type)
        self.settings.setValue("terminal/history_limit", history_limit)
        self.settings.setValue("terminal/initial_capital", initial_capital)
        self.settings.setValue("terminal/refresh_interval_ms", refresh_interval_ms)
        self.settings.setValue("terminal/orderbook_interval_ms", orderbook_interval_ms)
        self.settings.setValue("terminal/show_bid_ask_lines", show_bid_ask_lines)
        self.settings.setValue("risk/max_portfolio_risk", self.controller.max_portfolio_risk)
        self.settings.setValue("risk/max_risk_per_trade", self.controller.max_risk_per_trade)
        self.settings.setValue("risk/max_position_size_pct", self.controller.max_position_size_pct)
        self.settings.setValue("risk/max_gross_exposure_pct", self.controller.max_gross_exposure_pct)


def _hotfix_show_settings_window(self):
    window = self._get_or_create_tool_window(
        "application_settings",
        "Settings",
        width=680,
        height=700,
    )

    if getattr(window, "_settings_container", None) is None:
        container = QWidget()
        layout = QVBoxLayout(container)

        intro = QLabel("Configure trading defaults, chart behavior, refresh timing, and risk in one place.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #c9d5e8; font-weight: 600; padding: 4px 0 10px 0;")
        layout.addWidget(intro)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        general_tab = QWidget()
        general_form = QFormLayout(general_tab)

        timeframe = QComboBox()
        timeframe.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        order_type = QComboBox()
        order_type.addItems(["market", "limit"])

        history_limit = QDoubleSpinBox()
        history_limit.setDecimals(0)
        history_limit.setRange(100, 10000)
        history_limit.setSingleStep(100)

        initial_capital = QDoubleSpinBox()
        initial_capital.setDecimals(2)
        initial_capital.setRange(0, 1000000000)
        initial_capital.setSingleStep(1000)

        refresh_ms = QDoubleSpinBox()
        refresh_ms.setDecimals(0)
        refresh_ms.setRange(250, 60000)
        refresh_ms.setSingleStep(250)

        orderbook_ms = QDoubleSpinBox()
        orderbook_ms.setDecimals(0)
        orderbook_ms.setRange(250, 60000)
        orderbook_ms.setSingleStep(250)

        general_form.addRow("Default timeframe", timeframe)
        general_form.addRow("Default order type", order_type)
        general_form.addRow("History limit", history_limit)
        general_form.addRow("Initial capital", initial_capital)
        general_form.addRow("Terminal refresh (ms)", refresh_ms)
        general_form.addRow("Orderbook refresh (ms)", orderbook_ms)
        tabs.addTab(general_tab, "General")

        display_tab = QWidget()
        display_form = QFormLayout(display_tab)

        bid_ask_mode = QComboBox()
        bid_ask_mode.addItem("Show", True)
        bid_ask_mode.addItem("Hide", False)

        up_color_btn = QPushButton()
        down_color_btn = QPushButton()
        up_color_btn.clicked.connect(
            lambda: _hotfix_pick_settings_color(
                window,
                "_settings_up_color",
                up_color_btn,
                "Select Bullish Candle Color",
            )
        )
        down_color_btn.clicked.connect(
            lambda: _hotfix_pick_settings_color(
                window,
                "_settings_down_color",
                down_color_btn,
                "Select Bearish Candle Color",
            )
        )

        display_form.addRow("Bid/ask guide lines", bid_ask_mode)
        display_form.addRow("Bullish candle color", up_color_btn)
        display_form.addRow("Bearish candle color", down_color_btn)
        tabs.addTab(display_tab, "Display")

        risk_tab = QWidget()
        risk_form = QFormLayout(risk_tab)

        max_portfolio = QDoubleSpinBox()
        max_portfolio.setDecimals(4)
        max_portfolio.setRange(0, 100000)
        max_portfolio.setSingleStep(0.01)

        max_trade = QDoubleSpinBox()
        max_trade.setDecimals(4)
        max_trade.setRange(0, 100000)
        max_trade.setSingleStep(0.01)

        max_position = QDoubleSpinBox()
        max_position.setDecimals(4)
        max_position.setRange(0, 100000)
        max_position.setSingleStep(0.01)

        max_gross = QDoubleSpinBox()
        max_gross.setDecimals(4)
        max_gross.setRange(0, 100000)
        max_gross.setSingleStep(0.01)

        risk_form.addRow("Max portfolio risk", max_portfolio)
        risk_form.addRow("Max risk per trade", max_trade)
        risk_form.addRow("Max position size", max_position)
        risk_form.addRow("Max gross exposure", max_gross)
        tabs.addTab(risk_tab, "Risk")

        summary = QLabel("-")
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #9fb0c7; padding-top: 8px;")
        layout.addWidget(summary)

        actions = QHBoxLayout()
        exposure_btn = QPushButton("Open Portfolio Exposure")
        exposure_btn.clicked.connect(self._show_portfolio_exposure)
        apply_btn = QPushButton("Save Settings")
        apply_btn.setStyleSheet(self._action_button_style())
        apply_btn.clicked.connect(lambda: self._apply_settings_window(window))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(window.close)
        actions.addWidget(exposure_btn)
        actions.addStretch()
        actions.addWidget(apply_btn)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

        window.setCentralWidget(container)
        window._settings_container = container
        window._settings_tabs = tabs
        window._settings_timeframe = timeframe
        window._settings_order_type = order_type
        window._settings_history_limit = history_limit
        window._settings_initial_capital = initial_capital
        window._settings_refresh_ms = refresh_ms
        window._settings_orderbook_ms = orderbook_ms
        window._settings_bid_ask_mode = bid_ask_mode
        window._settings_up_button = up_color_btn
        window._settings_down_button = down_color_btn
        window._settings_max_portfolio = max_portfolio
        window._settings_max_trade = max_trade
        window._settings_max_position = max_position
        window._settings_max_gross = max_gross
        window._settings_summary = summary

    risk_engine = _hotfix_get_live_risk_engine(self)
    refresh_interval = 1000
    if hasattr(self, "refresh_timer") and self.refresh_timer is not None:
        refresh_interval = max(250, self.refresh_timer.interval())
    orderbook_interval = 1500
    if hasattr(self, "orderbook_timer") and self.orderbook_timer is not None:
        orderbook_interval = max(250, self.orderbook_timer.interval())

    window._settings_timeframe.setCurrentText(getattr(self, "current_timeframe", getattr(self.controller, "time_frame", "1h")))
    window._settings_order_type.setCurrentText(getattr(self, "order_type", getattr(self.controller, "order_type", "limit")))
    window._settings_history_limit.setValue(float(getattr(self.controller, "limit", 1000)))
    window._settings_initial_capital.setValue(float(getattr(self.controller, "initial_capital", 10000)))
    window._settings_refresh_ms.setValue(float(refresh_interval))
    window._settings_orderbook_ms.setValue(float(orderbook_interval))
    window._settings_bid_ask_mode.setCurrentIndex(0 if getattr(self, "show_bid_ask_lines", True) else 1)

    window._settings_up_color = getattr(self, "candle_up_color", "#26a69a")
    window._settings_down_color = getattr(self, "candle_down_color", "#ef5350")
    _hotfix_update_color_button(window._settings_up_button, window._settings_up_color)
    _hotfix_update_color_button(window._settings_down_button, window._settings_down_color)

    window._settings_max_portfolio.setValue(float(getattr(risk_engine, "max_portfolio_risk", getattr(self.controller, "max_portfolio_risk", 0.2))))
    window._settings_max_trade.setValue(float(getattr(risk_engine, "max_risk_per_trade", getattr(self.controller, "max_risk_per_trade", 0.02))))
    window._settings_max_position.setValue(float(getattr(risk_engine, "max_position_size_pct", getattr(self.controller, "max_position_size_pct", 0.05))))
    window._settings_max_gross.setValue(float(getattr(risk_engine, "max_gross_exposure_pct", getattr(self.controller, "max_gross_exposure_pct", 1.0))))

    window._settings_summary.setText(
        "Current defaults: "
        f"{window._settings_timeframe.currentText()} | "
        f"{window._settings_order_type.currentText()} orders | "
        f"history {int(window._settings_history_limit.value())} candles | "
        f"capital {window._settings_initial_capital.value():.2f}"
    )

    window.show()
    window.raise_()
    window.activateWindow()
    return window


def _hotfix_apply_settings_window(self, window=None):
    try:
        values = _hotfix_collect_settings_values(self, window)
        if not values:
            return

        _hotfix_apply_settings_values(self, values, persist=True, reload_chart=True)

        active_window = window or self.detached_tool_windows.get("application_settings")
        summary = getattr(active_window, "_settings_summary", None)
        if summary is not None:
            summary.setText(
                "Saved settings. "
                f"Timeframe: {values['timeframe']} | "
                f"Order type: {values['order_type']} | "
                f"History: {values['history_limit']} | "
                f"Bid/ask lines: {'shown' if values['show_bid_ask_lines'] else 'hidden'}"
            )

        self.system_console.log("Application settings updated successfully.", "INFO")

    except Exception as e:
        self.logger.error(f"Settings error: {e}")


def _hotfix_open_settings(self):
    self._show_settings_window()


def _hotfix_restore_settings(self):
    geometry = self.settings.value("geometry")
    if geometry:
        self.restoreGeometry(geometry)

    state = self.settings.value("windowState")
    if state:
        self.restoreState(state)

    values = {
        "timeframe": self.settings.value("terminal/current_timeframe", getattr(self.controller, "time_frame", getattr(self, "current_timeframe", "1h"))),
        "order_type": self.settings.value("terminal/order_type", getattr(self.controller, "order_type", getattr(self, "order_type", "limit"))),
        "history_limit": _hotfix_settings_int(self.settings.value("terminal/history_limit", getattr(self.controller, "limit", 1000)), getattr(self.controller, "limit", 1000)),
        "initial_capital": _hotfix_settings_float(self.settings.value("terminal/initial_capital", getattr(self.controller, "initial_capital", 10000)), getattr(self.controller, "initial_capital", 10000)),
        "refresh_interval_ms": _hotfix_settings_int(self.settings.value("terminal/refresh_interval_ms", 1000), 1000),
        "orderbook_interval_ms": _hotfix_settings_int(self.settings.value("terminal/orderbook_interval_ms", 1500), 1500),
        "show_bid_ask_lines": _hotfix_settings_bool(self.settings.value("terminal/show_bid_ask_lines", getattr(self, "show_bid_ask_lines", True)), getattr(self, "show_bid_ask_lines", True)),
        "candle_up_color": self.settings.value("chart/candle_up_color", getattr(self, "candle_up_color", "#26a69a")),
        "candle_down_color": self.settings.value("chart/candle_down_color", getattr(self, "candle_down_color", "#ef5350")),
        "max_portfolio_risk": _hotfix_settings_float(self.settings.value("risk/max_portfolio_risk", getattr(self.controller, "max_portfolio_risk", 0.2)), getattr(self.controller, "max_portfolio_risk", 0.2)),
        "max_risk_per_trade": _hotfix_settings_float(self.settings.value("risk/max_risk_per_trade", getattr(self.controller, "max_risk_per_trade", 0.02)), getattr(self.controller, "max_risk_per_trade", 0.02)),
        "max_position_size_pct": _hotfix_settings_float(self.settings.value("risk/max_position_size_pct", getattr(self.controller, "max_position_size_pct", 0.05)), getattr(self.controller, "max_position_size_pct", 0.05)),
        "max_gross_exposure_pct": _hotfix_settings_float(self.settings.value("risk/max_gross_exposure_pct", getattr(self.controller, "max_gross_exposure_pct", 1.0)), getattr(self.controller, "max_gross_exposure_pct", 1.0)),
    }

    _hotfix_apply_settings_values(self, values, persist=False, reload_chart=False)


def _hotfix_close_event(self, event):
    try:
        if hasattr(self, "refresh_timer") and self.refresh_timer is not None:
            self.refresh_timer.stop()
        if hasattr(self, "orderbook_timer") and self.orderbook_timer is not None:
            self.orderbook_timer.stop()
        if hasattr(self, "spinner_timer") and self.spinner_timer is not None:
            self.spinner_timer.stop()
    except Exception:
        pass

    values = {
        "timeframe": getattr(self, "current_timeframe", getattr(self.controller, "time_frame", "1h")),
        "order_type": getattr(self, "order_type", getattr(self.controller, "order_type", "limit")),
        "history_limit": getattr(self.controller, "limit", 1000),
        "initial_capital": getattr(self.controller, "initial_capital", 10000),
        "refresh_interval_ms": self.refresh_timer.interval() if hasattr(self, "refresh_timer") and self.refresh_timer is not None else 1000,
        "orderbook_interval_ms": self.orderbook_timer.interval() if hasattr(self, "orderbook_timer") and self.orderbook_timer is not None else 1500,
        "show_bid_ask_lines": getattr(self, "show_bid_ask_lines", True),
        "candle_up_color": getattr(self, "candle_up_color", "#26a69a"),
        "candle_down_color": getattr(self, "candle_down_color", "#ef5350"),
        "max_portfolio_risk": getattr(self.controller, "max_portfolio_risk", 0.2),
        "max_risk_per_trade": getattr(self.controller, "max_risk_per_trade", 0.02),
        "max_position_size_pct": getattr(self.controller, "max_position_size_pct", 0.05),
        "max_gross_exposure_pct": getattr(self.controller, "max_gross_exposure_pct", 1.0),
    }
    _hotfix_apply_settings_values(self, values, persist=True, reload_chart=False)
    super(Terminal, self).closeEvent(event)


async def _hotfix_refresh_markets_async(self):
    broker = getattr(self.controller, "broker", None)
    if broker is None:
        raise RuntimeError("Broker is not connected")

    if hasattr(broker, "connect"):
        try:
            maybe = broker.connect()
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception:
            pass

    symbols = None
    if hasattr(self.controller, "_fetch_symbols"):
        symbols = await self.controller._fetch_symbols(broker)
    else:
        if hasattr(broker, "fetch_symbol"):
            symbols = await broker.fetch_symbol()
        elif hasattr(broker, "fetch_symbols"):
            symbols = await broker.fetch_symbols()

    if not symbols:
        raise RuntimeError("No symbols were returned by the broker")

    broker_cfg = getattr(getattr(self.controller, "config", None), "broker", None)
    broker_type = getattr(broker_cfg, "type", None)
    exchange = getattr(broker_cfg, "exchange", None) or getattr(broker, "exchange_name", "Broker")

    if hasattr(self.controller, "_filter_symbols_for_trading"):
        symbols = self.controller._filter_symbols_for_trading(symbols, broker_type, exchange=exchange)

    if hasattr(self.controller, "_select_trade_symbols"):
        selected = await self.controller._select_trade_symbols(symbols, broker_type)
        if selected:
            symbols = selected

    self.controller.symbols = list(symbols)
    self.controller.symbols_signal.emit(str(exchange), list(self.controller.symbols))

    active_symbol = self._current_chart_symbol()
    if active_symbol and hasattr(self.controller, "request_candle_data"):
        await self.controller.request_candle_data(
            symbol=active_symbol,
            timeframe=getattr(self, "current_timeframe", "1h"),
            limit=min(getattr(self.controller, "limit", 300), 1000),
        )
        await self._reload_chart_data(active_symbol, getattr(self, "current_timeframe", "1h"))

    if active_symbol and hasattr(self.controller, "request_orderbook"):
        await self.controller.request_orderbook(symbol=active_symbol, limit=20)

    self._refresh_terminal()
    self.system_console.log(f"Markets refreshed: {len(self.controller.symbols)} symbols loaded.", "INFO")


def _hotfix_refresh_markets(self):
    async def runner():
        try:
            await _hotfix_refresh_markets_async(self)
        except Exception as e:
            self.system_console.log(f"Market refresh failed: {e}", "ERROR")

    asyncio.get_event_loop().create_task(runner())


async def _hotfix_reload_balance_async(self):
    if not hasattr(self.controller, "update_balance"):
        raise RuntimeError("Balance reload is not supported by this controller")

    await self.controller.update_balance()
    self._refresh_terminal()

    balance = getattr(self.controller, "balances", {})
    summary, _tooltip = self._compact_balance_text(balance)
    self.system_console.log(f"Balances reloaded: {summary}", "INFO")


def _hotfix_reload_balance(self):
    async def runner():
        try:
            await _hotfix_reload_balance_async(self)
        except Exception as e:
            self.system_console.log(f"Balance reload failed: {e}", "ERROR")

    asyncio.get_event_loop().create_task(runner())


def _hotfix_refresh_active_orderbook(self):
    symbol = self._current_chart_symbol()
    if not symbol:
        self.system_console.log("Open a chart tab before refreshing orderbook.", "ERROR")
        return

    async def runner():
        try:
            if not hasattr(self.controller, "request_orderbook"):
                raise RuntimeError("Orderbook refresh is not supported by this controller")
            await self.controller.request_orderbook(symbol=symbol, limit=20)
            self.system_console.log(f"Orderbook refreshed for {symbol}.", "INFO")
        except Exception as e:
            self.system_console.log(f"Orderbook refresh failed: {e}", "ERROR")

    asyncio.get_event_loop().create_task(runner())


def _hotfix_refresh_active_chart_data(self):
    chart = self.chart_tabs.currentWidget()
    if not isinstance(chart, ChartWidget):
        self.system_console.log("Open a chart tab before refreshing candles.", "ERROR")
        return

    symbol = chart.symbol
    timeframe = getattr(chart, "timeframe", getattr(self, "current_timeframe", "1h"))

    async def runner():
        try:
            if not hasattr(self.controller, "request_candle_data"):
                raise RuntimeError("Chart refresh is not supported by this controller")

            await self.controller.request_candle_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=min(getattr(self.controller, "limit", 300), 1000),
            )
            await self._reload_chart_data(symbol, timeframe)
            self.system_console.log(f"Chart data refreshed for {symbol} ({timeframe}).", "INFO")
        except Exception as e:
            self.system_console.log(f"Chart refresh failed: {e}", "ERROR")

    asyncio.get_event_loop().create_task(runner())


# Bind overrides
Terminal.run_backtest_clicked = _hotfix_run_backtest_clicked
Terminal.start_backtest = _hotfix_start_backtest
Terminal.stop_backtest = _hotfix_stop_backtest
Terminal._generate_report = _hotfix_generate_report
Terminal._show_optimization_window = _hotfix_show_optimization_window
Terminal._refresh_optimization_window = _hotfix_refresh_optimization_window
Terminal._run_strategy_optimization = _hotfix_run_strategy_optimization
Terminal._apply_best_optimization_params = _hotfix_apply_best_optimization_params
Terminal._optimize_strategy = _hotfix_optimize_strategy
Terminal._reload_chart_data = _hotfix_reload_chart_data
Terminal._refresh_markets = _hotfix_refresh_markets
Terminal._reload_balance = _hotfix_reload_balance
Terminal._refresh_active_chart_data = _hotfix_refresh_active_chart_data
Terminal._refresh_active_orderbook = _hotfix_refresh_active_orderbook
Terminal._show_settings_window = _hotfix_show_settings_window
Terminal._apply_settings_window = _hotfix_apply_settings_window
Terminal._show_risk_settings_window = _hotfix_show_settings_window
Terminal._apply_risk_settings = _hotfix_apply_settings_window
Terminal._open_settings = _hotfix_open_settings
Terminal._open_risk_settings = _hotfix_open_risk_settings
Terminal._restore_settings = _hotfix_restore_settings
Terminal.closeEvent = _hotfix_close_event
Terminal.save_settings = _hotfix_save_settings
















