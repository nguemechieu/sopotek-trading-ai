from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import socket

from sqlalchemy import DateTime

from app.db.base import coerce_utc_datetime
from app.db.session import (
    build_user_auth_repair_statements,
    init_db_with_retry,
    is_retryable_database_startup_error,
    normalize_timestamped_model,
)
from app.models.log import LogEntry
from app.models.portfolio import Portfolio
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.user import User


def test_timestamp_columns_are_timezone_aware() -> None:
    for model in (User, Portfolio, Strategy, Trade, LogEntry):
        created_at_type = model.__table__.c.created_at.type
        updated_at_type = model.__table__.c.updated_at.type

        assert isinstance(created_at_type, DateTime)
        assert created_at_type.timezone is True
        assert isinstance(updated_at_type, DateTime)
        assert updated_at_type.timezone is True


def test_coerce_utc_datetime_handles_naive_and_aware_inputs() -> None:
    aware_value = datetime(2026, 4, 6, 20, 49, 53, tzinfo=timezone.utc)
    naive_value = datetime(2026, 4, 6, 20, 49, 53)

    coerced_aware = coerce_utc_datetime(aware_value, timezone_aware=True)
    coerced_naive = coerce_utc_datetime(aware_value, timezone_aware=False)

    assert coerced_aware.tzinfo == timezone.utc
    assert coerced_naive.tzinfo is None
    assert coerce_utc_datetime(naive_value, timezone_aware=True).tzinfo == timezone.utc


def test_normalize_timestamped_model_stamps_timezone_aware_columns() -> None:
    user = User(
        email="trader@sopotek.ai",
        username="fundtrader",
        full_name="Fund Trader",
        password_hash="hash",
    )
    normalize_timestamped_model(user)

    assert user.created_at.tzinfo == timezone.utc
    assert user.updated_at.tzinfo == timezone.utc


def test_normalize_timestamped_model_can_follow_live_naive_schema_override() -> None:
    user = User(
        email="legacy@sopotek.ai",
        username="legacytrader",
        full_name="Legacy Trader",
        password_hash="hash",
    )
    normalize_timestamped_model(
        user,
        timezone_overrides={"users": {"created_at": False, "updated_at": False}},
    )

    assert user.created_at.tzinfo is None
    assert user.updated_at.tzinfo is None


def test_user_auth_repair_statements_use_boolean_false_defaults() -> None:
    statements = build_user_auth_repair_statements({"id", "email", "username"})

    assert "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE" in statements
    assert "ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT FALSE" in statements
    assert "ALTER TABLE users ADD COLUMN two_factor_secret VARCHAR(64)" in statements


def test_retryable_database_startup_error_detects_nested_dns_failure() -> None:
    wrapped = RuntimeError("database startup failed")
    wrapped.__cause__ = socket.gaierror(-2, "Name or service not known")

    assert is_retryable_database_startup_error(wrapped) is True


def test_init_db_with_retry_retries_then_succeeds() -> None:
    attempts: list[int] = []

    async def flaky_initializer(_engine: object) -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise socket.gaierror(-2, "Name or service not known")

    asyncio.run(
        init_db_with_retry(
            object(),
            attempts=3,
            delay_seconds=0.0,
            initializer=flaky_initializer,
        )
    )

    assert len(attempts) == 3
