from __future__ import annotations

import logging

from sopotek.agents import (
    BreakoutAgent,
    ExecutionMonitorAgent,
    MarketAnalystAgent,
    MeanReversionAgent,
    MLAgent,
    RiskManagerAgent,
    StrategySelectorAgent,
    TrendFollowingAgent,
)
from sopotek.broker.base import BaseBroker
from sopotek.core.event_bus import AsyncEventBus, InMemoryEventStore
from sopotek.core.event_types import EventType
from sopotek.engines import (
    EventDrivenBacktestEngine,
    ExecutionEngine,
    FeatureEngine,
    MarketDataEngine,
    MultiAgentStrategyEngine,
    PerformanceEngine,
    PortfolioEngine,
    RiskEngine,
    StrategyEngine,
    StrategyRegistry,
    TradeFeedbackEngine,
)
from sopotek.ml import MLFilterEngine, TradeOutcomeTrainingPipeline
from sopotek.storage import QuantPersistenceRecorder, QuantRepository


class SopotekRuntime:
    """Composable v2 runtime for the desktop trading system."""

    def __init__(
        self,
        broker: BaseBroker,
        *,
        event_bus: AsyncEventBus | None = None,
        starting_equity: float = 100000.0,
        candle_timeframes: list[str] | None = None,
        enable_default_agents: bool = True,
        enable_ml_filter: bool = True,
        ml_probability_threshold: float = 0.55,
        persistence_recorder: QuantPersistenceRecorder | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger("SopotekRuntime")
        self.bus = event_bus or AsyncEventBus(store=InMemoryEventStore(), enable_persistence=True, logger=self.logger)
        self.broker = broker
        self.registry = StrategyRegistry()
        self.quant_repository = QuantRepository()
        self.ml_pipeline = TradeOutcomeTrainingPipeline()

        self.market_data = MarketDataEngine(broker, self.bus, candle_timeframes=candle_timeframes or ["1m"])
        self.feature_engine = FeatureEngine(self.bus, timeframe=(candle_timeframes or ["1m"])[0])
        self.strategy_engine = StrategyEngine(self.bus, self.registry)
        self.multi_agent_strategy_engine = MultiAgentStrategyEngine(self.bus)
        self.portfolio_engine = PortfolioEngine(self.bus, starting_cash=starting_equity)
        self.risk_engine = RiskEngine(self.bus, starting_equity=starting_equity)
        self.performance_engine = PerformanceEngine(self.bus)
        self.feedback_engine = TradeFeedbackEngine(self.bus, default_timeframe=(candle_timeframes or ["1m"])[0])
        self.ml_filter = MLFilterEngine(
            self.bus,
            self.ml_pipeline,
            threshold=ml_probability_threshold,
            allow_passthrough=True,
        ) if enable_ml_filter else None
        execution_trigger = EventType.MODEL_APPROVED if self.ml_filter is not None else EventType.RISK_APPROVED
        self.execution_engine = ExecutionEngine(broker, self.bus, listen_event_type=execution_trigger)
        self.persistence_recorder = persistence_recorder or QuantPersistenceRecorder(
            self.bus,
            quant_repository=self.quant_repository,
            exchange_name=getattr(broker, "exchange_name", "paper"),
        )
        self.backtest_engine = EventDrivenBacktestEngine(self)

        self.market_analyst = MarketAnalystAgent()
        self.strategy_selector = StrategySelectorAgent()
        self.risk_manager = RiskManagerAgent(self.risk_engine)
        self.execution_monitor = ExecutionMonitorAgent()

        for agent in (
            self.market_analyst,
            self.strategy_selector,
            self.risk_manager,
            self.execution_monitor,
        ):
            agent.attach(self.bus)

        self.default_strategy_agents = []
        if enable_default_agents:
            self.default_strategy_agents = [
                self.register_agent(TrendFollowingAgent(timeframe=(candle_timeframes or ["1m"])[0], default_quantity=1.0)),
                self.register_agent(MeanReversionAgent(timeframe=(candle_timeframes or ["1m"])[0], default_quantity=1.0)),
                self.register_agent(BreakoutAgent(timeframe=(candle_timeframes or ["1m"])[0], default_quantity=1.0)),
                self.register_agent(MLAgent(self.ml_pipeline, timeframe=(candle_timeframes or ["1m"])[0], default_quantity=1.0)),
            ]

    def register_strategy(self, strategy, *, active: bool = True, symbols: list[str] | None = None):
        return self.registry.register(strategy, active=active, symbols=symbols)

    def register_agent(self, agent):
        return self.multi_agent_strategy_engine.register(agent)

    async def start(self, symbols: list[str]) -> None:
        self.bus.run_in_background()
        await self.market_data.start(symbols)

    async def stop(self) -> None:
        await self.market_data.stop()
        await self.bus.shutdown()

    def retrain_from_feedback(self):
        feedback_rows = self.quant_repository.load_feedback()
        if len(feedback_rows) < 4:
            return None
        try:
            return self.ml_pipeline.fit_from_feedback(feedback_rows)
        except ValueError:
            return None
