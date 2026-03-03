import asyncio

import pandas as pd
from PySide6.QtCore import QObject

from sopotek_trading.backend.analytics.performance_engine import PerformanceEngine
from sopotek_trading.backend.broker.broker import Broker
from sopotek_trading.backend.broker.broker_factory import BrokerFactory
from sopotek_trading.backend.core.multi_symbol_orchestrator import MultiSymbolOrchestrator
from sopotek_trading.backend.core.trading_engine import TradingEngine

from sopotek_trading.backend.execution.execution_manager import ExecutionManager
from sopotek_trading.backend.market.binance_web_socket import BinanceWebSocket
from sopotek_trading.backend.market.candle_buffer import CandleBuffer
from sopotek_trading.backend.portfolio.portfolio import Portfolio
from sopotek_trading.backend.portfolio.portfolio_manager import PortfolioManager
from sopotek_trading.backend.quant.ml.ml_signal import MLSignal
from sopotek_trading.backend.risk.risk_engine import RiskEngine
from sopotek_trading.backend.strategy.strategy import Strategy


class SopotekTrading(QObject):


    def __init__(self, config,controller):
        super().__init__()

        self.controller = controller
        self.logger=controller.logger
        self.ticker_signal = controller.ticker_signal
        self.equity_signal = controller.equity_signal
        self.candle_signal = controller.candle_signal
        self.trade_signal = controller.trade_signal
        self.connection_signal =controller.connection_signal
        self.orderbook_signal = controller.orderbook_signal



        self.config = config
        self.limit = config["limit"] or 1000
        self.equity_refresh = config['equity_refresh'] or 60

        self.strategy_debug_signal = controller.strategy_debug_signal



        self.time_frame = config.get("time_frame", "1h")
        self.symbols = config.get("symbols", [])[:5]

        self.running = False
        self.autotrading_enabled = False
        self.model_trained = {}
        self.spread_pct=0
        self.performance_engine=PerformanceEngine(self.controller)




        adapter = BrokerFactory.create(config, logger=self.logger)
        self.broker = Broker(adapter, logger=self.logger,controller=self.controller)

        self.execution_manager = ExecutionManager(
            broker=self.broker,
            logger=self.logger
        )

        self.risk_engine = RiskEngine(self.broker, 0.0)
        self.portfolio = Portfolio(self.broker)
        self.portfolio_manager = PortfolioManager(
            self.broker,
            self.portfolio,
            self.risk_engine
        )

        self.ml_model = MLSignal()
        self.candle_buffer = CandleBuffer(max_length=500)

        self.ws_manager = None
        self.current_equity = 0.04
        self.strategy = Strategy(controller=self.controller)
        self.engine=TradingEngine(controller=self.controller,strategy=self.strategy,
                                  risk_engine=self.risk_engine,portfolio=self.portfolio,
                                  execution_manager=self.execution_manager,
                                  timeframe=self.time_frame,
                                  limit=self.limit,broker=self.broker,symbols=self.symbols)

        self.orchestrator=MultiSymbolOrchestrator(engine=self.engine, symbols=self.symbols,
                                                  candle_buffer=self.candle_buffer,
                                                  logger=self.logger, controller=self.controller)

        self.logger.info("Sopotek Trading System Ready")

    async def initialize(self):

        try:
            self.connection_signal.emit("connecting")

            await self.broker.connect()
            await self.execution_manager.start()

            balance = await self.broker.fetch_balance()
            self.current_equity = balance["equity"]

            await self.risk_engine.update_equity(self.current_equity)

            self.running = True

            asyncio.create_task(self._balance_scheduler())

            self.ws_manager = BinanceWebSocket(
                self.symbols,
                self.time_frame,
                self._on_ws_candle,
                self._on_ticker_callback
            )

            asyncio.create_task(self.ws_manager.start())

            self.connection_signal.emit("connected")

        except Exception as e:
            self.connection_signal.emit("disconnected")
            raise e

    async def shutdown(self):

        self.logger.info("Shutting down system...")
        self.running = False
        self.autotrading_enabled = False

        if self.ws_manager:
            self.ws_manager.stop()

        await self.execution_manager.shutdown()
        await self.broker.close()

        self.connection_signal.emit("disconnected")
        self.logger.info("Shutdown complete.")

    async def _balance_scheduler(self):

        while self.running:
            try:
                balance = await self.broker.fetch_balance()
                self.current_equity = balance["equity"]
                self.equity_signal.emit(self.current_equity)
            except Exception as e:
                self.logger.error(f"Balance scheduler error: {e}")

            await asyncio.sleep(30)

    async def _on_ws_candle(self, symbol: str, candle: dict):
        """
        WebSocket candle handler.
        Receives closed candle data from exchange.
        """

        try:
         # ----------------------------
        # Normalize Symbol
        # ----------------------------
         if "/" not in symbol and symbol.endswith("USDT"):
            symbol = symbol[:-4] + "/USDT"

        # ----------------------------
        # Validate Candle Structure
        # ----------------------------
         required_keys = {"open", "high", "low", "close", "volume"}
         if not required_keys.issubset(candle.keys()):
            self.logger.warning(f"Incomplete candle data for {symbol}")
            return

        # ----------------------------
        # Update Candle Buffer
        # ----------------------------
         self.candle_buffer.update(symbol, candle)
         df = self.candle_buffer.get(symbol)

         if df is None or df.empty:
            return

        # ----------------------------
        # Emit to UI
        # ----------------------------
         self.candle_signal.emit(symbol, df.copy())

        # ----------------------------
        # Ensure Minimum History
        # ----------------------------
         if len(df) < 120:
            return

        # ----------------------------
        # Train Model (Once Per Symbol)
        # ----------------------------
         if not self.model_trained.get(symbol, False):
            try:
                self.ml_model.train(df)
                self.model_trained[symbol] = True
                self.logger.info(f"Model trained for {symbol}")
            except Exception as e:
                self.logger.error(f"Training error for {symbol}: {e}")
            return

        # ----------------------------
        # Trading Execution
        # ----------------------------
         if self.autotrading_enabled:
             asyncio.create_task(
                self.run_trade(symbol, df.copy())
            )

        except Exception as e:
         self.logger.error(f"WS candle error ({symbol}): {e}")
    async def _on_ticker_callback(self, symbol: str, bid: float, ask: float):
     """
        Handles real-time ticker updates (bid/ask).
        """

     try:
        # ---------------------------------
        # Normalize symbol
        # ---------------------------------
        if "/" not in symbol and symbol.endswith("USDT"):
            symbol = symbol[:-4] + "/USDT"

        # ---------------------------------
        # Validate numbers
        # ---------------------------------
        bid = float(bid)
        ask = float(ask)

        if bid <= 0 or ask <= 0:
            return

        # ---------------------------------
        # Calculate derived values
        # ---------------------------------
        mid_price = (bid + ask) / 2
        spread = ask - bid
        spread_pct = (spread / mid_price) * 100 if mid_price else 0
        self.spread_pct=spread_pct

        # ---------------------------------
        # Emit to UI
        # ---------------------------------
        self.ticker_signal.emit(symbol, bid, ask)

        # ---------------------------------
        # Optional: Feed strategy live price
        # ---------------------------------
        # If you later want ultra-low latency trading,
        # you can use mid_price here instead of candle close.

        # Example:
        # if self.autotrading_enabled:
        #     await self.run_tick_trade(symbol, mid_price)

     except Exception as e:
        self.logger.error(f"Ticker callback error ({symbol}): {e}")


    # ======================================================
