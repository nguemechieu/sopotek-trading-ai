import asyncio
import pickle

from sopotek_trading.backend.core.trading_engine import TradingEngine
from sopotek_trading.backend.market.candle_buffer import CandleBuffer


class TradingOrchestrator:

    def __init__(
            self,
            controller,
            broker,
            strategy,
            risk_engine,
            portfolio,
            execution_manager,
            symbols,
            timeframe="1m",
            equity_refresh=60,
            limit=1000
    ):

        self.controller = controller
        self.logger = controller.logger

        self.broker = broker
        self.symbols = symbols
        self.timeframe = timeframe
        self.equity_refresh = equity_refresh
        self.limit = limit

        self.running = False
        self.tasks = []

        self.candle_buffer = CandleBuffer()

        self.engine = TradingEngine(
            self.controller,
            broker=broker,
            strategy=strategy,
            risk_engine=risk_engine,
            portfolio=portfolio,
            execution_manager=execution_manager,
            symbols=symbols,
            timeframe=timeframe,
            limit=limit
        )





    # -------------------------------------------------
    # START
    # -------------------------------------------------

    async def start(self):

        self.logger.info("Starting orchestrator...")
        self.running = True

        await self.broker.connect()

        self.tasks.append(asyncio.create_task(self.engine.start()))
        self.tasks.append(asyncio.create_task(self._equity_monitor()))


    # -------------------------------------------------
    # WEBSOCKET CALLBACK
    # -------------------------------------------------

    async def _on_ws_candle(self, symbol, candle):

        self.candle_buffer.update(symbol, candle)

        df = self.candle_buffer.get(symbol)

        if df is None:
            return

        await self.engine.on_market_tick(symbol, df)

    # -------------------------------------------------
    # EQUITY MONITOR
    # -------------------------------------------------

    async def _equity_monitor(self):

        while self.running:
            try:
                balance = await self.broker.fetch_balance()
                equity = balance.get("equity")

                await self.engine.update_equity(equity)

                self.logger.info("Equity updated: %.2f", equity)

            except Exception:
                self.logger.exception("Equity refresh failed")

            await asyncio.sleep(self.equity_refresh)

    # -------------------------------------------------
    # STOP
    # -------------------------------------------------

    async def stop(self):

        self.logger.info("Stopping orchestrator...")
        self.running = False

        for task in self.tasks:
            task.cancel()

        await asyncio.gather(*self.tasks, return_exceptions=True)

        await self.broker.close()