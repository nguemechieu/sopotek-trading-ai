from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_license_service
from app.core.security import get_current_user, get_db, require_roles
from app.models.enums import LicensePlan, UserRole
from app.models.portfolio import Portfolio
from app.models.user import User
from app.models.workspace_config import WorkspaceConfig
from app.schemas.workspace import (
    WorkspaceManifestResponse,
    WorkspacePageEntry,
    WorkspaceSettings,
    WorkspaceSettingsResponse,
)


router = APIRouter()


WORKSPACE_PAGE_DEFINITIONS = [
    {
        "id": "dashboard",
        "href": "/dashboard",
        "label": "Control Panel",
        "detail": "Portfolio, watchlist, AI signals, notifications, and launch parameters.",
        "roles": [UserRole.ADMIN, UserRole.TRADER, UserRole.VIEWER],
        "required_features": ["workspace"],
        "writable_roles": [UserRole.ADMIN, UserRole.TRADER],
    },
    {
        "id": "terminal",
        "href": "/terminal",
        "label": "Terminal",
        "detail": "Guided command workspace for market, risk, strategy, and execution tasks.",
        "roles": [UserRole.ADMIN, UserRole.TRADER, UserRole.VIEWER],
        "required_features": ["workspace"],
        "writable_roles": [UserRole.ADMIN, UserRole.TRADER],
    },
    {
        "id": "market",
        "href": "/market",
        "label": "Market View",
        "detail": "Live watchlists, price structure, and instrument-level context.",
        "roles": [UserRole.ADMIN, UserRole.TRADER, UserRole.VIEWER],
        "required_features": ["market_monitoring"],
        "writable_roles": [],
    },
    {
        "id": "strategies",
        "href": "/strategies",
        "label": "Strategies",
        "detail": "Strategy state, performance, and assignment controls.",
        "roles": [UserRole.ADMIN, UserRole.TRADER, UserRole.VIEWER],
        "required_features": ["workspace"],
        "writable_roles": [UserRole.ADMIN, UserRole.TRADER],
    },
    {
        "id": "orders",
        "href": "/orders",
        "label": "Orders & Trades",
        "detail": "Execution flow, fills, and trade lifecycle history.",
        "roles": [UserRole.ADMIN, UserRole.TRADER, UserRole.VIEWER],
        "required_features": ["manual_trading"],
        "writable_roles": [UserRole.ADMIN, UserRole.TRADER],
    },
    {
        "id": "risk",
        "href": "/risk",
        "label": "Risk",
        "detail": "Exposure, drawdown, and desk-level risk controls.",
        "roles": [UserRole.ADMIN, UserRole.TRADER, UserRole.VIEWER],
        "required_features": ["workspace"],
        "writable_roles": [UserRole.ADMIN, UserRole.TRADER],
    },
    {
        "id": "admin",
        "href": "/admin",
        "label": "Admin",
        "detail": "Platform control center for operators managing workspace access, trading surfaces, and entitlements.",
        "roles": [UserRole.ADMIN],
        "required_features": ["admin_controls"],
        "writable_roles": [UserRole.ADMIN],
    },
    {
        "id": "admin-licenses",
        "href": "/admin/licenses",
        "label": "License Admin",
        "detail": "Issue, verify, and manage desktop and platform license entitlements.",
        "roles": [UserRole.ADMIN],
        "required_features": ["admin_controls"],
        "writable_roles": [UserRole.ADMIN],
    },
    {
        "id": "admin-users",
        "href": "/admin/users",
        "label": "User Admin",
        "detail": "Create operator accounts, promote admins, and manage authentication access across the platform.",
        "roles": [UserRole.ADMIN],
        "required_features": ["admin_controls"],
        "writable_roles": [UserRole.ADMIN],
    },
]


def _resolve_available_features(*, role: UserRole, license_service, license_plan) -> list[str]:
    resolved_plan = license_plan or LicensePlan.FREE
    features = set(license_service.plan_definition(resolved_plan).features)
    features.add("workspace")
    if role in {UserRole.ADMIN, UserRole.TRADER}:
        features.add("manual_trading")
    if role == UserRole.ADMIN:
        features.add("institutional_risk")
        features.add("admin_controls")
    return sorted(features)


