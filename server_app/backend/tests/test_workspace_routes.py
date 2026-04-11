from __future__ import annotations


def _register_user(client, *, role: str = "trader"):
    response = client.post(
        "/auth/register",
        json={
            "email": "config@sopotek.ai",
            "username": "configdesk",
            "password": "SuperSecure123",
            "full_name": "Config Desk",
            "role": role,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_workspace_settings_require_auth(client) -> None:
    response = client.get("/workspace/settings")
    assert response.status_code == 401


def test_workspace_settings_default_and_persist(client) -> None:
    token = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    initial_response = client.get("/workspace/settings", headers=headers)
    assert initial_response.status_code == 200
    initial_payload = initial_response.json()
    assert initial_payload["broker_type"] == "paper"
    assert initial_payload["exchange"] == "paper"
    assert initial_payload["mode"] == "paper"
    assert initial_payload["risk_percent"] == 2
    assert initial_payload["paper_starting_equity"] == 100000.0
    assert initial_payload["profile_name"] == ""
    assert initial_payload["risk_profile_name"] == "Balanced"
    assert initial_payload["timeframe"] == "1h"
    assert initial_payload["order_type"] == "limit"
    assert initial_payload["strategy_name"] == "Trend Following"
    assert initial_payload["max_portfolio_risk"] == 0.1
    assert initial_payload["max_risk_per_trade"] == 0.02
    assert initial_payload["max_position_size_pct"] == 0.1
    assert initial_payload["max_gross_exposure_pct"] == 2.0
    assert initial_payload["hedging_enabled"] is True
    assert initial_payload["margin_closeout_guard_enabled"] is True
    assert initial_payload["max_margin_closeout_pct"] == 0.5
    assert initial_payload["strategy_rsi_period"] == 14
    assert initial_payload["strategy_ema_fast"] == 20
    assert initial_payload["strategy_ema_slow"] == 50
    assert initial_payload["watchlist_symbols"] == []
    assert initial_payload["ai_assistance_enabled"] is True
    assert initial_payload["auto_improve_enabled"] is True
    assert initial_payload["openai_model"] == "gpt-5-mini"
    assert initial_payload["desktop_sync_enabled"] is False
    assert initial_payload["desktop_last_sync_source"] == "unknown"

    update_response = client.put(
        "/workspace/settings",
        headers=headers,
        json={
            "language": "en",
            "broker_type": "crypto",
            "exchange": "coinbase",
            "customer_region": "us",
            "mode": "live",
            "market_type": "spot",
            "ibkr_connection_mode": "webapi",
            "ibkr_environment": "gateway",
            "ibkr_base_url": "",
            "ibkr_websocket_url": "",
            "ibkr_host": "",
            "ibkr_port": "",
            "ibkr_client_id": "",
            "schwab_environment": "sandbox",
            "api_key": "coinbase-key",
            "secret": "coinbase-secret",
            "password": "",
            "account_id": "desk-001",
            "risk_percent": 3,
            "paper_starting_equity": 250000,
            "remember_profile": True,
            "profile_name": "coinbase_main",
            "risk_profile_name": "Institutional",
            "max_portfolio_risk": 0.12,
            "max_risk_per_trade": 0.03,
            "max_position_size_pct": 0.08,
            "max_gross_exposure_pct": 1.8,
            "hedging_enabled": False,
            "margin_closeout_guard_enabled": True,
            "max_margin_closeout_pct": 0.45,
            "timeframe": "4h",
            "order_type": "market",
            "strategy_name": "Adaptive Trend",
            "strategy_rsi_period": 12,
            "strategy_ema_fast": 18,
            "strategy_ema_slow": 48,
            "strategy_atr_period": 12,
            "strategy_oversold_threshold": 32.0,
            "strategy_overbought_threshold": 68.0,
            "strategy_breakout_lookback": 24,
            "strategy_min_confidence": 0.62,
            "strategy_signal_amount": 1.5,
            "watchlist_symbols": ["BTC_USDT", "ETH_USDT"],
            "ai_assistance_enabled": True,
            "auto_improve_enabled": True,
            "openai_api_key": "sk-test",
            "openai_model": "gpt-5-mini",
            "desktop_sync_enabled": True,
            "desktop_device_name": "desktop-trader-01",
            "desktop_app_version": "desktop-2026.04",
            "desktop_last_sync_at": "2026-04-06T20:55:00Z",
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
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["exchange"] == "coinbase"
    assert update_payload["mode"] == "live"
    assert update_payload["account_id"] == "desk-001"
    assert update_payload["risk_percent"] == 3
    assert update_payload["paper_starting_equity"] == 250000
    assert update_payload["profile_name"] == "coinbase_main"
    assert update_payload["risk_profile_name"] == "Institutional"
    assert update_payload["timeframe"] == "4h"
    assert update_payload["order_type"] == "market"
    assert update_payload["strategy_name"] == "Adaptive Trend"
    assert update_payload["max_portfolio_risk"] == 0.12
    assert update_payload["max_risk_per_trade"] == 0.03
    assert update_payload["max_position_size_pct"] == 0.08
    assert update_payload["max_gross_exposure_pct"] == 1.8
    assert update_payload["watchlist_symbols"] == ["BTC_USDT", "ETH_USDT"]
    assert update_payload["openai_model"] == "gpt-5-mini"
    assert update_payload["desktop_sync_enabled"] is True
    assert update_payload["desktop_device_name"] == "desktop-trader-01"
    assert update_payload["desktop_last_sync_source"] == "desktop"

    persisted_response = client.get("/workspace/settings", headers=headers)
    assert persisted_response.status_code == 200
    persisted_payload = persisted_response.json()
    assert persisted_payload["exchange"] == "coinbase"
    assert persisted_payload["broker_type"] == "crypto"
    assert persisted_payload["account_id"] == "desk-001"
    assert persisted_payload["profile_name"] == "coinbase_main"
    assert persisted_payload["timeframe"] == "4h"
    assert persisted_payload["order_type"] == "market"
    assert persisted_payload["strategy_name"] == "Adaptive Trend"
    assert persisted_payload["watchlist_symbols"] == ["BTC_USDT", "ETH_USDT"]
    assert persisted_payload["desktop_sync_enabled"] is True
    assert persisted_payload["desktop_app_version"] == "desktop-2026.04"

    portfolio_response = client.get("/portfolio", headers=headers)
    assert portfolio_response.status_code == 200
    portfolio_payload = portfolio_response.json()
    assert portfolio_payload["broker"] == "coinbase"
    assert portfolio_payload["account_id"] == "desk-001"
    assert portfolio_payload["risk_limits"]["risk_percent"] == 3
    assert portfolio_payload["risk_limits"]["max_risk_per_trade"] == 0.03
    assert portfolio_payload["risk_limits"]["timeframe"] == "4h"
    assert portfolio_payload["risk_limits"]["strategy_name"] == "Adaptive Trend"


def test_workspace_manifest_reflects_backend_navigation(client) -> None:
    token = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/workspace/manifest", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_route"] == "/dashboard"
    assert payload["role"] == "trader"
    assert "workspace" in payload["available_features"]
    hrefs = {item["href"] for item in payload["navigation"] if item["visible"]}
    assert "/dashboard" in hrefs
    assert "/terminal" in hrefs
    assert "/orders" in hrefs


def test_admin_workspace_manifest_includes_license_admin_page(client) -> None:
    token = _register_user(client, role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/workspace/manifest", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "admin"
    hrefs = {item["href"] for item in payload["navigation"] if item["visible"]}
    assert "/admin" in hrefs
    assert "/admin/licenses" in hrefs
    assert "/admin/users" in hrefs
