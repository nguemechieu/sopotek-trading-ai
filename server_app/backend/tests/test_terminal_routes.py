from __future__ import annotations


def _register_and_authenticate(client, *, email: str, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "SuperSecure123",
            "full_name": "Terminal User",
            "role": "trader",
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_terminal_manifest_and_help_command(client) -> None:
    headers = _register_and_authenticate(client, email="terminal@sopotek.ai", username="terminaldesk")

    manifest_response = client.get("/terminal/manifest", headers=headers)
    assert manifest_response.status_code == 200
    manifest_payload = manifest_response.json()
    assert manifest_payload["active_terminal_id"]
    assert manifest_payload["active_terminal_label"]
    assert manifest_payload["broker_label"] == "PAPER"
    assert any(item["kind"] == "execution" for item in manifest_payload["terminals"])
    assert any(item["command"] == "/trade" for item in manifest_payload["commands"])
    assert any(item["command"] == "/assist" for item in manifest_payload["commands"])
    assert any(item["command"] == "/params" for item in manifest_payload["commands"])
    trade_spec = next(item for item in manifest_payload["commands"] if item["command"] == "/trade")
    assert any(param["name"] == "order_type" for param in trade_spec["parameters"])
    assert manifest_payload["desktop_defaults"]["timeframe"] == "1h"
    assert manifest_payload["desktop_defaults"]["order_type"] == "limit"

    help_response = client.post("/terminal/execute", json={"command": "/help"}, headers=headers)
    assert help_response.status_code == 200
    help_payload = help_response.json()
    assert help_payload["status"] == "ok"
    assert help_payload["terminal_id"] == "default"
    assert any("/markets" in line for line in help_payload["lines"])


def test_terminal_trade_and_history(client) -> None:
    headers = _register_and_authenticate(client, email="trade@sopotek.ai", username="tradedesk")
    terminal_id = "coinbase-main--execution"

    trade_response = client.post(
        "/terminal/execute",
        json={
            "command": "/trade BTCUSDT long 0.01 order_type=limit limit_price=102500 stop_loss=99500 take_profit=110000 timeframe=4h",
            "terminal_id": terminal_id,
        },
        headers=headers,
    )
    assert trade_response.status_code == 200
    trade_payload = trade_response.json()
    assert trade_payload["status"] == "ok"
    assert trade_payload["terminal_id"] == terminal_id
    assert trade_payload["data"]["symbol"] == "BTCUSDT"
    assert trade_payload["data"]["order_type"] == "limit"
    assert trade_payload["data"]["timeframe"] == "4h"
    assert trade_payload["data"]["limit_price"] == 102500.0
    assert trade_payload["data"]["stop_loss"] == 99500.0
    assert trade_payload["data"]["take_profit"] == 110000.0

    history_response = client.get(f"/terminal/history?terminal_id={terminal_id}", headers=headers)
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert history_payload
    assert history_payload[0]["command"].startswith("/trade")
    assert history_payload[0]["terminal_id"] == terminal_id

    other_history_response = client.get("/terminal/history?terminal_id=coinbase-main--review", headers=headers)
    assert other_history_response.status_code == 200
    assert other_history_response.json() == []

    orders_response = client.get("/orders", headers=headers)
    assert orders_response.status_code == 200
    orders_payload = orders_response.json()
    assert orders_payload[0]["requested_price"] == 102500.0
    assert orders_payload[0]["details"]["timeframe"] == "4h"
    assert orders_payload[0]["details"]["stop_loss"] == 99500.0
    assert orders_payload[0]["details"]["take_profit"] == 110000.0


def test_terminal_assist_uses_runtime_service(client, monkeypatch) -> None:
    headers = _register_and_authenticate(client, email="assist@sopotek.ai", username="assistdesk")

    async def fake_assist(user_id: str, question: str) -> dict[str, str]:
        _ = user_id, question
        return {"provider": "runtime", "answer": "Risk is contained and BTC_USDT remains the main focus symbol."}

    monkeypatch.setattr(client.app.state.runtime_service, "assist", fake_assist)

    response = client.post(
        "/terminal/execute",
        json={"command": "/assist Summarize the current desk risk"},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["provider"] == "runtime"
    assert any("Risk is contained" in line for line in payload["lines"])


def test_terminal_params_reflect_workspace_settings(client) -> None:
    headers = _register_and_authenticate(client, email="params@sopotek.ai", username="paramsdesk")

    workspace_response = client.put(
        "/workspace/settings",
        headers=headers,
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
            "paper_starting_equity": 75000,
            "remember_profile": True,
            "profile_name": "desk-alpha",
            "risk_profile_name": "Tactical",
            "max_portfolio_risk": 0.11,
            "max_risk_per_trade": 0.025,
            "max_position_size_pct": 0.09,
            "max_gross_exposure_pct": 1.6,
            "hedging_enabled": False,
            "margin_closeout_guard_enabled": True,
            "max_margin_closeout_pct": 0.42,
            "timeframe": "4h",
            "order_type": "market",
            "strategy_name": "Adaptive Trend",
            "strategy_rsi_period": 12,
            "strategy_ema_fast": 18,
            "strategy_ema_slow": 48,
            "strategy_atr_period": 12,
            "strategy_oversold_threshold": 33.0,
            "strategy_overbought_threshold": 67.0,
            "strategy_breakout_lookback": 24,
            "strategy_min_confidence": 0.61,
            "strategy_signal_amount": 1.4,
            "watchlist_symbols": ["BTC_USDT"],
            "ai_assistance_enabled": True,
            "auto_improve_enabled": True,
            "openai_api_key": "",
            "openai_model": "gpt-5-mini",
            "desktop_sync_enabled": True,
            "desktop_device_name": "desktop-a",
            "desktop_app_version": "desktop-2026.04",
            "desktop_last_sync_at": "2026-04-07T07:30:00Z",
            "desktop_last_sync_source": "desktop",
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
    )
    assert workspace_response.status_code == 200

    manifest_response = client.get("/terminal/manifest", headers=headers)
    assert manifest_response.status_code == 200
    manifest_payload = manifest_response.json()
    assert manifest_payload["desktop_defaults"]["timeframe"] == "4h"
    assert manifest_payload["desktop_defaults"]["order_type"] == "market"
    assert manifest_payload["desktop_defaults"]["risk_profile_name"] == "Tactical"
    assert manifest_payload["broker_label"] == "COINBASE"
    assert manifest_payload["account_label"] == "desk-alpha"
    assert any(item["label"].startswith("COINBASE desk-alpha") for item in manifest_payload["terminals"])

    params_response = client.post("/terminal/execute", json={"command": "/params"}, headers=headers)
    assert params_response.status_code == 200
    params_payload = params_response.json()
    assert params_payload["status"] == "ok"
    assert any("Timeframe :: 4h" in line for line in params_payload["lines"])
    assert any("Order type :: market" in line for line in params_payload["lines"])
    assert any("Risk profile :: Tactical" in line for line in params_payload["lines"])
