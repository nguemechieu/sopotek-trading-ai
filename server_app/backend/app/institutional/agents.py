from __future__ import annotations

from dataclasses import dataclass

from .events import EventTopic


@dataclass(frozen=True, slots=True)
class AgentBlueprint:
    name: str
    ownership: str
    consumes: tuple[EventTopic, ...]
    publishes: tuple[EventTopic, ...]
    success_metric: str


@dataclass(frozen=True, slots=True)
class AgentFlowStep:
    step: int
    actor: str
    action: str
    input_topics: tuple[EventTopic, ...]
    output_topics: tuple[EventTopic, ...]


AGENT_BLUEPRINTS: tuple[AgentBlueprint, ...] = (
    AgentBlueprint(
        name="Master Agent",
        ownership="Global orchestrator for policy, coordination, and escalation routing.",
        consumes=(EventTopic.MARKET_TICK, EventTopic.PORTFOLIO_UPDATE, EventTopic.RISK_ALERT),
        publishes=(EventTopic.STRATEGY_SIGNAL, EventTopic.NOTIFICATION_DISPATCH),
        success_metric="time-to-decision under 150 ms with zero policy violations",
    ),
    AgentBlueprint(
        name="Market Agent",
        ownership="Extract volatility, liquidity, and regime intelligence from live feeds.",
        consumes=(EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE),
        publishes=(EventTopic.STRATEGY_SIGNAL,),
        success_metric="stable feature coverage and volatility regime accuracy",
    ),
    AgentBlueprint(
        name="Strategy Agent",
        ownership="Convert market state into ranked signal candidates.",
        consumes=(EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE),
        publishes=(EventTopic.STRATEGY_SIGNAL,),
        success_metric="risk-adjusted signal hit rate and turnover efficiency",
    ),
    AgentBlueprint(
        name="Risk Agent",
        ownership="Challenge signals and enforce capital/risk policies before execution.",
        consumes=(EventTopic.STRATEGY_SIGNAL, EventTopic.PORTFOLIO_UPDATE),
        publishes=(EventTopic.RISK_ALERT,),
        success_metric="zero limit breaches and bounded drawdown",
    ),
    AgentBlueprint(
        name="Execution Agent",
        ownership="Optimize broker venue selection, price improvement, and slippage.",
        consumes=(EventTopic.STRATEGY_SIGNAL, EventTopic.ORDER_CREATED),
        publishes=(EventTopic.ORDER_CREATED, EventTopic.ORDER_EXECUTED),
        success_metric="slippage below target benchmark",
    ),
    AgentBlueprint(
        name="Learning Agent",
        ownership="Translate paper/live results into retraining and model promotion signals.",
        consumes=(EventTopic.ORDER_EXECUTED, EventTopic.PORTFOLIO_UPDATE),
        publishes=(EventTopic.MODEL_PROMOTED, EventTopic.NOTIFICATION_DISPATCH),
        success_metric="positive walk-forward uplift after retraining",
    ),
)


AGENT_INTERACTION_FLOW: tuple[AgentFlowStep, ...] = (
    AgentFlowStep(
        step=1,
        actor="Market Agent",
        action="Consumes `market.tick` and `market.candle` to score volatility regime, liquidity, and microstructure drift.",
        input_topics=(EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE),
        output_topics=(EventTopic.STRATEGY_SIGNAL,),
    ),
    AgentFlowStep(
        step=2,
        actor="Strategy Agent",
        action="Ranks directional and neutral strategies, then emits a signal candidate with confidence metadata.",
        input_topics=(EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE),
        output_topics=(EventTopic.STRATEGY_SIGNAL,),
    ),
    AgentFlowStep(
        step=3,
        actor="Master Agent",
        action="Correlates market and strategy evidence, checks entitlement gates, and forwards a coordinated signal.",
        input_topics=(EventTopic.STRATEGY_SIGNAL, EventTopic.PORTFOLIO_UPDATE),
        output_topics=(EventTopic.STRATEGY_SIGNAL,),
    ),
    AgentFlowStep(
        step=4,
        actor="Risk Agent",
        action="Runs pre-trade validation for exposure, per-trade risk, and drawdown policies.",
        input_topics=(EventTopic.STRATEGY_SIGNAL, EventTopic.PORTFOLIO_UPDATE),
        output_topics=(EventTopic.RISK_ALERT,),
    ),
    AgentFlowStep(
        step=5,
        actor="Execution Agent",
        action="Optimizes routing across CCXT, OANDA, or Alpaca and publishes `order.created`.",
        input_topics=(EventTopic.STRATEGY_SIGNAL,),
        output_topics=(EventTopic.ORDER_CREATED,),
    ),
    AgentFlowStep(
        step=6,
        actor="Trading Core Service",
        action="Submits broker-native orders and emits `order.executed` when fills arrive.",
        input_topics=(EventTopic.ORDER_CREATED,),
        output_topics=(EventTopic.ORDER_EXECUTED,),
    ),
    AgentFlowStep(
        step=7,
        actor="Portfolio Service",
        action="Revalues holdings, exposures, and PnL after each execution.",
        input_topics=(EventTopic.ORDER_EXECUTED,),
        output_topics=(EventTopic.PORTFOLIO_UPDATE,),
    ),
    AgentFlowStep(
        step=8,
        actor="Learning Agent",
        action="Feeds paper/live execution outcomes into retraining and model promotion workflows.",
        input_topics=(EventTopic.ORDER_EXECUTED, EventTopic.PORTFOLIO_UPDATE),
        output_topics=(EventTopic.MODEL_PROMOTED,),
    ),
)
