from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.institutional.example_gateway import create_app
from app.institutional.events import EventTopic


def test_architecture_and_order_flow() -> None:
    app = create_app()

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        architecture = client.get("/v1/architecture/overview")
        assert architecture.status_code == 200
        assert architecture.json()["services"]

        first_tick = client.post(
            "/v1/market/ticks",
            json={
                "symbol": "EUR_USD",
                "venue": "oanda",
                "bid": 1.1000,
                "ask": 1.1002,
                "last_price": 1.1001,
                "volume_24h": 1000000,
                "ts_event": datetime.now(UTC).isoformat(),
            },
        )
        assert first_tick.status_code == 202

        second_tick = client.post(
            "/v1/market/ticks",
            json={
                "symbol": "EUR_USD",
                "venue": "oanda",
                "bid": 1.1150,
                "ask": 1.1152,
                "last_price": 1.1151,
                "volume_24h": 1005000,
                "ts_event": datetime.now(UTC).isoformat(),
            },
        )
        assert second_tick.status_code == 202

        order = client.post(
            "/v1/orders",
            json={
                "account_id": "acct-fx-001",
                "user_id": "opsdesk",
                "symbol": "EUR_USD",
                "side": "buy",
                "quantity": 10000,
                "entry_price": 1.1151,
                "stop_price": 1.1090,
                "asset_class": "fx",
            },
        )
        assert order.status_code == 201
        order_payload = order.json()
        order_id = order_payload["order"]["order_id"]
        assert order_payload["route"]["venue"] == "oanda"

        execution = client.post(
            f"/v1/orders/{order_id}/execute",
            json={
                "fill_price": 1.1152,
                "filled_quantity": 10000,
                "fees": 3.5,
                "liquidity": "maker",
            },
        )
        assert execution.status_code == 200

        events = client.get("/v1/events")
        assert events.status_code == 200
        topics = [event["topic"] for event in events.json()["events"]]
        assert EventTopic.MARKET_TICK.value in topics
        assert EventTopic.STRATEGY_SIGNAL.value in topics
        assert EventTopic.ORDER_CREATED.value in topics
        assert EventTopic.ORDER_EXECUTED.value in topics
        assert EventTopic.PORTFOLIO_UPDATE.value in topics

        notifications = client.get("/v1/notifications")
        assert notifications.status_code == 200
        assert notifications.json()["notifications"]
