import asyncio
import logging

from manager.portfolio_manager import PortfolioManager
from execution.execution_manager import ExecutionManager
from strategy.strategy_registry import StrategyRegistry
from engines.risk_engine import RiskEngine
from execution.order_router import OrderRouter
from event_bus.event_bus import EventBus
from core.multi_symbol_orchestrator import MultiSymbolOrchestrator


class SopotekTrading:

    def __init__(self, controller=None):

        self.controller = controller
        self.logger = logging.getLogger(__name__)

        # =========================
        # BROKER
        # =========================

        self.broker = getattr(controller, "broker", None)
        self.broker = getattr(controller, "broker", None)

        if self.broker is None:
          raise RuntimeError("Broker not initialized")

        if hasattr(self.broker, "exchange"):
          pass
        else:
         raise RuntimeError("Controller broker is not a valid broker instance")
        self.symbols = getattr(controller, "symbols", ["BTC/USDT", "ETH/USDT"])


        if self.broker is None:
            raise RuntimeError("Broker not initialized")

        # =========================
        # CORE COMPONENTS
        # =========================

        self.strategy = StrategyRegistry()

        self.event_bus = EventBus()

        self.portfolio = PortfolioManager(event_bus=self.event_bus)

        self.router = OrderRouter(broker=self.broker)

        self.execution_manager = ExecutionManager(
            broker=self.broker,
            event_bus=self.event_bus,
            router=self.router
        )

        self.risk_engine = None
        self.orchestrator = None

        # =========================
        # SYSTEM SETTINGS
        # =========================

        self.time_frame = "1d"
        self.limit = 1000
        self.running = False

        self.logger.info("Sopotek Trading System initialized")

    # ==========================================
    # START SYSTEM
    # ==========================================

    async def start(self):

        if self.broker is None:
            raise RuntimeError("Broker not initialized")



        balance = getattr(self.controller, "balances",...)
        equity = 12#balance.get("total", {}).get("USDT", 10)



        self.risk_engine = RiskEngine(
            account_equity=equity,
            max_portfolio_risk=100,
            max_risk_per_trade=50,
            max_position_size_pct=25,
            max_gross_exposure_pct=30
        )

        self.orchestrator = MultiSymbolOrchestrator(controller=self.controller,
            broker=self.broker,
            strategy=self.strategy,
            execution_manager=self.execution_manager,
            risk_engine=self.risk_engine
        )


        await self.orchestrator.start(symbols=self.symbols)

        self.logger.info(f"Loaded {len(self.symbols)} symbols")

        self.running = True

        await self.run()

    # ==========================================
    # MAIN TRADING LOOP
    # ==========================================

    async def run(self):

        self.logger.info("Trading loop started")

        while self.running:

            try:

                for symbol in self.symbols[:100]:

                    candles = await self.broker.fetch_ohlcv(
                        symbol,
                        timeframe=self.time_frame,
                        limit=self.limit
                    )

                    signal = self.strategy.generate_ai_signal(candles)

                    if signal:
                        await self.process_signal(symbol, signal)

                await asyncio.sleep(5)

            except Exception:
                self.logger.exception("Trading loop error")

    # ==========================================
    # PROCESS SIGNAL
    # ==========================================

    async def process_signal(self, symbol, signal):

        side = signal["side"]
        price = signal.get("price")
        amount = signal["amount"]

        allowed = self.risk_engine.validate_trade(symbol, amount)

        if not allowed:

            self.logger.warning("Trade rejected by risk engine")

            return

        order = await self.execution_manager.execute(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price
        )

        self.portfolio.update(order)

    # ==========================================
    # STOP SYSTEM
    # ==========================================

    async def stop(self):

        self.logger.info("Stopping trading system")

        self.running = False

        if self.broker:

            await self.broker.close()