from __future__ import annotations

from dataclasses import dataclass

from .events import EventTopic


@dataclass(frozen=True, slots=True)
class ServiceBlueprint:
    slug: str
    name: str
    responsibility: str
    storage: tuple[str, ...]
    publishes: tuple[EventTopic, ...]
    consumes: tuple[EventTopic, ...]
    interfaces: tuple[str, ...]
    scale_unit: str


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    service: str
    method: str
    path: str
    purpose: str
    auth_scope: str


SERVICE_BLUEPRINTS: dict[str, ServiceBlueprint] = {
    "api_gateway": ServiceBlueprint(
        slug="api_gateway",
        name="API Gateway",
        responsibility="Northbound ingress for desktop, mobile, admin, and partner traffic.",
        storage=("Redis rate limits", "Redis request cache"),
        publishes=(EventTopic.ORDER_CREATED, EventTopic.RISK_ALERT),
        consumes=(EventTopic.ORDER_EXECUTED, EventTopic.PORTFOLIO_UPDATE, EventTopic.RISK_ALERT),
        interfaces=("REST", "WebSocket", "gRPC edge"),
        scale_unit="horizontal stateless pods behind L7 ingress",
    ),
    "auth_service": ServiceBlueprint(
        slug="auth_service",
        name="Auth Service",
        responsibility="JWT, OAuth, RBAC, device sessions, token rotation, and policy enforcement.",
        storage=("PostgreSQL users/auth", "Redis sessions"),
        publishes=(EventTopic.AUTH_SESSION_CREATED,),
        consumes=(EventTopic.SUBSCRIPTION_UPDATED,),
        interfaces=("REST", "OAuth callbacks", "internal token introspection"),
        scale_unit="horizontal stateless pods with Redis-backed sessions",
    ),
    "user_profile_service": ServiceBlueprint(
        slug="user_profile_service",
        name="User/Profile Service",
        responsibility="Desk preferences, broker profiles, watchlists, personalization, and account metadata.",
        storage=("PostgreSQL user profile", "Redis profile cache"),
        publishes=(EventTopic.PORTFOLIO_UPDATE,),
        consumes=(EventTopic.AUTH_SESSION_CREATED,),
        interfaces=("REST", "internal query API"),
        scale_unit="horizontal stateless pods",
    ),
    "license_subscription_service": ServiceBlueprint(
        slug="license_subscription_service",
        name="License & Subscription Service",
        responsibility="Stripe billing, plan entitlements, license key validation, and feature gating.",
        storage=("PostgreSQL subscription", "Redis entitlement cache"),
        publishes=(EventTopic.SUBSCRIPTION_UPDATED, EventTopic.NOTIFICATION_DISPATCH),
        consumes=(EventTopic.AUTH_SESSION_CREATED,),
        interfaces=("REST", "Stripe webhook", "internal entitlement API"),
        scale_unit="horizontal stateless pods with idempotent webhooks",
    ),
    "trading_core_service": ServiceBlueprint(
        slug="trading_core_service",
        name="Trading Core Service",
        responsibility="Strategy execution orchestration, order lifecycle state, account fanout, and smart routing.",
        storage=("PostgreSQL orders/executions", "Redis working orders"),
        publishes=(EventTopic.ORDER_CREATED, EventTopic.ORDER_EXECUTED),
        consumes=(EventTopic.STRATEGY_SIGNAL, EventTopic.RISK_ALERT),
        interfaces=("REST", "internal command API", "broker adapters"),
        scale_unit="partitioned by account shard and venue",
    ),
    "risk_engine_service": ServiceBlueprint(
        slug="risk_engine_service",
        name="Risk Engine Service",
        responsibility="Hard limits, intraday kill switches, sizing, exposure, and liquidation workflows.",
        storage=("PostgreSQL risk policies", "Redis live exposures"),
        publishes=(EventTopic.RISK_ALERT,),
        consumes=(EventTopic.ORDER_CREATED, EventTopic.ORDER_EXECUTED, EventTopic.PORTFOLIO_UPDATE),
        interfaces=("REST", "internal pre-trade API"),
        scale_unit="hot-active pods partitioned by prime book/account",
    ),
    "portfolio_service": ServiceBlueprint(
        slug="portfolio_service",
        name="Portfolio Service",
        responsibility="Cross-venue holdings, PnL, capital allocation, and end-of-day reconciliation.",
        storage=("PostgreSQL portfolio ledger", "Redis portfolio snapshots"),
        publishes=(EventTopic.PORTFOLIO_UPDATE,),
        consumes=(EventTopic.ORDER_EXECUTED, EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE),
        interfaces=("REST", "internal valuation API"),
        scale_unit="partitioned by portfolio/account",
    ),
    "market_data_service": ServiceBlueprint(
        slug="market_data_service",
        name="Market Data Service",
        responsibility="Normalized multi-venue tick, candle, and order book ingestion over WebSocket and REST.",
        storage=("Redis market cache", "Object storage market replay"),
        publishes=(EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE),
        consumes=(),
        interfaces=("WebSocket ingestion", "REST ingestion", "internal fanout"),
        scale_unit="partitioned by venue and instrument universe",
    ),
    "ai_agent_service": ServiceBlueprint(
        slug="ai_agent_service",
        name="AI Agent Service",
        responsibility="Master orchestration plus market, strategy, risk, execution, and learning agents.",
        storage=("PostgreSQL agent decisions", "Object storage prompts and traces"),
        publishes=(EventTopic.STRATEGY_SIGNAL, EventTopic.RISK_ALERT, EventTopic.NOTIFICATION_DISPATCH),
        consumes=(EventTopic.MARKET_TICK, EventTopic.MARKET_CANDLE, EventTopic.PORTFOLIO_UPDATE),
        interfaces=("REST", "internal event consumers"),
        scale_unit="partitioned by strategy cluster and region",
    ),
    "ml_training_pipeline": ServiceBlueprint(
        slug="ml_training_pipeline",
        name="ML Training Pipeline",
        responsibility="Feature engineering, backtesting, retraining, evaluation, and model promotion.",
        storage=("Object storage models", "PostgreSQL experiment metadata"),
        publishes=(EventTopic.MODEL_PROMOTED, EventTopic.NOTIFICATION_DISPATCH),
        consumes=(EventTopic.ORDER_EXECUTED, EventTopic.PORTFOLIO_UPDATE),
        interfaces=("batch job API", "scheduler", "offline notebook jobs"),
        scale_unit="ephemeral GPU/CPU workers by training job",
    ),
    "notification_service": ServiceBlueprint(
        slug="notification_service",
        name="Notification Service",
        responsibility="Email, SMS, Telegram, push, and desktop notifications for actionable events.",
        storage=("PostgreSQL notification log", "Redis delivery queue"),
        publishes=(EventTopic.NOTIFICATION_DISPATCH,),
        consumes=(EventTopic.RISK_ALERT, EventTopic.ORDER_EXECUTED, EventTopic.SUBSCRIPTION_UPDATED),
        interfaces=("REST", "internal delivery workers"),
        scale_unit="horizontal stateless workers with queue consumers",
    ),
}


