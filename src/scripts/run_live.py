import asyncio
import logging
import sys
from pathlib import Path


from src.engines.trading_engine import TradingEngine
from event_bus.event_bus import EventBus
from execution.execution_manager import ExecutionManager
from portfolio.portfolio_manager import PortfolioManager
from strategy.momentum_strategy import MomentumStrategy
from broker.broker_factory import BrokerFactory
from core.multi_symbol_orchestrator import MultiSymbolOrchestrator
from engines.market_data_engine import MarketDataEngine
from engines.risk_engine import RiskEngine

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))



logging.basicConfig(level=logging.INFO)


async def main():

    # ===============================
    # BROKER CONFIG
    # ===============================

    broker_config = {
        "type": "crypto",
        "exchange": "binanceus",
        "api_key": "5VnocTRZTCkGetIP6o5bvot7AS6rKvH9LzJegvzT33IeXlpGyDGdcZYxaRiws6RC",
        "secret": "Smpi0umS83da9cVuF7YH7wD4CGkMKgIrs1nohscr4On1g230ScCy25PZhLhgtCod"
    }

    broker = BrokerFactory.create(broker_config)

    await broker.connect()

    # ===============================
    # COMPONENTS
    # ===============================
    event_bus = EventBus()

    strategy = MomentumStrategy(event_bus=event_bus)

    risk_engine = RiskEngine()

    execution = ExecutionManager(broker)

    portfolio = PortfolioManager()

    market_data_engine = MarketDataEngine(broker, event_bus)

    engine = TradingEngine(
        market_data_engine=market_data_engine,
        strategy=strategy,
        risk_engine=risk_engine,
        execution_manager=execution,
        portfolio_manager=portfolio
    )

    orchestrator = MultiSymbolOrchestrator(engine)

    await orchestrator.start()


if __name__ == "__main__":

    asyncio.run(main())