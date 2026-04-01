import os
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.exc import OperationalError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage import database as storage_db


def test_normalize_database_url_repairs_mysql_scheme_and_charset_typo():
    normalized = storage_db.normalize_database_url(
        " mysql://sopotek:sopotek_local@localhost:3306/sopotek_trading?chartset=utf8mb4 "
    )

    assert normalized == (
        "mysql+pymysql://sopotek:sopotek_local@localhost:3306/"
        "sopotek_trading?charset=utf8mb4"
    )


def test_sqlite_engine_configures_busy_timeout_and_wal(tmp_path):
    database_path = tmp_path / "sqlite-pragmas.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = storage_db._create_engine(database_url)

    try:
        with engine.connect() as connection:
            busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()
            journal_mode = str(connection.execute(text("PRAGMA journal_mode")).scalar_one()).lower()

        assert busy_timeout == storage_db.SQLITE_BUSY_TIMEOUT_MS
        assert journal_mode == "wal"
    finally:
        engine.dispose()


def test_run_with_sqlite_lock_retry_retries_transient_lock(monkeypatch):
    calls = {"count": 0}
    monkeypatch.setattr(storage_db.time, "sleep", lambda _seconds: None)

    def flaky_operation():
        calls["count"] += 1
        if calls["count"] == 1:
            raise OperationalError("PRAGMA main.table_info('trades')", {}, Exception("database is locked"))
        return "ok"

    result = storage_db._run_with_sqlite_lock_retry(
        flaky_operation,
        database_url="sqlite:///memory-test.sqlite3",
    )

    assert result == "ok"
    assert calls["count"] == 2


def test_configure_database_normalizes_remote_url_before_storing(monkeypatch):
    created_urls = []
    previous_engine = storage_db.engine
    previous_session_local = storage_db.SessionLocal
    previous_url = storage_db.DATABASE_URL
    previous_env = os.environ.get("SOPOTEK_DATABASE_URL")

    fake_previous_engine = SimpleNamespace(dispose=lambda: None)
    fake_next_engine = SimpleNamespace(dispose=lambda: None)

    monkeypatch.setattr(storage_db, "engine", fake_previous_engine)
    monkeypatch.setattr(storage_db, "_create_engine", lambda database_url: created_urls.append(database_url) or fake_next_engine)
    monkeypatch.setattr(storage_db, "_create_session_factory", lambda active_engine: ("session-factory", active_engine))

    try:
        configured = storage_db.configure_database(
            "mysql://user:secret@localhost:3306/sopotek_trading?chartset=utf8mb4"
        )

        assert configured == "mysql+pymysql://user:secret@localhost:3306/sopotek_trading?charset=utf8mb4"
        assert created_urls == [configured]
        assert storage_db.DATABASE_URL == configured
        assert os.environ["SOPOTEK_DATABASE_URL"] == configured
    finally:
        storage_db.engine = previous_engine
        storage_db.SessionLocal = previous_session_local
        storage_db.DATABASE_URL = previous_url
        if previous_env is None:
            os.environ.pop("SOPOTEK_DATABASE_URL", None)
        else:
            os.environ["SOPOTEK_DATABASE_URL"] = previous_env
