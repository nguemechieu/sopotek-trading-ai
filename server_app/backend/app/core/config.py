from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _split_csv(value: str | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = "Sopotek Trading AI Platform API"
    environment: str = field(default_factory=lambda: os.getenv("SOPOTEK_PLATFORM_ENV", "development"))
    secret_key: str = field(default_factory=lambda: os.getenv("SOPOTEK_PLATFORM_SECRET_KEY", "change-me-in-production"))
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_ACCESS_TOKEN_MINUTES", "720"))
    )
    remember_me_access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_REMEMBER_ACCESS_TOKEN_MINUTES", "10080"))
    )
    refresh_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_REFRESH_TOKEN_MINUTES", "10080"))
    )
    remember_me_refresh_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_REMEMBER_REFRESH_TOKEN_MINUTES", "43200"))
    )
    password_reset_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_PASSWORD_RESET_MINUTES", "30"))
    )
    license_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_LICENSE_TOKEN_MINUTES", "1440"))
    )
    license_offline_grace_hours: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_OFFLINE_GRACE_HOURS", "24"))
    )
    license_validation_rate_limit: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_LICENSE_RATE_LIMIT", "12"))
    )
    license_validation_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_LICENSE_RATE_WINDOW_SECONDS", "60"))
    )
    email_verification_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_EMAIL_VERIFY_MINUTES", "1440"))
    )
    require_verified_email: bool = field(
        default_factory=lambda: _env_flag(
            "SOPOTEK_PLATFORM_REQUIRE_VERIFIED_EMAIL",
            os.getenv("SOPOTEK_PLATFORM_ENV", "development").strip().lower() == "production",
        )
    )
    auth_rate_limit_attempts: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_AUTH_RATE_LIMIT_ATTEMPTS", "6"))
    )
    auth_rate_limit_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_AUTH_RATE_LIMIT_WINDOW_SECONDS", "60"))
    )
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "SOPOTEK_PLATFORM_DATABASE_URL",
            "sqlite+aiosqlite:///./backend/platform.db",
        )
    )
    database_connect_retry_attempts: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_PLATFORM_DATABASE_CONNECT_RETRY_ATTEMPTS", "10"))
    )
    database_connect_retry_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("SOPOTEK_PLATFORM_DATABASE_CONNECT_RETRY_DELAY_SECONDS", "2"))
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _split_csv(
            os.getenv("SOPOTEK_PLATFORM_CORS_ORIGINS"),
            default=("http://localhost:3000", "http://127.0.0.1:3000"),
        )
    )
    frontend_base_url: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_PLATFORM_FRONTEND_BASE_URL", "http://localhost:3000")
    )
    license_key_pepper: str | None = field(
        default_factory=lambda: os.getenv("SOPOTEK_PLATFORM_LICENSE_KEY_PEPPER") or None
    )
    stripe_secret_key: str | None = field(default_factory=lambda: os.getenv("SOPOTEK_STRIPE_SECRET_KEY") or None)
    stripe_webhook_secret: str | None = field(
        default_factory=lambda: os.getenv("SOPOTEK_STRIPE_WEBHOOK_SECRET") or None
    )
    stripe_pro_monthly_price_id: str | None = field(
        default_factory=lambda: os.getenv("SOPOTEK_STRIPE_PRO_MONTHLY_PRICE_ID") or None
    )
    stripe_elite_monthly_price_id: str | None = field(
        default_factory=lambda: os.getenv("SOPOTEK_STRIPE_ELITE_MONTHLY_PRICE_ID") or None
    )
    kafka_bootstrap_servers: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_KAFKA_BOOTSTRAP_SERVERS", "memory")
    )
    kafka_required: bool = field(
        default_factory=lambda: _env_flag("SOPOTEK_PLATFORM_KAFKA_REQUIRED", False)
    )
    kafka_client_id: str = field(default_factory=lambda: os.getenv("SOPOTEK_KAFKA_CLIENT_ID", "sopotek-platform-api"))
    kafka_group_id: str = field(default_factory=lambda: os.getenv("SOPOTEK_KAFKA_GROUP_ID", "sopotek-platform-web"))
    kafka_market_topic: str = field(default_factory=lambda: os.getenv("SOPOTEK_KAFKA_MARKET_TOPIC", "market.data"))
    kafka_execution_topic: str = field(default_factory=lambda: os.getenv("SOPOTEK_KAFKA_EXECUTION_TOPIC", "execution.events"))
    kafka_portfolio_topic: str = field(default_factory=lambda: os.getenv("SOPOTEK_KAFKA_PORTFOLIO_TOPIC", "portfolio.updates"))
    kafka_risk_topic: str = field(default_factory=lambda: os.getenv("SOPOTEK_KAFKA_RISK_TOPIC", "risk.alerts"))
    kafka_strategy_state_topic: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_KAFKA_STRATEGY_STATE_TOPIC", "strategy.state")
    )
    kafka_strategy_command_topic: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_KAFKA_STRATEGY_COMMAND_TOPIC", "strategy.commands")
    )
    kafka_trading_command_topic: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_KAFKA_TRADING_COMMAND_TOPIC", "trading.commands")
    )
    kafka_risk_command_topic: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_KAFKA_RISK_COMMAND_TOPIC", "risk.commands")
    )
    bootstrap_admin_email: str | None = field(
        default_factory=lambda: os.getenv("SOPOTEK_PLATFORM_BOOTSTRAP_ADMIN_EMAIL") or None
    )
    bootstrap_admin_password: str | None = field(
        default_factory=lambda: os.getenv("SOPOTEK_PLATFORM_BOOTSTRAP_ADMIN_PASSWORD") or None
    )

    @property
    def is_memory_kafka(self) -> bool:
        return str(self.kafka_bootstrap_servers or "").strip().lower() in {"", "memory", "inmemory"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