# AUTOTRADING CONTROL
# ======================================================

    async def start_autotrading(self, symbols):

     if not symbols:
        return

     self.autotrading_enabled = True
     self.symbols = symbols

     self.logger.info(f"AutoTrading enabled for {symbols}")

     await self.orchestrator.shutdown()

     self.orchestrator = MultiSymbolOrchestrator(
        engine=self.engine,
        symbols=self.symbols,
        candle_buffer=self.candle_buffer,
        logger=self.logger,
        controller=self.controller
    )

     asyncio.create_task(self.orchestrator.start())





    async def stop_autotrading(self):
        self.autotrading_enabled = False
        await self.orchestrator.shutdown()
        self.logger.info("AutoTrading disabled")

    async def run_trade(self, symbol: str, df):

     try:
        # ---------------------------------
        # 1️⃣ Prediction
        # ---------------------------------


        analysis = self.ml_model.predict(df)

        signal = analysis.get("signal", "HOLD").upper()
        entry_price = float(analysis.get("current_price", 0))
        confidence = float(analysis.get("confidence", 0.5))
        debug_data = {
            "symbol": symbol,
            "signal": signal,
            "entry_price": entry_price,
            "confidence": confidence,
            "reason": analysis.get("reason", "ML prediction"),
        }

        if signal not in ["BUY", "SELL"]:
            debug_data["status"] = "SKIPPED"
            self.strategy_debug_signal.emit(debug_data)
            return

        if entry_price <= 0:
            self.logger.warning(f"Insufficient data for {symbol} price is {entry_price}")
            return

        # ---------------------------------
        # 2️⃣ Volatility-based Stop
        # ---------------------------------
        volatility = (
            df["close"]
            .pct_change()
            .rolling(20)
            .std()
            .iloc[-1]
        )

        volatility = float(volatility) if not pd.isna(volatility) else 0.01

        stop_distance = entry_price * volatility * 2

        stop_price = (
            entry_price - stop_distance
            if signal == "BUY"
            else entry_price + stop_distance
        )

        # ---------------------------------
        # 3️⃣ Risk Engine Position Size
        # ---------------------------------
        await self.risk_engine.update_equity(self.current_equity)

        size = self.risk_engine.position_size(
            entry_price=entry_price,
            stop_price=stop_price,
            confidence=confidence,
            volatility=volatility
        )
        debug_data.update({
            "volatility": volatility,
            "stop_price": stop_price,
            "size": size
        })

        if size <= 0:
            debug_data["status"] = "REJECTED_RISK"
            self.strategy_debug_signal.emit(debug_data)
            return
        if self.portfolio.has_position(symbol):
            self.logger.warning(f"Position {symbol} exists")
            return

        # ---------------------------------
        # 4️⃣ Execute Trade
        # ---------------------------------
        result = await self.execution_manager.execute_trade(
            user_id="system",
            symbol=symbol,
            side=signal.lower(),
            amount=size,
            order_type=self.config.get("order_type", "market"),
            price=entry_price
        )

        if not result:
            self.logger.info(f"{symbol}: no trade")

            return
        debug_data["status"] = "EXECUTED"
        self.strategy_debug_signal.emit(debug_data)

        # ---------------------------------
        # 5️⃣ Portfolio Update
        # ---------------------------------
        self.portfolio_manager.update_fill(
            symbol=symbol,
            side=signal,
            quantity=size,
            price=entry_price
        )

        # ---------------------------------
        # 6️⃣ Emit UI Trade Event
        # ---------------------------------
        trade_data = {
            "symbol": symbol,
            "side": signal,
            "price": entry_price,
            "size": size,
            "confidence": confidence,
            "volatility": volatility
        }

        self.trade_signal.emit(trade_data)

        # ---------------------------------
        # 7️⃣ Performance Recording (Optional)
        # ---------------------------------
        # If you use PerformanceEngine:
        self.performance_engine.record_trade(trade_data)

        self.logger.info(
            f"TRADE EXECUTED | {symbol} | {signal} | {size}"
        )

     except Exception as e:
        self.logger.error(f"run_trade error ({symbol}): {e}")