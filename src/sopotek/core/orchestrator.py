from __future__ import annotations

import logging

from sopotek.agents import (
    BreakoutAgent,
    ExecutionMonitorAgent,
    InvestorProfile,
    MarketAnalystAgent,
    MeanReversionAgent,
    MLAgent,
    ReasoningAgent,
    RiskManagerAgent,
    StrategySelectorAgent,
    TraderAgent,
    TrendFollowingAgent,
)
from sopotek.broker.base import BaseBroker
from sopotek.core.event_bus import AsyncEventBus, InMemoryEventStore, JsonlEventStore
from sopotek.core.event_types import EventType
from sopotek.core.market_hours_engine import MarketHoursEngine
from sopotek.core.runtime_state_cache import RuntimeStateCache
from sopotek.engines import (
    EventDrivenBacktestEngine,
    ExecutionEngine,
    FeatureEngine,
    MarketDataEngine,
    MultiAgentStrategyEngine,
    PerformanceEngine,
    PortfolioEngine,
    ProfitProtectionEngine,
    RiskEngine,
    StrategyEngine,
    StrategyRegistry,
    TradeFeedbackEngine,
)
from sopotek.ml import MLFilterEngine, TradeOutcomeTrainingPipeline
from sopotek.services import AlertingEngine, MobileDashboardService, TradeJournalAIEngine
from sopotek.storage import FeatureStore, QuantPersistenceRecorder, QuantRepository
from risk.time_stop_engine import TimeStopEngine


