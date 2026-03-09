import asyncio
import logging
import os
import sys
import traceback

import pandas as pd
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox
from alpaca.broker import Portfolio

from broker.rate_limiter import RateLimiter
from broker.broker_factory import BrokerFactory
from manager.broker_manager import BrokerManager

from core.sopotek_trading import SopotekTrading
from market_data.candle_buffer import CandleBuffer

from frontend.ui.dashboard import Dashboard
from frontend.ui.terminal import Terminal
from  frontend.ui.panels.orderbook_panel import OrderBookPanel
from  market_data.ticker_stream import  TickerStream


class AppController(QMainWindow):

    # =========================================================
    # SIGNALS
    # =========================================================

    symbols_signal = Signal(str, list)
    candle_signal = Signal(str, object)
    equity_signal = Signal(float)

    trade_signal = Signal(dict)
    ticker_signal = Signal(str, float, float)
    connection_signal = Signal(str)
    orderbook_signal = Signal(str, list, list)

    strategy_debug_signal = Signal(dict)
    autotrade_toggle = Signal(bool)

    logout_requested = Signal(str)
    training_status_signal = Signal(str, str)

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self):

        super().__init__()

        self.controller = self

        # -----------------------------------------------------
        # LOGGER
        # -----------------------------------------------------

        self.logger = logging.getLogger("AppController")
        self.logger.setLevel(logging.INFO)


        os.makedirs("logs", exist_ok=True)

        if not self.logger.handlers:
            self.logger.addHandler(logging.StreamHandler(sys.stdout))
            self.logger.addHandler(logging.FileHandler("logs/app.log"))

        # -----------------------------------------------------
        # CORE COMPONENTS
        # -----------------------------------------------------

        self.broker_manager = BrokerManager()
        self.rate_limiter = RateLimiter()

        self.broker = None
        self.trading_system = None
        self.terminal = None
        self.orchestrator=None

        # -----------------------------------------------------
        # SYSTEM CONFIG
        # -----------------------------------------------------

        self.max_portfolio_risk = 1700
        self.max_risk_per_trade = 20
        self.max_position_size_pct = 100
        self.max_gross_exposure_pct = 34
        self.confidence=0
        self.volatility = 0
        self.order_type="limit"
        self.time_frame = "1h"
        self.portfolio=None
        self.ai_signal=None
        self.balances=None


        self.ticker_stream=TickerStream()

        self.limit = 1000
        self.initial_capital = 10000

        self.candle_buffer = CandleBuffer(max_length=self.limit)
        self.symbols = ["BTC/USDT", "ETH/USDT","XLM/USDT"]



        self.connected = False
        self.config = None

        # -----------------------------------------------------
        # SETUP
        # -----------------------------------------------------

        try:
            self._setup_paths()
            self._setup_data()
            self._setup_ui(self.controller)

        except Exception as e:
            traceback.print_exc()
            self.logger.error(e)

    # =========================================================
    # PATHS
    # =========================================================

    def _setup_paths(self):

        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

    # =========================================================
    # DATA
    # =========================================================

    def _setup_data(self):

        self.historical_data = pd.DataFrame(
            columns=[
                "symbol",
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

    # =========================================================
    # UI
    # =========================================================

    def _setup_ui(self,controller):

        self.setWindowTitle("Sopotek Trading AI Platform")
        self.resize(1600, 900)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = Dashboard(controller)

        self.stack.addWidget(self.dashboard)

        # Qt → asyncio bridge
        self.dashboard.login_requested.connect(
            lambda config: asyncio.create_task(self.handle_login(config))
        )

    # =========================================================
    # LOGIN
    # =========================================================

    async def handle_login(self, config):

        try:

            if config is None:
                raise RuntimeError("Invalid configuration received")

            if config.broker is None:
                raise RuntimeError("Broker configuration missing")

            self.dashboard.show_loading()
            self.config = config
            broker_type = config.broker.type
            exchange = config.broker.exchange

            if not broker_type:
                raise RuntimeError("Broker type missing")

            # -------------------------------------------------
            # CREATE BROKER (ONLY ONCE)
            # -------------------------------------------------
            self.logger.info(f"Initializing broker {exchange}")
            self.broker = BrokerFactory.create(config)

            if self.broker is None:
                    raise RuntimeError("Broker creation failed")
            await self.broker.connect()
            self.symbols = await self.broker.fetch_symbol()
            self.balances =  await self.broker.fetch_balance() or await self.broker.fetch_balance().get("balances", {})

            self.logger.info(f"Initializing trading system {exchange}-{broker_type}-{self.balances}")

            self.logger.info(f"Broker {self.broker} connected")

            # -------------------------------------------------
            # START TRADING SYSTEM
            # -------------------------------------------------
            if self.trading_system is None:
                self.trading_system = SopotekTrading(config)
            await self.initialize_trading()

            self.dashboard.hide_loading()

        except Exception as e:

            traceback.print_exc()

            self.dashboard.hide_loading()

            QMessageBox.critical(self, "Initialization Failed", str(e))

    # =========================================================
    # INITIALIZE TERMINAL
    # =========================================================

    async def initialize_trading(self):

        try:

            await self._cleanup_session()

            self.terminal = Terminal(self.controller)

            self.stack.addWidget(self.terminal)
            self.stack.setCurrentWidget(self.terminal)
            self.terminal.logout_requested.connect( lambda: asyncio.create_task(self.logout()))

        except Exception as e:

            QMessageBox.critical(self, "Initialization Failed", str(e))

    # =========================================================
    # CLEANUP
    # =========================================================

    async def _cleanup_session(self):

        try:

            if self.trading_system:

                await self.trading_system.stop()

                self.trading_system = None

            if self.terminal:

                self.stack.removeWidget(self)

                self.terminal.deleteLater()

                self.terminal = None

        except Exception as e:

            self.logger.error(f"Cleanup error: {e}")

    # =========================================================
    # LOGOUT
    # =========================================================

    async def logout(self):

        try:

            await self._cleanup_session()

            if self.broker:
                await self.broker.close()

                self.broker = None
                self.connected = False

        finally:

            self.stack.setCurrentWidget(self.dashboard)

            self.dashboard.setEnabled(True)
            self.dashboard.connect_button.setText("Connect")