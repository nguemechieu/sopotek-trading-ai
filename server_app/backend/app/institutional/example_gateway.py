from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from .agents import AGENT_BLUEPRINTS, AGENT_INTERACTION_FLOW
from .blueprints import API_ENDPOINTS
from .brokerage import AccountContext, AssetClass, BrokerVenue, ExecutionIntent, SmartOrderRouter
from .config import InstitutionalPlatformSettings
from .database import CACHE_SPECS, DATABASE_TABLES, OBJECT_STORAGE_LAYOUT
from .event_bus import InMemoryEventBus
from .events import (
    EventEnvelope,
    EventTopic,
    MarketTickPayload,
    OrderCreatedPayload,
    OrderExecutedPayload,
    PortfolioUpdatePayload,
    RiskAlertPayload,
    StrategySignalPayload,
    build_event_schema_catalog,
)
from .risk import InstitutionalRiskEngine, PortfolioState, ProposedOrder
from .services import build_service_registry


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    user_id: str = "demo-user"
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_price: float | None = None
    asset_class: AssetClass
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "limit"
    preferred_venue: BrokerVenue | None = None
    strategy_id: str | None = None
    signal_id: str | None = None


class ExecuteOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_price: float = Field(gt=0)
    filled_quantity: float | None = Field(default=None, gt=0)
    fees: float = Field(default=0.0, ge=0)
    liquidity: Literal["maker", "taker", "internalized"] = "maker"
    venue: BrokerVenue | None = None


