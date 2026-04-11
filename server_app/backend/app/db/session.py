from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging
import socket

from sqlalchemy import event, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base, TimestampedMixin, coerce_utc_datetime


TIMESTAMPED_TABLES = (
    "users",
    "licenses",
    "devices",
    "subscriptions",
    "portfolios",
    "strategies",
    "trades",
    "logs",
    "workspace_configs",
)
TIMESTAMPED_COLUMNS = ("created_at", "updated_at")
logger = logging.getLogger(__name__)


def create_session_factory(settings: Settings) -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    return engine, session_factory


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, BaseException) else None
    return chain


def is_retryable_database_startup_error(exc: BaseException) -> bool:
    retryable_types = (OperationalError, OSError, ConnectionError, TimeoutError, socket.gaierror)
    return any(isinstance(item, retryable_types) for item in _iter_exception_chain(exc))


def _engine_timestamp_overrides(bind: Connection | Engine | None) -> dict[str, dict[str, bool]]:
    if bind is None:
        return {}
    if isinstance(bind, Connection):
        return dict(getattr(bind.engine, "_sopotek_timestamp_timezone_overrides", {}) or {})
    return dict(getattr(bind, "_sopotek_timestamp_timezone_overrides", {}) or {})


def _timestamp_timezone_flags(
    obj: TimestampedMixin,
    *,
    timezone_overrides: dict[str, dict[str, bool]] | None = None,
) -> tuple[bool, bool]:
    overrides = dict(timezone_overrides or {})
    table_name = str(getattr(obj, "__tablename__", "") or "").strip()
    table_overrides = dict(overrides.get(table_name, {}) or {})
    created_at_column = obj.__table__.c.created_at
    updated_at_column = obj.__table__.c.updated_at
    created_at_timezone = bool(
        table_overrides.get("created_at", getattr(created_at_column.type, "timezone", False))
    )
    updated_at_timezone = bool(
        table_overrides.get("updated_at", getattr(updated_at_column.type, "timezone", False))
    )
    return created_at_timezone, updated_at_timezone


def normalize_timestamped_model(
    obj: object,
    *,
    timezone_overrides: dict[str, dict[str, bool]] | None = None,
) -> None:
    if not isinstance(obj, TimestampedMixin):
        return

    created_at_timezone, updated_at_timezone = _timestamp_timezone_flags(
        obj,
        timezone_overrides=timezone_overrides,
    )

    setattr(
        obj,
        "created_at",
        coerce_utc_datetime(getattr(obj, "created_at", None), timezone_aware=created_at_timezone),
    )
    setattr(
        obj,
        "updated_at",
        coerce_utc_datetime(getattr(obj, "updated_at", None), timezone_aware=updated_at_timezone),
    )


@event.listens_for(Session, "before_flush")
def normalize_timestamped_models_before_flush(session: Session, flush_context, instances) -> None:
    timezone_overrides = _engine_timestamp_overrides(session.get_bind())
    for obj in list(session.new) + list(session.dirty):
        normalize_timestamped_model(obj, timezone_overrides=timezone_overrides)


async def inspect_postgres_timestamp_columns(connection: AsyncConnection) -> dict[str, dict[str, bool]]:
    quoted_tables = ", ".join(f"'{table_name}'" for table_name in TIMESTAMPED_TABLES)
    quoted_columns = ", ".join(f"'{column_name}'" for column_name in TIMESTAMPED_COLUMNS)
    result = await connection.execute(
        text(
            f"""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name IN ({quoted_tables})
              AND column_name IN ({quoted_columns})
            """
        )
    )
    overrides: dict[str, dict[str, bool]] = {}
    for row in result.mappings():
        overrides.setdefault(str(row["table_name"]), {})[str(row["column_name"])] = (
            str(row["data_type"]).strip().lower() == "timestamp with time zone"
        )
    return overrides


def apply_timestamp_timezone_overrides(engine: object, overrides: dict[str, dict[str, bool]]) -> None:
    sync_engine = getattr(engine, "sync_engine", engine)
    setattr(sync_engine, "_sopotek_timestamp_timezone_overrides", dict(overrides or {}))


async def repair_postgres_timestamp_columns(connection: AsyncConnection) -> None:
    quoted_tables = ", ".join(f"'{table_name}'" for table_name in TIMESTAMPED_TABLES)
    quoted_columns = ", ".join(f"'{column_name}'" for column_name in TIMESTAMPED_COLUMNS)
    await connection.execute(
        text(
            f"""
            DO $$
            DECLARE
                target RECORD;
            BEGIN
                FOR target IN
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name IN ({quoted_tables})
                      AND column_name IN ({quoted_columns})
                      AND data_type = 'timestamp without time zone'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMP WITH TIME ZONE USING %I AT TIME ZONE ''UTC''',
                        target.table_name,
                        target.column_name,
                        target.column_name
                    );
                END LOOP;
            END $$;
            """
        )
    )


async def init_db(engine: object) -> None:
    async_engine = engine
    from app.models import device, license, log, portfolio, strategy, subscription, trade, user, workspace_config  # noqa: F401

    logger.info(
        "ORM timestamp mode users.created_at timezone=%s",
        getattr(user.User.__table__.c.created_at.type, "timezone", None),
    )
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await repair_user_auth_columns(connection)
        if async_engine.dialect.name == "postgresql":
            await repair_postgres_timestamp_columns(connection)
            apply_timestamp_timezone_overrides(
                async_engine,
                await inspect_postgres_timestamp_columns(connection),
            )
        else:
            apply_timestamp_timezone_overrides(async_engine, {})


async def init_db_with_retry(
    engine: object,
    *,
    attempts: int = 1,
    delay_seconds: float = 0.0,
    initializer=None,
) -> None:
    max_attempts = max(int(attempts), 1)
    retry_delay_seconds = max(float(delay_seconds), 0.0)
    init_once = initializer or init_db

    for attempt in range(1, max_attempts + 1):
        try:
            await init_once(engine)
            return
        except Exception as exc:
            should_retry = attempt < max_attempts and is_retryable_database_startup_error(exc)
            if not should_retry:
                raise
            logger.warning(
                "Database initialization failed on attempt %s/%s; retrying in %.2fs. error=%s",
                attempt,
                max_attempts,
                retry_delay_seconds,
                exc,
            )
            if retry_delay_seconds > 0:
                await asyncio.sleep(retry_delay_seconds)


async def get_db_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


def build_user_auth_repair_statements(existing_columns: set[str]) -> list[str]:
    statements: list[str] = []
    if "email_verified" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE")
    if "two_factor_enabled" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT FALSE")
    if "two_factor_secret" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN two_factor_secret VARCHAR(64)")
    return statements


async def repair_user_auth_columns(connection: AsyncConnection) -> None:
    def _existing_columns(sync_connection) -> set[str]:
        inspector = sa_inspect(sync_connection)
        return {str(column.get("name") or "").strip() for column in inspector.get_columns("users")}

    existing_columns = await connection.run_sync(_existing_columns)
    statements = build_user_auth_repair_statements(existing_columns)

    for statement in statements:
        logger.info("Applying user auth schema repair: %s", statement)
        await connection.execute(text(statement))
