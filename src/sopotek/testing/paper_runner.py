from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sopotek.brokers import PaperBroker
from sopotek.core.orchestrator import SopotekRuntime
from sopotek.engines.backtest import BacktestRunResult
from storage import database as storage_db


@dataclass(slots=True)
class PaperTradingRun:
    result: BacktestRunResult
    retraining_report: object | None
    runtime: SopotekRuntime


async def run_paper_trading_session(
    candles_by_symbol: dict[str, list[list[Any] | dict[str, Any]]],
    *,
    timeframe: str = "1m",
    starting_equity: float = 100000.0,
    database_url: str | None = None,
    random_seed: int = 7,
    retrain_after_run: bool = True,
    enable_default_agents: bool = True,
    enable_trader_agent: bool = True,
    agents: list | None = None,
    trader_profiles: dict[str, Any] | None = None,
    active_trader_profile: str | None = None,
    trader_agent_kwargs: dict[str, Any] | None = None,
    broker_kwargs: dict[str, Any] | None = None,
) -> PaperTradingRun:
    if database_url:
        storage_db.configure_database(database_url)
    storage_db.init_database()

    broker = PaperBroker(seed=random_seed, **dict(broker_kwargs or {}))
    runtime = SopotekRuntime(
        broker=broker,
        starting_equity=starting_equity,
        candle_timeframes=[timeframe],
        enable_default_agents=enable_default_agents,
        enable_ml_filter=True,
        enable_trader_agent=enable_trader_agent,
        trader_profiles=trader_profiles,
        active_trader_profile=active_trader_profile,
        trader_agent_kwargs=trader_agent_kwargs,
    )
    for agent in agents or []:
        runtime.register_agent(agent)
    result = await runtime.backtest_engine.run(candles_by_symbol, timeframe=timeframe)
    retraining_report = runtime.retrain_from_feedback() if retrain_after_run else None
    return PaperTradingRun(result=result, retraining_report=retraining_report, runtime=runtime)
