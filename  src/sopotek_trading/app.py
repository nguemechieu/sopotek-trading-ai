import logging
import uuid

from sopotek_trading.executions.execution_manager import ExecutionManager
from sopotek_trading.executions.broker_factory import BrokerFactory
from sopotek_trading.risk.risk_core import RiskCore
from sopotek_trading.risk.portfolio.portofolio_manager  import PortfolioManager


logger = logging.getLogger(__name__)


class SopotekTrading:

    def __init__(self, exchange_name, api_key, secret):

        logger.info("Initializing Sopotek Trading System...")

        # Broker
        self.broker = BrokerFactory.create(
            exchange_name=exchange_name,
            api_key=api_key,
            secret=secret
        )

        # Portfolio
        self.portfolio = PortfolioManager()

        # Risk Engine
        self.risk_engine = RiskCore()

        # Execution Manager
        self.execution_manager = ExecutionManager(
            broker=self.broker,
            risk_engine=self.risk_engine,
            portfolio=self.portfolio
        )

        logger.info("Sopotek Trading System Ready")

    # -------------------------------------------------
    # Lifecycle
    # -------------------------------------------------
    def start(self):
        logger.info("Starting Sopotek Trading System")

    def stop(self):
        logger.info("Stopping Sopotek Trading System")

    # -------------------------------------------------
    # Submit Trade (Correct Way)
    # -------------------------------------------------
    def run_trade(self, symbol, side, amount, order_type="market"):

        user_id = str(uuid.uuid4())  # temporary mock user

        return self.execution_manager.execute_trade(
            user_id=user_id,
            symbol=symbol,
            side=side.lower(),
            amount=amount,
            order_type=order_type
        )