from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import LicensePlan, LicenseStatus, UserRole


class SolanaWorkspaceSettings(BaseModel):
    wallet_address: str = ""
    private_key: str = ""
    rpc_url: str = ""
    jupiter_api_key: str = ""
    okx_api_key: str = ""
    okx_secret: str = ""
    okx_passphrase: str = ""
    okx_project_id: str = ""


class WorkspaceSettings(BaseModel):
    language: str = "en"
    broker_type: Literal["crypto", "forex", "stocks", "options", "futures", "derivatives", "paper"] = "paper"
    exchange: str = "paper"
    customer_region: Literal["us", "global"] = "us"
    mode: Literal["live", "paper"] = "paper"
    market_type: Literal["auto", "spot", "derivative", "option", "otc"] = "auto"
    ibkr_connection_mode: Literal["webapi", "tws"] = "webapi"
    ibkr_environment: Literal["gateway", "hosted"] = "gateway"
    ibkr_base_url: str = ""
    ibkr_websocket_url: str = ""
    ibkr_host: str = ""
    ibkr_port: str = ""
    ibkr_client_id: str = ""
    schwab_environment: Literal["sandbox", "production"] = "sandbox"
    api_key: str = ""
    secret: str = ""
    password: str = ""
    account_id: str = ""
    risk_percent: int = Field(default=2, ge=1, le=100)
    paper_starting_equity: float = Field(default=100000.0, ge=1000.0)
    remember_profile: bool = True
    profile_name: str = ""
    risk_profile_name: str = "Balanced"
    max_portfolio_risk: float = Field(default=0.10, ge=0.0, le=1.0)
    max_risk_per_trade: float = Field(default=0.02, ge=0.0, le=1.0)
    max_position_size_pct: float = Field(default=0.10, ge=0.0, le=1.0)
    max_gross_exposure_pct: float = Field(default=2.0, ge=0.0, le=10.0)
    hedging_enabled: bool = True
    margin_closeout_guard_enabled: bool = True
    max_margin_closeout_pct: float = Field(default=0.50, ge=0.01, le=1.0)
    timeframe: str = "1h"
    order_type: Literal["market", "limit", "stop_limit", "stop"] = "limit"
    strategy_name: str = "Trend Following"
    strategy_rsi_period: int = Field(default=14, ge=2)
    strategy_ema_fast: int = Field(default=20, ge=2)
    strategy_ema_slow: int = Field(default=50, ge=3)
    strategy_atr_period: int = Field(default=14, ge=2)
    strategy_oversold_threshold: float = Field(default=35.0)
    strategy_overbought_threshold: float = Field(default=65.0)
    strategy_breakout_lookback: int = Field(default=20, ge=2)
    strategy_min_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    strategy_signal_amount: float = Field(default=1.0, gt=0.0)
    watchlist_symbols: list[str] = Field(default_factory=list)
    ai_assistance_enabled: bool = True
    auto_improve_enabled: bool = True
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    desktop_sync_enabled: bool = False
    desktop_device_name: str = ""
    desktop_app_version: str = ""
    desktop_last_sync_at: datetime | None = None
    desktop_last_sync_source: Literal["desktop", "web", "unknown"] = "unknown"
    solana: SolanaWorkspaceSettings = Field(default_factory=SolanaWorkspaceSettings)

    @model_validator(mode="after")
    def normalize_fields(self) -> "WorkspaceSettings":
        self.language = str(self.language or "en").strip() or "en"
        self.exchange = str(self.exchange or "paper").strip().lower() or "paper"
        self.api_key = str(self.api_key or "").strip()
        self.secret = str(self.secret or "").strip()
        self.password = str(self.password or "").strip()
        self.account_id = str(self.account_id or "").strip()
        self.paper_starting_equity = max(1000.0, float(self.paper_starting_equity or 100000.0))
        self.risk_profile_name = str(self.risk_profile_name or "Balanced").strip() or "Balanced"
        self.max_portfolio_risk = max(0.0, min(1.0, float(self.max_portfolio_risk)))
        self.max_risk_per_trade = max(0.0, min(1.0, float(self.max_risk_per_trade)))
        self.max_position_size_pct = max(0.0, min(1.0, float(self.max_position_size_pct)))
        self.max_gross_exposure_pct = max(0.0, min(10.0, float(self.max_gross_exposure_pct)))
        self.hedging_enabled = bool(self.hedging_enabled)
        self.margin_closeout_guard_enabled = bool(self.margin_closeout_guard_enabled)
        self.max_margin_closeout_pct = max(0.01, min(1.0, float(self.max_margin_closeout_pct)))
        self.timeframe = str(self.timeframe or "1h").strip().lower() or "1h"
        self.order_type = str(self.order_type or "limit").strip().lower() or "limit"
        if self.order_type not in {"market", "limit", "stop_limit", "stop"}:
            self.order_type = "limit"
        self.strategy_name = str(self.strategy_name or "Trend Following").strip() or "Trend Following"
        self.strategy_rsi_period = max(2, int(self.strategy_rsi_period))
        self.strategy_ema_fast = max(2, int(self.strategy_ema_fast))
        self.strategy_ema_slow = max(3, int(self.strategy_ema_slow))
        if self.strategy_ema_fast >= self.strategy_ema_slow:
            self.strategy_ema_fast = max(2, self.strategy_ema_slow - 1)
        self.strategy_atr_period = max(2, int(self.strategy_atr_period))
        self.strategy_oversold_threshold = float(self.strategy_oversold_threshold)
        self.strategy_overbought_threshold = float(self.strategy_overbought_threshold)
        if self.strategy_oversold_threshold >= self.strategy_overbought_threshold:
            self.strategy_oversold_threshold = min(self.strategy_oversold_threshold, self.strategy_overbought_threshold - 1.0)
        self.strategy_breakout_lookback = max(2, int(self.strategy_breakout_lookback))
        self.strategy_min_confidence = max(0.0, min(1.0, float(self.strategy_min_confidence)))
        self.strategy_signal_amount = max(0.0001, float(self.strategy_signal_amount))
        self.watchlist_symbols = [str(symbol or "").strip().upper() for symbol in list(self.watchlist_symbols or []) if str(symbol or "").strip()]
        self.ai_assistance_enabled = bool(self.ai_assistance_enabled)
        self.auto_improve_enabled = bool(self.auto_improve_enabled)
        self.openai_api_key = str(self.openai_api_key or "").strip()
        self.openai_model = str(self.openai_model or "gpt-5-mini").strip() or "gpt-5-mini"
        self.ibkr_base_url = str(self.ibkr_base_url or "").strip()
        self.ibkr_websocket_url = str(self.ibkr_websocket_url or "").strip()
        self.ibkr_host = str(self.ibkr_host or "").strip()
        self.ibkr_port = str(self.ibkr_port or "").strip()
        self.ibkr_client_id = str(self.ibkr_client_id or "").strip()
        self.profile_name = str(self.profile_name or "").strip()
        self.desktop_device_name = str(self.desktop_device_name or "").strip()
        self.desktop_app_version = str(self.desktop_app_version or "").strip()
        sync_source = str(self.desktop_last_sync_source or "unknown").strip().lower() or "unknown"
        self.desktop_last_sync_source = sync_source if sync_source in {"desktop", "web", "unknown"} else "unknown"
        if self.broker_type == "paper" or self.exchange == "paper":
            self.mode = "paper"
            self.exchange = "paper"
            self.broker_type = "paper"
        return self


class WorkspaceSettingsResponse(WorkspaceSettings):
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspacePageEntry(BaseModel):
    id: str
    href: str
    label: str
    detail: str
    roles: list[UserRole] = Field(default_factory=list)
    required_features: list[str] = Field(default_factory=list)
    visible: bool = True
    writable: bool = False
    status: Literal["enabled", "preview", "locked"] = "enabled"


class WorkspaceManifestResponse(BaseModel):
    default_route: str = "/dashboard"
    role: UserRole
    license_plan: LicensePlan | None = None
    license_status: LicenseStatus | None = None
    available_features: list[str] = Field(default_factory=list)
    navigation: list[WorkspacePageEntry] = Field(default_factory=list)
    recent_updates: list[str] = Field(default_factory=list)
    platform_version: str = "1.0.0"
