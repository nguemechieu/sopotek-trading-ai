import asyncio
import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from sopotek_trading.backend.analytics.performance_engine import PerformanceEngine
from sopotek_trading.backend.sopotek_trading import SopotekTrading
from sopotek_trading.frontend.ui.dashboard import Dashboard
from sopotek_trading.frontend.ui.trading_terminal import TradingTerminal


class AppController(QMainWindow):
    # ✅ Signals MUST be class attributes
    candle_signal = Signal(str, object)
    equity_signal = Signal(float)
    trade_signal = Signal(dict)
    ticker_signal = Signal(str, float, float)
    connection_signal = Signal(str)
    orderbook_signal = Signal(str, list, list)
    strategy_debug_signal = Signal(dict)
    autotrade_toggle = Signal(list)
    # NEW
    training_status_signal = Signal(str, str)
    # (symbol, status)

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger(__name__)
        self.debug_info = None
        self.controller = self
        self.performance_engine=PerformanceEngine(controller=self.controller)

        self.setWindowTitle("Sopotek Trading Platform")
        self.resize(1600, 900)

        self.trade_history = []
        self.server_message = {"message": "",
                               "status": "",
                               "error": ""}
        self.exchange_name = "fghj"
        self.api_key = "rt"
        self.secret = "er"
        self.mode = "live"
        self.rate_limiter = 5
        self.equity_refresh = 60
        self.limit = 1000
        self.exchange_options = "spot"
        self.account_id = "2345690"
        self.balance = 0.0
        self.equity = 0.0
        self.daily_loss = 0.0
        self.daily_gains = 0.0
        self.strategy_selected = "RSI"

        # ================================
        # Central Stack
        # ================================
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = Dashboard(self.controller)
        self.stack.addWidget(self.dashboard)

        self.trading_app = None
        self.terminal = None
        self.strategy_debug_signal.emit(self.debug_info)

        self.dashboard.login_success.connect(self._handle_login)

    def _handle_login(self, config):
        asyncio.create_task(self.initialize_trading(config))

    # ======================================================
    # Initialize Trading System
    # ======================================================

    async def initialize_trading(self, config):

        try:
            self.dashboard.show_loading()

            await self._cleanup_session()

            self.trading_app = SopotekTrading(config=config, controller=self.controller)
            await self.trading_app.initialize()

            self.terminal = TradingTerminal(controller=self.controller)

            self.terminal.logout_requested.connect(
                lambda: asyncio.create_task(self.logout())
            )

            # self.terminal.autotrade_toggle.connect(
            #     lambda enabled: asyncio.create_task(
            #         self.trading_app.start_autotrading()
            #         if enabled
            #         else self.trading_app.stop_autotrading()
            #     )
            # )

            self.stack.addWidget(self.terminal)
            self.stack.setCurrentWidget(self.terminal)

        except Exception as e:

            QMessageBox.critical(
                self,
                "Initialization Failed",
                str(e)
            )

            self.dashboard.hide_loading()

    # ======================================================
    # Cleanup Helper
    # ======================================================

    async def _cleanup_session(self):

        if self.trading_app:
            await self.trading_app.shutdown()
            self.trading_app = None

        if self.terminal:
            self.stack.removeWidget(self.terminal)
            self.terminal.deleteLater()
            self.terminal = None

    # ======================================================
    # Logout
    # ======================================================

    async def logout(self):

        try:
            await self._cleanup_session()

        finally:
            self.stack.setCurrentWidget(self.dashboard)
            self.dashboard.setEnabled(True)
            self.dashboard.connect_button.setText("Connect")
