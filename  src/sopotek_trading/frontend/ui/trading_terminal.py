import asyncio

import pyqtgraph as pg
from PySide6.QtCore import Qt, QSettings, QDateTime, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QDockWidget,
    QTableWidget, QTableWidgetItem,
    QPushButton, QLabel,
    QTabWidget, QInputDialog,
    QToolBar, QFileDialog
)

from sopotek_trading.backend.strategy.backtest_engine import BacktestEngine
from sopotek_trading.frontend.ui.report_generator import ReportGenerator
from sopotek_trading.frontend.ui.system_console import SystemConsole


class TradingTerminal(QMainWindow):
    logout_requested=Signal(str)
    autotrade_toggle = Signal(bool)

    def __init__(self, controller):
        super().__init__()


        self.controller = controller
        self.logger = controller.logger
        self.settings = QSettings("Sopotek", "TradingPlatform")

        self.setWindowTitle("Sopotek AI Trading Terminal")
        self.resize(1700, 950)
        self.connection_indicator = QLabel("● CONNECTING")
        self.connection_indicator.setStyleSheet("color: orange; font-weight: bold;")


        self.current_timeframe = "1m"
        self.autotrading_enabled = False
        self.timeframe_buttons = {}

        # ===== Signals =====
        self.controller.candle_signal.connect(self._update_chart)
        self.controller.equity_signal.connect(self._update_equity)
        self.controller.trade_signal.connect(self._update_trade_log)
        self.controller.ticker_signal.connect(self._update_ticker)

        # ===== Central Charts =====
        self.chart_tabs = QTabWidget()
        self.chart_tabs.setTabsClosable(True)
        self.chart_tabs.tabCloseRequested.connect(
            lambda i: self.chart_tabs.removeTab(i)
        )
        self.setCentralWidget(self.chart_tabs)

        # ===== Console =====
        self.system_console = SystemConsole()
        console_dock = QDockWidget("System Console", self)
        console_dock.setWidget(self.system_console)
        self.addDockWidget(Qt.BottomDockWidgetArea, console_dock)

        # ===== Panels =====
        self._create_menu_bar()
        self._create_toolbar()
        self._create_market_watch_panel()
        self._create_positions_panel()
        self._create_trade_log_panel()
        self._create_equity_panel()
        self._create_performance_panel()
        self._create_strategy_comparison()

        self._create_chart_tab("BTC/USDT", "1m")
        self._restore_settings()

    # ==========================================================
    # MENU
    # ==========================================================

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        report_action = QAction("Generate Trading Report", self)
        report_action.triggered.connect(self._generate_report)
        file_menu.addAction(report_action)

        backtest_action = QAction("Run Backtest", self)
        backtest_action.triggered.connect(
            lambda: asyncio.create_task(self.run_backtest_clicked())
        )
        file_menu.addAction(backtest_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        charts_menu = menu_bar.addMenu("Charts")
        new_chart = QAction("New Chart", self)
        new_chart.triggered.connect(self._add_new_chart)
        charts_menu.addAction(new_chart)
    def update_connection_status(self, status: str):

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
    # ==========================================================
    # TOOLBAR
    # ==========================================================

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        toolbar.addWidget(self.connection_indicator)

        self.heartbeat = QLabel("●")
        toolbar.addWidget(self.heartbeat)

        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            btn = QPushButton(tf)
            btn.clicked.connect(
                lambda checked, t=tf: self._set_timeframe(t)
            )
            toolbar.addWidget(btn)
            self.timeframe_buttons[tf] = btn

        toolbar.addSeparator()
        auto_btn = QPushButton("AutoTrading OFF")
        auto_btn.clicked.connect(self._toggle_autotrading)
        self.auto_button = auto_btn
        toolbar.addWidget(auto_btn)

        screenshot_btn = QPushButton("Screenshot")
        screenshot_btn.clicked.connect(self.take_screen_shot)
        toolbar.addWidget(screenshot_btn)

        self.autotrade_toggle.emit(self.autotrading_enabled)

    # ==========================================================
    # AUTOTRADING
    # ==========================================================

    def _toggle_autotrading(self):

     self.autotrading_enabled = not self.autotrading_enabled

     if self.autotrading_enabled:
        self.auto_button.setText("AutoTrading ON")
        self.auto_button.setStyleSheet("background-color: green; color: white;")
        asyncio.create_task(self.controller.start_autotrading())
     else:
        self.auto_button.setText("AutoTrading OFF")
        self.auto_button.setStyleSheet("")
        asyncio.create_task(self.controller.stop_autotrading())
    # ==========================================================
    # CHARTS
    # ==========================================================

    def _create_chart_tab(self, symbol, timeframe):
        chart = pg.PlotWidget()
        chart.setBackground("k")
        chart.showGrid(x=True, y=True)

        chart.symbol = symbol
        chart.timeframe = timeframe
        chart.plot_curve = chart.plot(pen="c")

        self.chart_tabs.addTab(chart, f"{symbol} ({timeframe})")

    def _add_new_chart(self):
        symbol, ok = QInputDialog.getText(
            self, "New Chart", "Enter Symbol:"
        )
        if ok and symbol:
            self._create_chart_tab(symbol.upper(), "1m")

    def _set_timeframe(self, tf):
        self.current_timeframe = tf
        index = self.chart_tabs.currentIndex()
        chart = self.chart_tabs.widget(index)
        chart.timeframe = tf
        self.chart_tabs.setTabText(
            index, f"{chart.symbol} ({tf})"
        )

    # ==========================================================
    # UPDATE METHODS
    # ==========================================================

    def _update_chart(self, symbol, df):
        for i in range(self.chart_tabs.count()):
            chart = self.chart_tabs.widget(i)
            if chart.symbol == symbol:
                chart.plot_curve.setData(df["close"].values)

        self.heartbeat.setStyleSheet("color: green;")

    def _update_equity(self, equity):
        self.equity_label.setText(f"Equity: {equity:.2f}")
        self.equity_curve.setData(self.controller.performance_engine.equity_history)

    def _update_trade_log(self, trade):
        row = self.trade_log.rowCount()
        self.trade_log.insertRow(row)
        self.trade_log.setItem(row, 0, QTableWidgetItem(trade["symbol"]))
        self.trade_log.setItem(row, 1, QTableWidgetItem(trade["side"]))
        self.trade_log.setItem(row, 2, QTableWidgetItem(str(trade["price"])))
        self.trade_log.setItem(row, 3, QTableWidgetItem(str(trade["size"])))

    def _update_ticker(self, symbol, bid, ask):
        mid = (bid + ask) / 2
        self.tick_prices.append(mid)
        if len(self.tick_prices) > 200:
            self.tick_prices.pop(0)
        self.tick_chart_curve.setData(self.tick_prices)

    # ==========================================================
    # PANELS
    # ==========================================================

    def _create_market_watch_panel(self):
        dock = QDockWidget("Market Watch", self)
        self.symbols_table = QTableWidget()
        self.symbols_table.setColumnCount(3)
        self.symbols_table.setHorizontalHeaderLabels(
            ["Symbol", "Bid", "Ask"]
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

    def _create_trade_log_panel(self):
        dock = QDockWidget("Trade Log", self)
        self.trade_log = QTableWidget()
        self.trade_log.setColumnCount(4)
        self.trade_log.setHorizontalHeaderLabels(
            ["Symbol", "Side", "Price", "Size"]
        )
        dock.setWidget(self.trade_log)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _create_equity_panel(self):
        dock = QDockWidget("Equity Curve", self)
        self.equity_chart = pg.PlotWidget()
        self.equity_curve = self.equity_chart.plot(pen="g")
        dock.setWidget(self.equity_chart)
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
        df = await self.controller.broker.fetch_ohlcv(
            "BTC/USDT", "1h",1000
        )
        engine = BacktestEngine(self.controller.ml_model, df)
        result = engine.run()
        self.system_console.log(
            f"Backtest Completed: {len(result['trades'])} trades",
            "INFO"
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

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        super().closeEvent(event)

    def _restore_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)