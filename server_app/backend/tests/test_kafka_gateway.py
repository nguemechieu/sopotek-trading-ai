from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.kafka_gateway import AioKafkaGateway


class _FailingProducer:
    def __init__(self, *args, **kwargs) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        raise OSError("Connection refused")

    async def stop(self) -> None:
        self.stopped = True


class _IdleConsumer:
    def __init__(self, *args, **kwargs) -> None:
        self.stopped = False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        self.stopped = True


def _install_failing_aiokafka(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "aiokafka",
        SimpleNamespace(
            AIOKafkaProducer=_FailingProducer,
            AIOKafkaConsumer=_IdleConsumer,
        ),
    )


def _register_user(client: TestClient) -> str:
    response = client.post(
        "/auth/register",
        json={
            "email": "ops@sopotek.ai",
            "username": "opsdesk",
            "password": "SuperSecure123",
            "full_name": "Ops Desk",
            "role": "trader",
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_app_starts_with_in_memory_kafka_fallback(monkeypatch, tmp_path: Path) -> None:
    _install_failing_aiokafka(monkeypatch)
    settings = Settings(
        secret_key="this-is-a-demo-secret-key-with-more-than-thirty-two-chars",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'platform-kafka-fallback.db').as_posix()}",
        kafka_bootstrap_servers="kafka:9092",
        kafka_required=False,
        frontend_base_url="http://localhost:3000",
    )

    app = create_app(settings)
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["kafka_mode"] == "memory-fallback"
        assert health.json()["kafka_status"] == "degraded"

        token = _register_user(client)
        response = client.post(
            "/control/trading/start",
            json={"selected_symbols": ["EUR_USD", "BTCUSDT"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        published = client.app.state.kafka_gateway.published_messages
        assert published
        assert published[-1]["topic"] == settings.kafka_trading_command_topic
        assert published[-1]["payload"]["command"] == "start_trading"


def test_kafka_gateway_raises_when_required(monkeypatch) -> None:
    _install_failing_aiokafka(monkeypatch)
    gateway = AioKafkaGateway(
        Settings(
            kafka_bootstrap_servers="kafka:9092",
            kafka_required=True,
        )
    )

    with pytest.raises(OSError, match="Connection refused"):
        asyncio.run(gateway.start())
