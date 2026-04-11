from __future__ import annotations

import os
from dataclasses import dataclass, field


def _flag(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class InstitutionalPlatformSettings:
    environment: str = field(default_factory=lambda: os.getenv("SOPOTEK_INSTITUTIONAL_ENV", "development"))
    region: str = field(default_factory=lambda: os.getenv("SOPOTEK_INSTITUTIONAL_REGION", "us-east-1"))
    kafka_bootstrap_servers: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_INSTITUTIONAL_KAFKA_BOOTSTRAP", "memory")
    )
    postgres_dsn: str = field(
        default_factory=lambda: os.getenv(
            "SOPOTEK_INSTITUTIONAL_POSTGRES_DSN",
            "postgresql+asyncpg://sopotek:sopotek@postgres:5432/sopotek",
        )
    )
    redis_dsn: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_INSTITUTIONAL_REDIS_DSN", "redis://redis:6379/0")
    )
    object_storage_bucket: str = field(
        default_factory=lambda: os.getenv("SOPOTEK_INSTITUTIONAL_OBJECT_BUCKET", "sopotek-institutional")
    )
    encryption_key_reference: str = field(
        default_factory=lambda: os.getenv(
            "SOPOTEK_INSTITUTIONAL_ENCRYPTION_KEY_REF",
            "aws-kms://alias/sopotek-trading-secrets",
        )
    )
    max_order_ack_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_INSTITUTIONAL_ORDER_ACK_TIMEOUT_MS", "250"))
    )
    max_event_replay_window_minutes: int = field(
        default_factory=lambda: int(os.getenv("SOPOTEK_INSTITUTIONAL_REPLAY_WINDOW_MINUTES", "1440"))
    )
    enable_auto_trading: bool = field(
        default_factory=lambda: _flag("SOPOTEK_INSTITUTIONAL_ENABLE_AUTO_TRADING", True)
    )
    enable_multi_agent: bool = field(
        default_factory=lambda: _flag("SOPOTEK_INSTITUTIONAL_ENABLE_MULTI_AGENT", True)
    )

    @property
    def is_memory_bus(self) -> bool:
        return str(self.kafka_bootstrap_servers or "").strip().lower() in {"", "memory", "inmemory"}