class SopotekRuntime:
    """Composable v2 runtime for the desktop trading system."""

    def __init__(
        self,
        broker: BaseBroker,
        *,
        event_bus: AsyncEventBus | None = None,
        starting_equity: float = 100000.0,
        candle_timeframes: list[str] | None = None,
        warmup_on_start: bool | None = None,
        warmup_history_limit: int = 120,
        enable_default_agents: bool = True,
        enable_ml_filter: bool = True,
        enable_profit_protection: bool = True,
        enable_time_stop: bool = True,
        enable_feature_store: bool = True,
        enable_market_hours: bool = True,
        enable_alerting: bool = True,
        enable_mobile_dashboard: bool = True,
        enable_trade_journal_ai: bool = True,
        enable_trader_agent: bool = False,
        ml_probability_threshold: float = 0.55,
        profit_protection_kwargs: dict | None = None,
        time_stop_kwargs: dict | None = None,
        market_hours_kwargs: dict | None = None,
        feature_store_dir: str = "data/feature_store",
        mobile_dashboard_dir: str = "data/mobile_dashboard",
        alerting_kwargs: dict | None = None,
        trade_journal_kwargs: dict | None = None,
        default_asset_type: str | None = None,
        require_high_liquidity_for_forex: bool = False,
        trader_profiles: dict[str, InvestorProfile | dict] | None = None,
        active_trader_profile: str | None = None,
        trader_agent_kwargs: dict | None = None,
        persistence_recorder: QuantPersistenceRecorder | None = None,
        event_store_path: str | None = None,
        persist_events: bool = True,
        restore_runtime_state_on_start: bool = False,
        restore_runtime_state_limit: int | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger("SopotekRuntime")
        self.bus = event_bus or self._build_default_event_bus(
            event_store_path=event_store_path,
            persist_events=persist_events,
            logger=self.logger,
        )
        self.broker = broker
        self.event_store_path = event_store_path
        self.restore_runtime_state_on_start = bool(restore_runtime_state_on_start)
        self.restore_runtime_state_limit = restore_runtime_state_limit
        self.state_cache = RuntimeStateCache().attach(self.bus)
        self.default_asset_type = self._resolve_default_asset_type(broker, fallback=default_asset_type)
        self.candle_timeframes = list(candle_timeframes or ["1m"])
        self.warmup_on_start = bool(enable_trader_agent) if warmup_on_start is None else bool(warmup_on_start)
        self.warmup_history_limit = max(0, int(warmup_history_limit))
        self.registry = StrategyRegistry()
        self.quant_repository = QuantRepository()
        self.ml_pipeline = TradeOutcomeTrainingPipeline()

        self.market_data = MarketDataEngine(broker, self.bus, candle_timeframes=self.candle_timeframes)
        self.feature_engine = FeatureEngine(self.bus, timeframe=self.candle_timeframes[0])
        self.strategy_engine = StrategyEngine(self.bus, self.registry)
        self.multi_agent_strategy_engine = MultiAgentStrategyEngine(self.bus)
        self.portfolio_engine = PortfolioEngine(self.bus, starting_cash=starting_equity)
        self.risk_engine = RiskEngine(
            self.bus,
            starting_equity=starting_equity,
            listen_event_type=EventType.ORDER_EVENT if enable_trader_agent else EventType.SIGNAL,
        )
        self.performance_engine = PerformanceEngine(self.bus)
        self.feedback_engine = TradeFeedbackEngine(self.bus, default_timeframe=self.candle_timeframes[0])
        self.ml_filter = MLFilterEngine(
            self.bus,
            self.ml_pipeline,
            threshold=ml_probability_threshold,
            allow_passthrough=True,
        ) if enable_ml_filter else None
        self.market_hours_engine = MarketHoursEngine(
            default_asset_type=self.default_asset_type,
            logger=self.logger,
            **dict(market_hours_kwargs or {}),
        ) if enable_market_hours else None
        execution_trigger = EventType.MODEL_APPROVED if self.ml_filter is not None else EventType.RISK_APPROVED
        self.execution_engine = ExecutionEngine(
            broker,
            self.bus,
            listen_event_type=execution_trigger,
            market_hours_engine=self.market_hours_engine,
            default_asset_type=self.default_asset_type,
            require_high_liquidity_for_forex=require_high_liquidity_for_forex,
            logger=self.logger,
        )
        self.profit_protection_engine = ProfitProtectionEngine(
            self.bus,
            predictor=self.ml_pipeline,
            risk_engine=self.risk_engine,
            portfolio_engine=self.portfolio_engine,
            logger=self.logger,
            **dict(profit_protection_kwargs or {}),
        ) if enable_profit_protection else None
        self.time_stop_engine = TimeStopEngine(
            self.bus,
            risk_engine=self.risk_engine,
            portfolio_engine=self.portfolio_engine,
            logger=self.logger,
            **dict(time_stop_kwargs or {}),
        ) if enable_time_stop else None
        self.trader_agent = TraderAgent(
            profiles=trader_profiles,
            active_profile_id=active_trader_profile,
            predictor=self.ml_pipeline,
            risk_engine=self.risk_engine,
            market_hours_engine=self.market_hours_engine,
            default_asset_type=self.default_asset_type,
            require_high_liquidity_for_forex=require_high_liquidity_for_forex,
            logger=self.logger,
            **dict(trader_agent_kwargs or {}),
        ) if enable_trader_agent else None
        self.persistence_recorder = persistence_recorder or QuantPersistenceRecorder(
            self.bus,
            quant_repository=self.quant_repository,
            exchange_name=getattr(broker, "exchange_name", "paper"),
        )
        self.trade_journal_ai = TradeJournalAIEngine(
            self.bus,
            quant_repository=self.quant_repository,
            trade_repository=self.persistence_recorder.trade_repository,
            exchange_name=getattr(broker, "exchange_name", "paper"),
            logger=self.logger,
            **dict(trade_journal_kwargs or {}),
        ) if enable_trade_journal_ai else None
        self.mobile_dashboard = MobileDashboardService(self.bus, base_dir=mobile_dashboard_dir) if enable_mobile_dashboard else None
        self.alerting_engine = AlertingEngine(
            self.bus,
            logger=self.logger,
            **dict(alerting_kwargs or {}),
        ) if enable_alerting else None
        self.feature_store = FeatureStore(self.bus, base_dir=feature_store_dir) if enable_feature_store else None
        self.backtest_engine = EventDrivenBacktestEngine(self)

        self.market_analyst = MarketAnalystAgent(timeframe=self.candle_timeframes[0])
        self.reasoning_agent = ReasoningAgent()
        self.strategy_selector = StrategySelectorAgent()
        self.risk_manager = RiskManagerAgent(self.risk_engine)
        self.execution_monitor = ExecutionMonitorAgent()

        for agent in (
            self.market_analyst,
            self.reasoning_agent,
            self.strategy_selector,
            self.risk_manager,
            self.execution_monitor,
            self.trader_agent,
        ):
            if agent is not None:
                agent.attach(self.bus)

        self.default_strategy_agents = []
        if enable_default_agents:
            self.default_strategy_agents = [
                self.register_agent(TrendFollowingAgent(timeframe=self.candle_timeframes[0], default_quantity=1.0)),
                self.register_agent(MeanReversionAgent(timeframe=self.candle_timeframes[0], default_quantity=1.0)),
                self.register_agent(BreakoutAgent(timeframe=self.candle_timeframes[0], default_quantity=1.0)),
                self.register_agent(MLAgent(self.ml_pipeline, timeframe=self.candle_timeframes[0], default_quantity=1.0)),
            ]

    def register_strategy(self, strategy, *, active: bool = True, symbols: list[str] | None = None):
        return self.registry.register(strategy, active=active, symbols=symbols)

    def register_agent(self, agent):
        return self.multi_agent_strategy_engine.register(agent)

    async def start(self, symbols: list[str]) -> None:
        if self.restore_runtime_state_on_start:
            restored = await self.restore_runtime_state(limit=self.restore_runtime_state_limit)
            if restored:
                self.logger.info("Restored runtime state from persisted events count=%s", restored)
        self.bus.run_in_background()
        await self._warmup_runtime(symbols)
        await self.market_data.start(symbols)

    async def stop(self) -> None:
        await self.market_data.stop()
        if self.alerting_engine is not None:
            await self.alerting_engine.close()
        await self.bus.shutdown()

    def retrain_from_feedback(self):
        feedback_rows = self.quant_repository.load_feedback()
        if len(feedback_rows) < 4:
            return None
        try:
            return self.ml_pipeline.fit_from_feedback(feedback_rows)
        except ValueError:
            return None

    async def restore_runtime_state(
        self,
        *,
        limit: int | None = None,
        clear_existing: bool = True,
        event_types: list[str] | None = None,
    ) -> int:
        return await self.state_cache.rebuild_from_bus(
            self.bus,
            event_types=event_types,
            limit=limit,
            clear=clear_existing,
        )

    async def _warmup_runtime(self, symbols: list[str]) -> None:
        if (
            self.trader_agent is None
            or not self.warmup_on_start
            or self.warmup_history_limit <= 0
            or not symbols
        ):
            return
        self.logger.info(
            "Warming TraderAgent from historical candles symbols=%s timeframes=%s limit=%s",
            len(symbols),
            self.candle_timeframes,
            self.warmup_history_limit,
        )
        self.trader_agent.suspend_evaluations()
        try:
            for symbol in symbols:
                for timeframe in self.candle_timeframes:
                    try:
                        await self.market_data.publish_history(
                            symbol,
                            timeframe=timeframe,
                            limit=self.warmup_history_limit,
                        )
                    except Exception:
                        self.logger.exception(
                            "TraderAgent warmup failed for symbol=%s timeframe=%s",
                            symbol,
                            timeframe,
                        )
            await self.bus.queue.join()
        finally:
            self.trader_agent.resume_evaluations()

        for symbol in symbols:
            await self.trader_agent.queue_evaluation(
                symbol,
                profile_id=self.trader_agent.active_profile_id,
                force=True,
                source="runtime_warmup",
            )
        await self.bus.queue.join()

    @staticmethod
    def _resolve_default_asset_type(broker: BaseBroker, *, fallback: str | None = None) -> str:
        explicit = str(
            fallback
            or getattr(getattr(broker, "config", None), "type", None)
            or getattr(broker, "exchange_type", None)
            or ""
        ).strip().lower()
        if explicit:
            return explicit

        venue = str(getattr(broker, "exchange_name", "") or "").strip().lower()
        if venue in {"oanda", "fxcm"}:
            return "forex"
        if venue in {"alpaca", "schwab"}:
            return "stocks"
        if venue in {"tradovate", "cme"}:
            return "futures"
        return "crypto"

    @staticmethod
    def _build_default_event_bus(
        *,
        event_store_path: str | None,
        persist_events: bool,
        logger: logging.Logger,
    ) -> AsyncEventBus:
        store = JsonlEventStore(event_store_path) if event_store_path else InMemoryEventStore()
        return AsyncEventBus(store=store, enable_persistence=bool(persist_events), logger=logger)


def build_coinbase_futures_runtime(config, **runtime_kwargs) -> SopotekRuntime:
    """Example runtime bootstrap for the dedicated Coinbase futures broker."""

    from broker.coinbase_futures import CoinbaseFuturesBroker

    broker = CoinbaseFuturesBroker(config)
    runtime_kwargs.setdefault("default_asset_type", "future")
    return SopotekRuntime(broker, **runtime_kwargs)
