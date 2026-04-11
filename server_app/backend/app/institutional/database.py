from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    purpose: str
    primary_key: str
    columns: tuple[str, ...]
    indexes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CacheSpec:
    keyspace: str
    purpose: str
    ttl_hint: str


@dataclass(frozen=True, slots=True)
class ObjectStorageSpec:
    prefix: str
    purpose: str
    retention: str


DATABASE_TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        name="users",
        purpose="Identity, RBAC role, and operator lifecycle state.",
        primary_key="user_id UUID",
        columns=("email UNIQUE", "password_hash", "role", "mfa_enabled", "status", "created_at"),
        indexes=("idx_users_email", "idx_users_role_status"),
    ),
    TableSpec(
        name="device_sessions",
        purpose="Desktop device registration, refresh token lineage, and last seen fingerprints.",
        primary_key="session_id UUID",
        columns=("user_id", "device_id", "oauth_provider", "refresh_token_hash", "expires_at", "last_seen_at"),
        indexes=("idx_device_sessions_user", "idx_device_sessions_device"),
    ),
    TableSpec(
        name="subscription_entitlements",
        purpose="Stripe subscription state, plan, license key bindings, and feature gates.",
        primary_key="entitlement_id UUID",
        columns=("user_id", "plan_code", "stripe_customer_id", "license_key_hash", "feature_flags JSONB", "status"),
        indexes=("idx_entitlements_user", "idx_entitlements_plan_status"),
    ),
    TableSpec(
        name="broker_accounts",
        purpose="Encrypted broker connections and venue-specific metadata.",
        primary_key="broker_account_id UUID",
        columns=("user_id", "venue", "account_alias", "encrypted_credentials_ref", "base_currency", "status"),
        indexes=("idx_broker_accounts_user", "idx_broker_accounts_venue"),
    ),
    TableSpec(
        name="portfolios",
        purpose="Top-level portfolio and strategy allocation boundaries.",
        primary_key="portfolio_id UUID",
        columns=("user_id", "name", "base_currency", "gross_limit", "net_limit", "created_at"),
        indexes=("idx_portfolios_user", "idx_portfolios_currency"),
    ),
    TableSpec(
        name="positions",
        purpose="Live and historical position inventory by account and symbol.",
        primary_key="position_id UUID",
        columns=("portfolio_id", "broker_account_id", "symbol", "quantity", "avg_price", "market_value", "updated_at"),
        indexes=("idx_positions_portfolio_symbol", "idx_positions_account_symbol"),
    ),
    TableSpec(
        name="orders",
        purpose="Order intents, routing decisions, and lifecycle state.",
        primary_key="order_id UUID",
        columns=("portfolio_id", "broker_account_id", "symbol", "side", "order_type", "quantity", "price", "status"),
        indexes=("idx_orders_portfolio_status", "idx_orders_account_created"),
    ),
    TableSpec(
        name="executions",
        purpose="Immutable fill ledger for reconciliation and slippage analytics.",
        primary_key="execution_id UUID",
        columns=("order_id", "venue", "fill_price", "fill_quantity", "fees", "liquidity_flag", "executed_at"),
        indexes=("idx_executions_order", "idx_executions_executed_at"),
    ),
    TableSpec(
        name="risk_policies",
        purpose="Per-account institutional limits and liquidation rules.",
        primary_key="policy_id UUID",
        columns=("portfolio_id", "max_risk_per_trade_pct", "max_portfolio_exposure_pct", "daily_drawdown_limit_pct", "auto_liquidation_pct"),
        indexes=("idx_risk_policies_portfolio",),
    ),
    TableSpec(
        name="risk_alerts",
        purpose="Alert history for limit breaches, throttles, and forced liquidations.",
        primary_key="alert_id UUID",
        columns=("portfolio_id", "severity", "code", "message", "metric", "threshold", "observed", "created_at"),
        indexes=("idx_risk_alerts_portfolio", "idx_risk_alerts_created_at"),
    ),
    TableSpec(
        name="agent_decisions",
        purpose="Master/market/strategy/risk/execution agent outputs and traceability.",
        primary_key="decision_id UUID",
        columns=("agent_name", "correlation_id", "symbol", "decision", "confidence", "trace_uri", "created_at"),
        indexes=("idx_agent_decisions_agent", "idx_agent_decisions_correlation"),
    ),
    TableSpec(
        name="ml_experiments",
        purpose="Backtests, retraining jobs, feature sets, and promoted model versions.",
        primary_key="experiment_id UUID",
        columns=("model_family", "feature_set_version", "paper_window_start", "paper_window_end", "scorecard JSONB", "status"),
        indexes=("idx_ml_experiments_family_status", "idx_ml_experiments_window"),
    ),
    TableSpec(
        name="notification_log",
        purpose="Outbound operator notifications and delivery outcomes.",
        primary_key="notification_id UUID",
        columns=("user_id", "channel", "template_code", "severity", "delivery_status", "sent_at"),
        indexes=("idx_notification_log_user", "idx_notification_log_sent_at"),
    ),
    TableSpec(
        name="event_journal",
        purpose="Kafka event replay index for audits and recovery drills.",
        primary_key="journal_id BIGSERIAL",
        columns=("topic", "partition_key", "event_id", "correlation_id", "payload JSONB", "occurred_at"),
        indexes=("idx_event_journal_topic_time", "idx_event_journal_correlation"),
    ),
)


CACHE_SPECS: tuple[CacheSpec, ...] = (
    CacheSpec("sessions:*", "JWT refresh session cache and device revocation list.", "15m to 30d"),
    CacheSpec("market:snapshot:*", "Latest normalized tick, candle, and top-of-book state.", "1s to 5m"),
    CacheSpec("portfolio:live:*", "Hot path portfolio and exposure snapshots.", "5s to 60s"),
    CacheSpec("risk:limits:*", "Materialized pre-trade limit sets for low-latency checks.", "1m to 15m"),
)


OBJECT_STORAGE_LAYOUT: tuple[ObjectStorageSpec, ...] = (
    ObjectStorageSpec("models/", "Promoted XGBoost/HMM artifacts and feature manifests.", "12 months or superseded"),
    ObjectStorageSpec("market-replay/", "Tick, candle, and order-book replay packs for backtests.", "90 days hot, archive after"),
    ObjectStorageSpec("agent-traces/", "Reasoning traces, prompts, and decision audit bundles.", "180 days"),
    ObjectStorageSpec("logs/", "Immutable structured logs and compliance exports.", "7 years archive"),
)
