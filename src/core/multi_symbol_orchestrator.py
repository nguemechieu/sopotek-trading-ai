import asyncio

from core.scheduler import Scheduler
from core.system_state import SystemState
from worker.symbol_worker import SymbolWorker
from  engines.trading_engine import TradingEngine
from  manager.portfolio_manager import PortfolioManager
from  event_bus.event_bus import  EventBus
from engines.market_data_engine import MarketDataEngine
class MultiSymbolOrchestrator:

    def __init__(self,controller, broker, strategy, execution_manager, risk_engine):
        self.controller = controller

        self.broker = broker
        self.event_bus=EventBus()
        self.strategy = strategy
        self.execution_manager = execution_manager
        self.portfolio_manager=PortfolioManager(self.event_bus)
        self.market_data_engine=MarketDataEngine(self.broker,self.event_bus)
        self.risk_engine=risk_engine

        self.engine = TradingEngine( self.market_data_engine,
                                     self.strategy,
                                     self.risk_engine,
                                     self.execution_manager,
                                     self.portfolio_manager)

        self.state = SystemState()

        self.scheduler = Scheduler()

        self.workers = []

    async def start(self, symbols=None):

        if symbols is None:

            raise RuntimeError("No symbols provided")

        tasks = []
        timeframe="1h"
        limit =1000
        for symbol in symbols:

            worker = SymbolWorker(
                symbol,
                self.broker,
                self.strategy,
                self.execution_manager,timeframe,limit
            )

            self.workers.append(worker)

            tasks.append(
                asyncio.create_task(worker.run())
            )

        await asyncio.gather(*tasks)




    # ===================================
    # STOP SYSTEM
    # ===================================

    async def shutdown(self):
        self.state.stop()

        await self.engine.stop()

        print("Trading system stopped")