class InstitutionalPlatformRuntime:
    def __init__(self, settings: InstitutionalPlatformSettings | None = None) -> None:
        self.settings = settings or InstitutionalPlatformSettings()
        self.event_bus = InMemoryEventBus()
        self.service_registry = build_service_registry()
        self.risk_engine = InstitutionalRiskEngine()
        self.router = SmartOrderRouter()
        self.accounts: tuple[AccountContext, ...] = (
            AccountContext(
                account_id="acct-fx-001",
                venue=BrokerVenue.OANDA,
                asset_classes=(AssetClass.FX,),
                base_currency="USD",
                buying_power=1_000_000.0,
                status="active",
            ),
            AccountContext(
                account_id="acct-crypto-001",
                venue=BrokerVenue.CCXT,
                asset_classes=(AssetClass.CRYPTO,),
                base_currency="USDT",
                buying_power=500_000.0,
                status="active",
            ),
            AccountContext(
                account_id="acct-equity-001",
                venue=BrokerVenue.ALPACA,
                asset_classes=(AssetClass.EQUITY,),
                base_currency="USD",
                buying_power=750_000.0,
                status="active",
            ),
        )
        self.portfolio_state = PortfolioState(
            net_liquidation=250_000.0,
            current_exposure=45_000.0,
            daily_pnl=1_250.0,
            active_positions={"EUR_USD": 25_000.0, "AAPL": 100.0},
        )
        self.orders: dict[str, dict[str, object]] = {}
        self.executions: dict[str, dict[str, object]] = {}
        self.notifications: list[dict[str, object]] = []
        self.latest_signals: list[dict[str, object]] = []
        self.last_prices: dict[str, float] = {}
        self._wire_consumers()

    def _wire_consumers(self) -> None:
        self.event_bus.subscribe(EventTopic.MARKET_TICK, self._on_market_tick)
        self.event_bus.subscribe(EventTopic.STRATEGY_SIGNAL, self._on_strategy_signal)
        self.event_bus.subscribe(EventTopic.RISK_ALERT, self._on_risk_alert)
        self.event_bus.subscribe(EventTopic.ORDER_EXECUTED, self._on_order_executed)
        self.event_bus.subscribe(EventTopic.PORTFOLIO_UPDATE, self._on_portfolio_update)

    async def publish(
        self,
        *,
        topic: EventTopic,
        producer: str,
        payload: BaseModel,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        user_id: str | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope.from_payload(
            topic=topic,
            producer=producer,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            user_id=user_id,
        )
        await self.event_bus.publish(envelope)
        return envelope

    async def _on_market_tick(self, envelope: EventEnvelope) -> None:
        payload = MarketTickPayload.model_validate(envelope.payload)
        previous_price = self.last_prices.get(payload.symbol)
        self.last_prices[payload.symbol] = payload.last_price
        if previous_price is None or previous_price <= 0:
            return
        change_pct = (payload.last_price - previous_price) / previous_price
        if abs(change_pct) < 0.01:
            return
        signal = StrategySignalPayload(
            symbol=payload.symbol,
            signal="buy" if change_pct > 0 else "sell",
            confidence=min(0.95, abs(change_pct) * 12.0),
            horizon="5m",
            regime="volatile_breakout",
            rationale=f"Price moved {change_pct:.2%} between successive ticks.",
            generated_by="market-agent",
            model_version="market-agent.v1",
        )
        await self.publish(
            topic=EventTopic.STRATEGY_SIGNAL,
            producer="ai_agent_service",
            payload=signal,
            correlation_id=envelope.correlation_id or envelope.event_id,
        )

    async def _on_strategy_signal(self, envelope: EventEnvelope) -> None:
        payload = StrategySignalPayload.model_validate(envelope.payload)
        self.latest_signals.append(payload.model_dump(mode="json"))
        self.latest_signals = self.latest_signals[-20:]

    async def _on_risk_alert(self, envelope: EventEnvelope) -> None:
        payload = RiskAlertPayload.model_validate(envelope.payload)
        self.notifications.append(
            {
                "channel": "desktop",
                "severity": payload.severity,
                "message": payload.message,
                "event_id": envelope.event_id,
            }
        )
        self.notifications = self.notifications[-50:]

    async def _on_order_executed(self, envelope: EventEnvelope) -> None:
        payload = OrderExecutedPayload.model_validate(envelope.payload)
        notional = payload.fill_price * payload.filled_quantity
        self.portfolio_state.current_exposure += notional
        self.portfolio_state.active_positions[payload.symbol] = (
            self.portfolio_state.active_positions.get(payload.symbol, 0.0) + payload.filled_quantity
        )
        portfolio_event = PortfolioUpdatePayload(
            account_id=payload.account_id,
            net_liquidation=self.portfolio_state.net_liquidation,
            gross_exposure=self.portfolio_state.current_exposure,
            net_exposure=self.portfolio_state.current_exposure,
            realized_pnl=self.portfolio_state.daily_pnl,
            unrealized_pnl=0.0,
            updated_at=datetime.now(UTC),
        )
        await self.publish(
            topic=EventTopic.PORTFOLIO_UPDATE,
            producer="portfolio_service",
            payload=portfolio_event,
            correlation_id=envelope.correlation_id or payload.order_id,
            causation_id=envelope.event_id,
        )

    async def _on_portfolio_update(self, envelope: EventEnvelope) -> None:
        payload = PortfolioUpdatePayload.model_validate(envelope.payload)
        self.notifications.append(
            {
                "channel": "ops",
                "severity": "info",
                "message": f"Portfolio {payload.account_id} updated: gross exposure {payload.gross_exposure:,.2f}.",
                "event_id": envelope.event_id,
            }
        )
        self.notifications = self.notifications[-50:]


def create_app(settings: InstitutionalPlatformSettings | None = None) -> FastAPI:
    runtime = InstitutionalPlatformRuntime(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.platform = runtime
        yield

    app = FastAPI(
        title="Sopotek Institutional API Gateway Example",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthcheck() -> dict[str, object]:
        return {
            "status": "ok",
            "environment": runtime.settings.environment,
            "region": runtime.settings.region,
            "service_count": len(runtime.service_registry),
            "topics": [topic.value for topic in EventTopic],
        }

    @app.get("/v1/architecture/overview")
    async def architecture_overview() -> dict[str, object]:
        return {
            "system": {
                "desktop": "PySide6 trading terminal with PyQtGraph charts and multi-exchange controls.",
                "backend": "FastAPI event-driven services backed by Kafka, PostgreSQL, Redis, and object storage.",
                "event_bus": "Kafka in production, in-memory event bus in this reference implementation.",
            },
            "services": [service.describe() for service in runtime.service_registry.values()],
            "storage": {
                "postgresql_tables": [asdict(table) for table in DATABASE_TABLES],
                "redis": [asdict(cache) for cache in CACHE_SPECS],
                "object_storage": [asdict(spec) for spec in OBJECT_STORAGE_LAYOUT],
            },
        }

    @app.get("/v1/architecture/services")
    async def architecture_services() -> dict[str, object]:
        return {
            "services": [service.describe() for service in runtime.service_registry.values()],
        }

    @app.get("/v1/architecture/events")
    async def architecture_events() -> dict[str, object]:
        return {"schemas": build_event_schema_catalog()}

    @app.get("/v1/architecture/database")
    async def architecture_database() -> dict[str, object]:
        return {
            "tables": [asdict(table) for table in DATABASE_TABLES],
            "cache_layers": [asdict(cache) for cache in CACHE_SPECS],
            "object_storage": [asdict(spec) for spec in OBJECT_STORAGE_LAYOUT],
        }

    @app.get("/v1/architecture/endpoints")
    async def architecture_endpoints() -> dict[str, object]:
        return {"endpoints": [asdict(endpoint) for endpoint in API_ENDPOINTS]}

    @app.get("/v1/architecture/agents")
    async def architecture_agents() -> dict[str, object]:
        return {
            "agents": [asdict(agent) for agent in AGENT_BLUEPRINTS],
            "flow": [asdict(step) for step in AGENT_INTERACTION_FLOW],
        }

    @app.get("/v1/portfolio")
    async def portfolio_snapshot() -> dict[str, object]:
        return {
            "net_liquidation": runtime.portfolio_state.net_liquidation,
            "current_exposure": runtime.portfolio_state.current_exposure,
            "daily_pnl": runtime.portfolio_state.daily_pnl,
            "positions": runtime.portfolio_state.active_positions,
        }

    @app.post("/v1/market/ticks", status_code=status.HTTP_202_ACCEPTED)
    async def ingest_tick(payload: MarketTickPayload) -> dict[str, object]:
        envelope = await runtime.publish(
            topic=EventTopic.MARKET_TICK,
            producer="market_data_service",
            payload=payload,
            correlation_id=str(uuid4()),
        )
        return {
            "accepted": True,
            "event_id": envelope.event_id,
            "latest_signal_count": len(runtime.latest_signals),
        }

    @app.post("/v1/orders", status_code=status.HTTP_201_CREATED)
    async def create_order(payload: CreateOrderRequest) -> dict[str, object]:
        decision = runtime.risk_engine.evaluate(
            portfolio=runtime.portfolio_state,
            order=ProposedOrder(
                account_id=payload.account_id,
                symbol=payload.symbol,
                side=payload.side,
                quantity=payload.quantity,
                entry_price=payload.entry_price,
                stop_price=payload.stop_price,
                asset_class=payload.asset_class,
            ),
        )
        if not decision.approved:
            alert = RiskAlertPayload(
                severity="critical" if decision.auto_liquidate else "warning",
                account_id=payload.account_id,
                code="PRE_TRADE_REJECTED",
                message=decision.reason,
                metric="exposure" if not decision.auto_liquidate else "drawdown",
                threshold=runtime.portfolio_state.net_liquidation * runtime.risk_engine.limits.max_portfolio_exposure_pct,
                observed=runtime.portfolio_state.current_exposure,
                action="auto_liquidate" if decision.auto_liquidate else "block_order",
            )
            await runtime.publish(
                topic=EventTopic.RISK_ALERT,
                producer="risk_engine_service",
                payload=alert,
                correlation_id=str(uuid4()),
                user_id=payload.user_id,
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=decision.reason)

        route = runtime.router.select_route(
            ExecutionIntent(
                account_id=payload.account_id,
                symbol=payload.symbol,
                side=payload.side,
                quantity=decision.capped_quantity,
                price=payload.entry_price,
                asset_class=payload.asset_class,
                preferred_venue=payload.preferred_venue,
            ),
            runtime.accounts,
        )
        order_id = str(uuid4())
        order_event = OrderCreatedPayload(
            order_id=order_id,
            account_id=payload.account_id,
            user_id=payload.user_id,
            symbol=payload.symbol,
            side=payload.side,
            quantity=decision.capped_quantity,
            order_type=payload.order_type,
            venue=route.venue.value,
            notional=decision.notional,
            price=payload.entry_price,
            strategy_id=payload.strategy_id,
            signal_id=payload.signal_id,
            route_hint=f"{route.venue.value}:{route.composite_cost:.2f}",
        )
        envelope = await runtime.publish(
            topic=EventTopic.ORDER_CREATED,
            producer="trading_core_service",
            payload=order_event,
            correlation_id=order_id,
            user_id=payload.user_id,
        )
        runtime.orders[order_id] = {
            "order": order_event.model_dump(mode="json"),
            "risk_decision": asdict(decision),
            "route": {
                "venue": route.venue.value,
                "account_id": route.account_id,
                "estimated_latency_ms": route.estimated_latency_ms,
                "fees_bps": route.fees_bps,
                "expected_slippage_bps": route.expected_slippage_bps,
            },
            "event_id": envelope.event_id,
            "status": "accepted",
        }
        return runtime.orders[order_id]

    @app.post("/v1/orders/{order_id}/execute")
    async def execute_order(order_id: str, payload: ExecuteOrderRequest) -> dict[str, object]:
        stored = runtime.orders.get(order_id)
        if stored is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown order_id.")
        order_payload = OrderCreatedPayload.model_validate(stored["order"])
        execution = OrderExecutedPayload(
            order_id=order_id,
            account_id=order_payload.account_id,
            symbol=order_payload.symbol,
            venue=(payload.venue or BrokerVenue(order_payload.venue)).value,
            fill_price=payload.fill_price,
            filled_quantity=payload.filled_quantity or order_payload.quantity,
            fees=payload.fees,
            liquidity=payload.liquidity,
            status="filled",
            executed_at=datetime.now(UTC),
        )
        envelope = await runtime.publish(
            topic=EventTopic.ORDER_EXECUTED,
            producer="trading_core_service",
            payload=execution,
            correlation_id=order_id,
            causation_id=stored["event_id"],
            user_id=order_payload.user_id,
        )
        runtime.executions[order_id] = {
            "execution": execution.model_dump(mode="json"),
            "event_id": envelope.event_id,
            "status": "filled",
        }
        return runtime.executions[order_id]

    @app.get("/v1/events")
    async def list_events() -> dict[str, object]:
        return {
            "events": [message.model_dump(mode="json") for message in runtime.event_bus.messages],
        }

    @app.get("/v1/notifications")
    async def list_notifications() -> dict[str, object]:
        return {"notifications": list(runtime.notifications)}

    return app


app = create_app()
