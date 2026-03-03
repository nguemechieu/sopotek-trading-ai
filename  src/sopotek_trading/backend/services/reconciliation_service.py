import asyncio


class ReconciliationService:

    def __init__(self, broker, portfolio, logger):
        self.broker = broker
        self.portfolio = portfolio
        self.logger = logger
        self.running = True

    async def start(self):
        asyncio.create_task(self._loop())

    async def _loop(self):
        while self.running:
            try:
                live_positions = await self.broker.fetch_positions()
                self.portfolio.sync(live_positions)
            except Exception as ex:
                self.logger.exception("Reconciliation error",ex)

            await asyncio.sleep(30)

    async def shutdown(self):
        self.running = False