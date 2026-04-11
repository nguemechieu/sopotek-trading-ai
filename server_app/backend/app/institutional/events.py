from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventTopic(str, Enum):
    MARKET_TICK = "market.tick"
    MARKET_CANDLE = "market.candle"
    STRATEGY_SIGNAL = "strategy.signal"
    ORDER_CREATED = "order.created"
    ORDER_EXECUTED = "order.executed"
    RISK_ALERT = "risk.alert"
    PORTFOLIO_UPDATE = "portfolio.update"
    AUTH_SESSION_CREATED = "auth.session.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    MODEL_PROMOTED = "ml.model.promoted"
    NOTIFICATION_DISPATCH = "notification.dispatch"


class BaseEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketTickPayload(BaseEventPayload):
    symbol: str
    venue: str
    bid: float
    ask: float
    last_price: float
    volume_24h: float | None = None
    ts_event: datetime


class MarketCandlePayload(BaseEventPayload):
    symbol: str
    venue: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ts_open: datetime
    ts_close: datetime


class StrategySignalPayload(BaseEventPayload):
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    signal: Literal["buy", "sell", "flat"]
    confidence: float = Field(ge=0.0, le=1.0)
    horizon: str
    regime: str
    rationale: str
    generated_by: str
    model_version: str


class OrderCreatedPayload(BaseEventPayload):
    order_id: str
    account_id: str
    user_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    order_type: Literal["market", "limit", "stop", "stop_limit"]
    venue: str
    notional: float = Field(gt=0)
    price: float = Field(gt=0)
    strategy_id: str | None = None
    signal_id: str | None = None
    route_hint: str | None = None


class OrderExecutedPayload(BaseEventPayload):
    order_id: str
    account_id: str
    symbol: str
    venue: str
    fill_price: float = Field(gt=0)
    filled_quantity: float = Field(gt=0)
    fees: float = Field(ge=0)
    liquidity: Literal["maker", "taker", "internalized"]
    status: Literal["partially_filled", "filled", "cancelled"]
    executed_at: datetime


class RiskAlertPayload(BaseEventPayload):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    severity: Literal["info", "warning", "critical"]
    account_id: str
    code: str
    message: str
    metric: str
    threshold: float
    observed: float
    action: str


class PortfolioUpdatePayload(BaseEventPayload):
    account_id: str
    net_liquidation: float = Field(gt=0)
    gross_exposure: float = Field(ge=0)
    net_exposure: float
    realized_pnl: float
    unrealized_pnl: float
    updated_at: datetime


EVENT_PAYLOAD_MODELS: dict[EventTopic, type[BaseEventPayload]] = {
    EventTopic.MARKET_TICK: MarketTickPayload,
    EventTopic.MARKET_CANDLE: MarketCandlePayload,
    EventTopic.STRATEGY_SIGNAL: StrategySignalPayload,
    EventTopic.ORDER_CREATED: OrderCreatedPayload,
    EventTopic.ORDER_EXECUTED: OrderExecutedPayload,
    EventTopic.RISK_ALERT: RiskAlertPayload,
    EventTopic.PORTFOLIO_UPDATE: PortfolioUpdatePayload,
}


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: EventTopic
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str
    correlation_id: str | None = None
    causation_id: str | None = None
    tenant_id: str = "sopotek"
    user_id: str | None = None
    payload: dict[str, Any]

    @classmethod
    def from_payload(
        cls,
        *,
        topic: EventTopic,
        producer: str,
        payload: BaseEventPayload,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        tenant_id: str = "sopotek",
        user_id: str | None = None,
    ) -> "EventEnvelope":
        return cls(
            topic=topic,
            event_type=type(payload).__name__,
            producer=producer,
            correlation_id=correlation_id,
            causation_id=causation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            payload=payload.model_dump(mode="json"),
        )


def build_event_schema_catalog() -> dict[str, dict[str, Any]]:
    return {
        topic.value: {
            "payload_schema": model.model_json_schema(),
            "envelope_fields": EventEnvelope.model_json_schema()["properties"],
        }
        for topic, model in EVENT_PAYLOAD_MODELS.items()
    }
