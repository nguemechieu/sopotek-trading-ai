from __future__ import annotations


def _register_user(client):
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


def test_start_trading_publishes_command(client) -> None:
    token = _register_user(client)
    response = client.post(
        "/control/trading/start",
        json={"selected_symbols": ["EUR_USD", "XAU_USD"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["trading_enabled"] is True
    assert payload["selected_symbols"] == ["EUR_USD", "XAU_USD"]

    published = client.app.state.kafka_gateway.published_messages
    assert published
    assert published[-1]["topic"] == client.app.state.settings.kafka_trading_command_topic
    assert published[-1]["payload"]["command"] == "start_trading"


def test_submit_order_persists_trade(client) -> None:
    token = _register_user(client)
    response = client.post(
        "/orders",
        json={
            "symbol": "EUR_USD",
            "side": "buy",
            "quantity": 10000,
            "order_type": "market",
            "venue": "oanda",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["symbol"] == "EUR_USD"
    assert payload["status"] == "pending"

    orders_response = client.get("/orders", headers={"Authorization": f"Bearer {token}"})
    assert orders_response.status_code == 200
    assert len(orders_response.json()) == 1


class _FakePaperMarketBroker:
    async def connect(self):
        return True

    async def close(self):
        return True

    async def fetch_ticker(self, symbol):
        return {
            "symbol": symbol,
            "last": 101.25,
            "bid": 101.0,
            "ask": 101.5,
            "percentage": 0.8,
            "baseVolume": 2500,
        }

    async def fetch_ohlcv(self, symbol, timeframe="1m", limit=48):
        _ = symbol, timeframe, limit
        return [
            [1712500000000, 100.0, 101.0, 99.5, 100.8, 1200],
            [1712500060000, 100.8, 101.6, 100.4, 101.25, 1800],
        ]

    async def fetch_orderbook(self, symbol, limit=12):
        _ = symbol, limit
        return {
            "bids": [[101.0, 5.0], [100.9, 4.0]],
            "asks": [[101.5, 5.0], [101.6, 4.0]],
        }


class _FakeOandaBroker:
    async def connect(self):
        return True

    async def close(self):
        return True

    async def fetch_ticker(self, symbol):
        return {
            "symbol": symbol,
            "last": 1.1025,
            "bid": 1.1024,
            "ask": 1.1026,
            "percentage": 0.3,
            "baseVolume": 12500,
        }

    async def fetch_ohlcv(self, symbol, timeframe="1m", limit=48):
        _ = symbol, timeframe, limit
        return [
            [1712500000000, 1.1010, 1.1020, 1.1005, 1.1018, 1200],
            [1712500060000, 1.1018, 1.1027, 1.1015, 1.1025, 1800],
        ]

    async def fetch_orderbook(self, symbol, limit=12):
        _ = symbol, limit
        return {
            "bids": [[1.1024, 100000], [1.1023, 100000]],
            "asks": [[1.1026, 100000], [1.1027, 100000]],
        }

    async def fetch_balance(self):
        return {
            "free": {"USD": 15000.0},
            "used": {"USD": 2500.0},
            "total": {"USD": 17500.0},
            "equity": 17620.0,
            "currency": "USD",
        }

    async def fetch_positions(self):
        return []


def test_start_trading_boots_runtime_and_fills_paper_orders(client, monkeypatch) -> None:
    token = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    workspace_response = client.put(
        "/workspace/settings",
        json={
            "language": "en",
            "broker_type": "crypto",
            "exchange": "coinbase",
            "customer_region": "us",
            "mode": "paper",
            "market_type": "spot",
            "ibkr_connection_mode": "webapi",
            "ibkr_environment": "gateway",
            "ibkr_base_url": "",
            "ibkr_websocket_url": "",
            "ibkr_host": "",
            "ibkr_port": "",
            "ibkr_client_id": "",
            "schwab_environment": "sandbox",
            "api_key": "",
            "secret": "",
            "password": "",
            "account_id": "paper-coinbase",
            "risk_percent": 2,
            "paper_starting_equity": 50000,
            "remember_profile": True,
            "profile_name": "paper_coinbase",
            "watchlist_symbols": ["BTC_USDT"],
            "ai_assistance_enabled": True,
            "auto_improve_enabled": True,
            "openai_api_key": "",
            "openai_model": "gpt-5-mini",
            "desktop_sync_enabled": False,
            "desktop_device_name": "",
            "desktop_app_version": "",
            "desktop_last_sync_at": None,
            "desktop_last_sync_source": "unknown",
            "solana": {
                "wallet_address": "",
                "private_key": "",
                "rpc_url": "",
                "jupiter_api_key": "",
                "okx_api_key": "",
                "okx_secret": "",
                "okx_passphrase": "",
                "okx_project_id": "",
            },
        },
        headers=headers,
    )
    assert workspace_response.status_code == 200

    async def fake_create_broker(settings):
        _ = settings
        return _FakePaperMarketBroker()

    monkeypatch.setattr(client.app.state.runtime_service, "_create_broker", fake_create_broker)

    start_response = client.post(
        "/control/trading/start",
        json={"selected_symbols": ["BTC_USDT"]},
        headers=headers,
    )
    assert start_response.status_code == 200
    start_payload = start_response.json()
    assert start_payload["runtime"]["active"] is True
    assert start_payload["runtime"]["exchange"] == "coinbase"

    order_response = client.post(
        "/orders",
        json={
            "symbol": "BTC_USDT",
            "side": "buy",
            "quantity": 1.5,
            "order_type": "market",
            "venue": "terminal",
        },
        headers=headers,
    )
    assert order_response.status_code == 202
    order_payload = order_response.json()
    assert order_payload["status"] == "filled"
    assert order_payload["average_price"] == 101.5
    assert order_payload["filled_quantity"] == 1.5

    positions_response = client.get("/positions", headers=headers)
    assert positions_response.status_code == 200
    positions_payload = positions_response.json()
    assert len(positions_payload) == 1
    assert positions_payload[0]["symbol"] == "BTC_USDT"

    portfolio_response = client.get("/portfolio", headers=headers)
    assert portfolio_response.status_code == 200
    portfolio_payload = portfolio_response.json()
    assert portfolio_payload["broker"] == "coinbase:paper"
    assert portfolio_payload["selected_symbols"] == ["BTC_USDT"]
    assert portfolio_payload["active_positions"] == 1


def test_start_trading_boots_oanda_with_default_symbols_when_watchlist_is_empty(client, monkeypatch) -> None:
    token = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    workspace_response = client.put(
        "/workspace/settings",
        json={
            "language": "en",
            "broker_type": "forex",
            "exchange": "oanda",
            "customer_region": "us",
            "mode": "live",
            "market_type": "otc",
            "ibkr_connection_mode": "webapi",
            "ibkr_environment": "gateway",
            "ibkr_base_url": "",
            "ibkr_websocket_url": "",
            "ibkr_host": "",
            "ibkr_port": "",
            "ibkr_client_id": "",
            "schwab_environment": "sandbox",
            "api_key": "oanda-token",
            "secret": "",
            "password": "",
            "account_id": "acct-1",
            "risk_percent": 1,
            "paper_starting_equity": 100000,
            "remember_profile": True,
            "profile_name": "oanda_live",
            "watchlist_symbols": [],
            "ai_assistance_enabled": True,
            "auto_improve_enabled": True,
            "openai_api_key": "",
            "openai_model": "gpt-5-mini",
            "desktop_sync_enabled": False,
            "desktop_device_name": "",
            "desktop_app_version": "",
            "desktop_last_sync_at": None,
            "desktop_last_sync_source": "unknown",
            "solana": {
                "wallet_address": "",
                "private_key": "",
                "rpc_url": "",
                "jupiter_api_key": "",
                "okx_api_key": "",
                "okx_secret": "",
                "okx_passphrase": "",
                "okx_project_id": "",
            },
        },
        headers=headers,
    )
    assert workspace_response.status_code == 200

    async def fake_create_broker(settings):
        _ = settings
        return _FakeOandaBroker()

    monkeypatch.setattr(client.app.state.runtime_service, "_create_broker", fake_create_broker)

    start_response = client.post(
        "/control/trading/start",
        json={"selected_symbols": []},
        headers=headers,
    )
    assert start_response.status_code == 200
    payload = start_response.json()
    assert payload["selected_symbols"] == ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"]
    assert payload["runtime"]["active"] is True
    assert payload["runtime"]["selected_symbols"] == ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"]

    portfolio_response = client.get("/portfolio", headers=headers)
    assert portfolio_response.status_code == 200
    portfolio_payload = portfolio_response.json()
    assert portfolio_payload["broker"] == "oanda"
    assert portfolio_payload["selected_symbols"] == ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"]
