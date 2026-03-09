class TradingEngine:

    def __init__(
            self,
            market_data_engine,
            strategy,
            risk_engine,
            execution_manager,
            portfolio_manager
    ):
        self.market_data = market_data_engine

        self.strategy = strategy

        self.risk = risk_engine

        self.execution = execution_manager

        self.portfolio = portfolio_manager

    # ===================================
    # START ENGINE
    # ===================================

    async def start(self):
        await self.market_data.start()

    # ===================================
    # STOP ENGINE
    # ===================================

    async def stop(self):
        await self.market_data.stop()
