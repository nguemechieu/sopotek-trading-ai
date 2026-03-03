import asyncio
import logging

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from sopotek_trading.backend.sopotek_trading import SopotekTrading
from sopotek_trading.frontend.ui.dashboard import Dashboard
from sopotek_trading.frontend.ui.trading_terminal import TradingTerminal


class AppController(QMainWindow):

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Sopotek Trading Platform")
        self.resize(1600, 900)

        self.trade_history = []

        # ================================
        # Central Stack
        # ================================
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = Dashboard()
        self.stack.addWidget(self.dashboard)

        self.trading_app = None
        self.terminal = None

        self.dashboard.login_success.connect(
            lambda config: asyncio.create_task(
                self.initialize_trading(config)
            )
        )

    # ======================================================
    # Initialize Trading System
    # ======================================================

    async def initialize_trading(self, config):

        try:
            self.dashboard.setEnabled(False)
            self.dashboard.connect_button.setText("Connecting...")

            # Clean old session
            await self._cleanup_session()

            # Create backend
            self.trading_app = SopotekTrading(config)
            await self.trading_app.initialize()

            # Create terminal
            self.terminal = TradingTerminal(self.trading_app)

            self.terminal.logout_requested.connect(
                lambda: asyncio.create_task(self.logout())
            )
            self.terminal.autotrade_toggle.connect(
                lambda enabled: asyncio.create_task(
                    self.trading_app.start_autotrading()
                    if enabled
                    else self.trading_app.stop_autotrading()
                )
            )

            self.stack.addWidget(self.terminal)
            self.stack.setCurrentWidget(self.terminal)

        except Exception as e:

            QMessageBox.critical(
                self,
                "Initialization Failed",
                str(e)
            )

            self.dashboard.setEnabled(True)
            self.dashboard.connect_button.setText("Connect")

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