API_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("API Gateway", "GET", "/healthz", "Cluster health and dependency readiness.", "public"),
    EndpointSpec("Auth Service", "POST", "/v1/auth/login", "Issue JWT and refresh tokens for a device session.", "public"),
    EndpointSpec("Auth Service", "POST", "/v1/auth/refresh", "Rotate short-lived access credentials.", "device_session"),
    EndpointSpec("Auth Service", "GET", "/v1/auth/oauth/{provider}/callback", "Complete OAuth device authorization.", "public"),
    EndpointSpec("Auth Service", "DELETE", "/v1/auth/device-sessions/{session_id}", "Revoke a device session.", "user"),
    EndpointSpec("User/Profile Service", "GET", "/v1/users/me", "Resolve the authenticated operator profile.", "user"),
    EndpointSpec("User/Profile Service", "PATCH", "/v1/users/me/profile", "Update desk preferences and watchlists.", "user"),
    EndpointSpec("User/Profile Service", "GET", "/v1/users/me/devices", "List active desktop devices.", "user"),
    EndpointSpec("License & Subscription Service", "GET", "/v1/subscriptions/current", "Return active plan and entitlements.", "user"),
    EndpointSpec("License & Subscription Service", "POST", "/v1/billing/checkout", "Create a Stripe checkout or billing portal session.", "user"),
    EndpointSpec("License & Subscription Service", "POST", "/v1/licenses/validate", "Validate a desktop license key for a bound device.", "desktop"),
    EndpointSpec("Trading Core Service", "POST", "/v1/orders", "Submit an order intent into smart routing.", "trade:write"),
    EndpointSpec("Trading Core Service", "GET", "/v1/orders/{order_id}", "Fetch order lifecycle state.", "trade:read"),
    EndpointSpec("Trading Core Service", "POST", "/v1/orders/{order_id}/cancel", "Cancel an open working order.", "trade:write"),
    EndpointSpec("Trading Core Service", "POST", "/v1/execution/smart-route", "Preview venue routing decisions.", "trade:read"),
    EndpointSpec("Risk Engine Service", "GET", "/v1/risk/policies/{account_id}", "Fetch hard and soft risk guardrails.", "risk:read"),
    EndpointSpec("Risk Engine Service", "POST", "/v1/risk/evaluate-order", "Run pre-trade risk validation.", "trade:write"),
    EndpointSpec("Risk Engine Service", "POST", "/v1/risk/auto-liquidation", "Trigger emergency flattening workflow.", "risk:admin"),
    EndpointSpec("Portfolio Service", "GET", "/v1/portfolio/{account_id}", "Return aggregate positions and account value.", "portfolio:read"),
    EndpointSpec("Portfolio Service", "GET", "/v1/portfolio/{account_id}/exposure", "Return gross and net exposure summary.", "portfolio:read"),
    EndpointSpec("Portfolio Service", "GET", "/v1/portfolio/{account_id}/pnl", "Return realized and unrealized PnL.", "portfolio:read"),
    EndpointSpec("Market Data Service", "GET", "/v1/market/snapshot/{symbol}", "Fetch latest normalized market snapshot.", "market:read"),
    EndpointSpec("Market Data Service", "WS", "/v1/market/stream", "Real-time tick and portfolio fanout.", "market:stream"),
    EndpointSpec("Market Data Service", "POST", "/v1/market/ingest/tick", "Internal venue ingestion endpoint.", "internal"),
    EndpointSpec("AI Agent Service", "POST", "/v1/agents/master/cycle", "Run coordinated agent reasoning cycle.", "ai:write"),
    EndpointSpec("AI Agent Service", "GET", "/v1/agents/status", "Return live agent mesh status.", "ai:read"),
    EndpointSpec("AI Agent Service", "GET", "/v1/agents/decisions/{decision_id}", "Inspect a persisted agent decision.", "ai:read"),
    EndpointSpec("ML Training Pipeline", "POST", "/v1/ml/train", "Launch a new training experiment.", "ml:write"),
    EndpointSpec("ML Training Pipeline", "POST", "/v1/ml/backtest", "Run institutional backtest against a strategy/model bundle.", "ml:write"),
    EndpointSpec("ML Training Pipeline", "POST", "/v1/ml/retrain/paper-results", "Promote paper trading feedback into retraining.", "ml:write"),
    EndpointSpec("Notification Service", "POST", "/v1/notifications/dispatch", "Send an operator-facing alert.", "notify:write"),
    EndpointSpec("Notification Service", "GET", "/v1/notifications/preferences", "Read per-user notification routing policy.", "user"),
)
