import asyncio


from sopotek_trading.backend.broker.rate_limiter import RateLimiter
from sopotek_trading.backend.market.binance_web_socket import BinanceWebSocket
from sopotek_trading.backend.market.candle_buffer import CandleBuffer
from sopotek_trading.backend.quant.ml.ml_models_manager import MLModelManager


class TradingEngine:

    def __init__(self, controller, broker, strategy, risk_engine, portfolio, execution_manager, symbols, timeframe,
                 limit=1000):

        self.ws_manager = None
        self.controller = controller
        self.logger = controller.logger
        self.logger.info("Trading engine started.")
        self.limit = limit

        # FIXED (no trailing commas)
        self.broker = broker
        self.strategy = strategy
        self.risk_engine = risk_engine
        self.portfolio = portfolio
        self.execution_manager = execution_manager
        self.symbols = symbols
        self.timeframe = timeframe

        self.rate_limiter = RateLimiter()
        self.model_manager = MLModelManager()
        self.candle_buffer = CandleBuffer()

        self.trading_enabled = True
        self.current_equity = 0.0
        self.tasks = []

        self.symbol_locks = {
            symbol: asyncio.Lock()
            for symbol in self.symbols
        }

        for symbol in self.symbols:
            self.model_manager.register_symbol(symbol)

    # -------------------------------------------------
    # START
    # -------------------------------------------------

    async def start(self):

        await self.broker.connect()

        self.tasks.append(
            asyncio.create_task(self._balance_scheduler())
        )

        self.tasks.append(
            asyncio.create_task(self._health_scheduler())
        )

        await self._initial_model_training()

        self.ws_manager = BinanceWebSocket(
            self.symbols,
            self.timeframe,
            self._on_ws_candle,
            self.on_market_tick
        )

        ws_task = asyncio.create_task(self.ws_manager.start())
        self.tasks.append(ws_task)

        self.logger.info("Trading engine started.")

    # -------------------------------------------------
    # WEBSOCKET CALLBACK
    # -------------------------------------------------

    async def _on_ws_candle(self, symbol, candle):

        self.candle_buffer.update(symbol, candle)

        df = self.candle_buffer.get(symbol)

        if df is None or len(df) < 100:
            return

        await self.on_market_tick(symbol, df)

    # -------------------------------------------------
    # MARKET PROCESSING
    # -------------------------------------------------

    async def on_market_tick(self, symbol, df):

        signal = await self.strategy.generate_signal(symbol, df)
        if not signal:
            return

        positions = self.portfolio.get_positions()

        approved, _ = self.risk_engine.validate_trade(signal, positions)
        if not approved:
            return

        size = self.risk_engine.position_size(
            entry_price=signal["entry_price"],
            stop_price=signal["stop_price"],
            confidence=signal["confidence"],
            volatility=signal["volatility"],
        )

        if size <= 0:
            return

        async with self.symbol_locks[symbol]:

            await self.rate_limiter.wait()

            order = await self.execution_manager.execute_trade(
                user_id="system",
                symbol=symbol,
                side=signal["signal"].lower(),
                amount=size,
                order_type="market",
                price=signal["entry_price"],
            )

            if order:
                self.portfolio.update_position(
                    symbol=symbol,
                    side=signal["signal"],
                    quantity=size,
                    price=signal["entry_price"]
                )

    # -------------------------------------------------
    # BALANCE SCHEDULER
    # -------------------------------------------------

    async def _balance_scheduler(self):

        while self.trading_enabled:

            try:
                balance = await self.broker.fetch_balance()

                equity = (
                        balance.get("equity")
                        or balance.get("total")
                        or balance.get("free")
                        or 0.0
                )

                self.current_equity = float(equity)

                await self.risk_engine.update_equity(
                    self.current_equity
                )

                if hasattr(self.controller, "equity_signal"):
                    self.controller.equity_signal.emit(
                        self.current_equity
                    )

            except asyncio.CancelledError:
                break

            except Exception as e:
                self.logger.error(
                    f"Balance scheduler error: {e}"
                )

            await asyncio.sleep(30)

    # -------------------------------------------------
    # HEALTH MONITOR
    # -------------------------------------------------

    async def _health_scheduler(self):

        while self.trading_enabled:

            try:
                start = asyncio.get_event_loop().time()

                await self.broker.ping()

                latency = (
                        asyncio.get_event_loop().time() - start
                )

                if hasattr(self.controller, "connection_signal"):
                    self.controller.connection_signal.emit(
                        "connected"
                    )

                if latency > 2:
                    self.logger.warning(
                        f"High latency: {latency:.2f}s"
                    )

            except asyncio.CancelledError:
                break

            except Exception as e:

                self.logger.error(
                    f"Health check failed: {e}"
                )

                if hasattr(self.controller, "connection_signal"):
                    self.controller.connection_signal.emit(
                        "disconnected"
                    )

                await self._attempt_reconnect()

            await asyncio.sleep(60)

    # -------------------------------------------------
    # RECONNECT
    # -------------------------------------------------

    async def _attempt_reconnect(self):

        try:
            await self.broker.close()
        except Exception:
            pass

        try:
            await self.broker.connect()
            self.logger.info("Reconnected.")
        except Exception as e:
            self.logger.error(
                f"Reconnect failed: {e}"
            )

    # -------------------------------------------------
    # INITIAL TRAINING
    # -------------------------------------------------

    async def _initial_model_training(self):

        self.logger.info("Initial model training...")

        for symbol in self.symbols:

            try:
                df = await self.broker.fetch_ohlcv(
                    symbol,
                    timeframe=self.timeframe,
                    limit=500
                )

                if df is None or len(df) < 200:
                    continue

                self.candle_buffer.set(symbol, df)

                await self.model_manager.train(symbol, df)

            except Exception as e:
                self.logger.error(
                    f"Training failed for {symbol}: {e}"
                )

        self.logger.info("Initial training complete.")

    # -------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------

    async def shutdown(self):

        self.trading_enabled = False

        for task in self.tasks:
            task.cancel()

        await asyncio.gather(
            *self.tasks,
            return_exceptions=True
        )

        if self.ws_manager:
            self.ws_manager.stop()

        await self.broker.close()

        self.logger.info("Trading engine stopped.")

    async def update_equity(self, equity):
        pass