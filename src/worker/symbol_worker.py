# core/symbol_worker.py

import asyncio
import logging


class SymbolWorker:

    def __init__(self, symbol, broker, strategy, execution_manager,timeframe,limit):
        self.logger=logging.getLogger("SymbolWorker")

        self.symbol = symbol
        self.broker = broker
        self.strategy = strategy
        self.execution_manager = execution_manager
        self.timeframe = timeframe
        self.limit = limit
        self.running = True


    async def run(self):

        while self.running:

            try:

                candles = await self.broker.fetch_ohlcv(
                    self.symbol,
                    timeframe=self.timeframe,
                    limit=self.limit
                )

                signal = self.strategy.generate_signal(candles)

                if signal:

                    await self.execution_manager.execute(
                        symbol=self.symbol,
                        side=signal["side"],
                        amount=signal["amount"],
                        price=signal.get("price")
                    )

                await asyncio.sleep(2)

            except Exception as e:
                self.logger.error(f"Worker error {self.symbol}: {e}")