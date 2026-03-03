import asyncio


class MultiSymbolOrchestrator:

    def __init__(self, engine, symbols, candle_buffer, logger):
        self.engine = engine
        self.symbols = symbols
        self.candle_buffer = candle_buffer
        self.logger = logger
        self.running = True

    async def start(self):
        while self.running:
            tasks = [
                self.engine.on_market_tick(symbol, self.candle_buffer)
                for symbol in self.symbols
            ]

            await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(1)  # throttle loop

    async def shutdown(self):
        self.running = False