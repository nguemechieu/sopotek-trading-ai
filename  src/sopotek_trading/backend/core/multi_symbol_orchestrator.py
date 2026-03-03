import asyncio


class MultiSymbolOrchestrator:

    def __init__(self, engine, symbols, candle_buffer, logger, controller):
        self.engine = engine
        self.symbols = symbols
        self.candle_buffer = candle_buffer
        self.logger = logger
        self.controller = controller
        self.running = True

    async def start(self):

        while self.running:

            tasks = [
                self._process_symbol(symbol)
                for symbol in self.symbols
            ]

            await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(1)

    async def _process_symbol(self, symbol):

        try:
            result = await self.engine.on_market_tick(
                symbol,
                self.candle_buffer
            )

            if result:

                # 🔥 Emit strategy debug to UI
                if "debug" in result:
                    self.controller.strategy_debug_signal.emit(
                        result["debug"]
                    )

        except Exception as e:
            self.logger.error(
                f"Error processing {symbol}: {e}"
            )

    async def shutdown(self):
        self.running = False