def _build_workspace_manifest(
    *,
    current_user: User,
    available_features: list[str],
    license_plan,
    license_status,
    platform_version: str,
) -> WorkspaceManifestResponse:
    feature_set = set(available_features)
    navigation: list[WorkspacePageEntry] = []
    for definition in WORKSPACE_PAGE_DEFINITIONS:
        visible = current_user.role in definition["roles"] and (
            not definition["required_features"] or any(item in feature_set for item in definition["required_features"])
        )
        navigation.append(
            WorkspacePageEntry(
                id=definition["id"],
                href=definition["href"],
                label=definition["label"],
                detail=definition["detail"],
                roles=list(definition["roles"]),
                required_features=list(definition["required_features"]),
                visible=visible,
                writable=current_user.role in definition["writable_roles"],
                status="enabled" if visible else "locked",
            )
        )
    visible_routes = [item.href for item in navigation if item.visible]
    default_route = "/dashboard" if "/dashboard" in visible_routes else (visible_routes[0] if visible_routes else "/dashboard")
    return WorkspaceManifestResponse(
        default_route=default_route,
        role=current_user.role,
        license_plan=license_plan,
        license_status=license_status,
        available_features=available_features,
        navigation=navigation,
        recent_updates=[
            "Integrated terminal is now part of the backend workspace contract.",
            "Navigation and page access are driven by the backend manifest instead of hardcoded frontend lists.",
            "Control center, risk, market, strategy, order, and terminal pages now share one backend-aware workspace model.",
            "Admin operators can now manage platform and desktop licenses from the shared control plane.",
        ],
        platform_version=platform_version,
    )


def _serialize_workspace_config(config: WorkspaceConfig | None) -> WorkspaceSettingsResponse:
    settings = WorkspaceSettings.model_validate((config.settings_json if config is not None else {}) or {})
    return WorkspaceSettingsResponse(
        **settings.model_dump(),
        created_at=getattr(config, "created_at", None),
        updated_at=getattr(config, "updated_at", None),
    )


@router.get("/settings", response_model=WorkspaceSettingsResponse)
async def get_workspace_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceSettingsResponse:
    config = await db.scalar(select(WorkspaceConfig).where(WorkspaceConfig.user_id == current_user.id))
    return _serialize_workspace_config(config)


@router.put("/settings", response_model=WorkspaceSettingsResponse)
async def update_workspace_settings(
    payload: WorkspaceSettings,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TRADER)),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceSettingsResponse:
    config = await db.scalar(select(WorkspaceConfig).where(WorkspaceConfig.user_id == current_user.id))
    if config is None:
        config = WorkspaceConfig(user_id=current_user.id, settings_json={})
        db.add(config)

    normalized = WorkspaceSettings.model_validate(payload.model_dump())
    config.settings_json = normalized.model_dump(mode="json")

    portfolio = await db.scalar(
        select(Portfolio).where(Portfolio.user_id == current_user.id).order_by(Portfolio.updated_at.desc())
    )
    if portfolio is None:
        portfolio = Portfolio(user_id=current_user.id, account_id="primary", broker="paper", risk_limits={})
        db.add(portfolio)

    merged_risk_limits = dict(portfolio.risk_limits or {})
    merged_risk_limits.update(
        {
            "risk_percent": normalized.risk_percent,
            "risk_profile_name": normalized.risk_profile_name,
            "max_portfolio_risk": normalized.max_portfolio_risk,
            "max_risk_per_trade": normalized.max_risk_per_trade,
            "max_position_size_pct": normalized.max_position_size_pct,
            "max_gross_exposure_pct": normalized.max_gross_exposure_pct,
            "hedging_enabled": normalized.hedging_enabled,
            "margin_closeout_guard_enabled": normalized.margin_closeout_guard_enabled,
            "max_margin_closeout_pct": normalized.max_margin_closeout_pct,
            "timeframe": normalized.timeframe,
            "order_type": normalized.order_type,
            "strategy_name": normalized.strategy_name,
            "strategy_rsi_period": normalized.strategy_rsi_period,
            "strategy_ema_fast": normalized.strategy_ema_fast,
            "strategy_ema_slow": normalized.strategy_ema_slow,
            "strategy_atr_period": normalized.strategy_atr_period,
            "strategy_oversold_threshold": normalized.strategy_oversold_threshold,
            "strategy_overbought_threshold": normalized.strategy_overbought_threshold,
            "strategy_breakout_lookback": normalized.strategy_breakout_lookback,
            "strategy_min_confidence": normalized.strategy_min_confidence,
            "strategy_signal_amount": normalized.strategy_signal_amount,
            "broker_type": normalized.broker_type,
            "exchange": normalized.exchange,
            "mode": normalized.mode,
            "market_type": normalized.market_type,
            "remember_profile": normalized.remember_profile,
        }
    )
    portfolio.account_id = normalized.account_id or "primary"
    portfolio.broker = normalized.exchange or normalized.broker_type or "paper"
    portfolio.risk_limits = merged_risk_limits

    await db.flush()
    await db.commit()
    await db.refresh(config)
    return _serialize_workspace_config(config)


@router.get("/manifest", response_model=WorkspaceManifestResponse)
async def get_workspace_manifest(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    license_service=Depends(get_license_service),
) -> WorkspaceManifestResponse:
    license = await license_service.get_primary_license(db, current_user.id)
    available_features = _resolve_available_features(
        role=current_user.role,
        license_service=license_service,
        license_plan=getattr(license, "plan", None),
    )
    return _build_workspace_manifest(
        current_user=current_user,
        available_features=available_features,
        license_plan=getattr(license, "plan", None),
        license_status=getattr(license, "status", None),
        platform_version="2026.04.control-center",
    )
