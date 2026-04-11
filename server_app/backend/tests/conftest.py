from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        secret_key="this-is-a-demo-secret-key-with-more-than-thirty-two-chars",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'platform-test.db').as_posix()}",
        kafka_bootstrap_servers="memory",
        frontend_base_url="http://localhost:3000",
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
