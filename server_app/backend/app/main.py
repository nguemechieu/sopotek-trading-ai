from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.db.session import create_session_factory, init_db_with_retry
from app.services.auth_rate_limiter import AuthRateLimiter
from app.services.bootstrap import ensure_bootstrap_admin
from app.services.command_service import TradingControlService
from app.services.core_bridge import TradingCoreBridge
from app.services.kafka_gateway import build_kafka_gateway
from app.services.license_service import LicenseService
from app.services.rate_limiter import SlidingWindowRateLimiter
from app.services.runtime_service import RuntimeHostService
from app.services.state_store import PlatformStateStore
from app.services.stripe_service import StripeBillingService
from app.services.terminal_service import TerminalService
from app.ws.router import router as websocket_router


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    engine, session_factory = create_session_factory(active_settings)
    platform_state = PlatformStateStore()
    kafka_gateway = build_kafka_gateway(active_settings)
    auth_rate_limiter = AuthRateLimiter(
        max_attempts=active_settings.auth_rate_limit_attempts,
        window_seconds=active_settings.auth_rate_limit_window_seconds,
    )
    license_rate_limiter = SlidingWindowRateLimiter()
    license_service = LicenseService(active_settings)
    stripe_service = StripeBillingService(active_settings, license_service)
    runtime_service = RuntimeHostService(
        settings=active_settings,
        state_store=platform_state,
    )
    control_service = TradingControlService(
        settings=active_settings,
        state_store=platform_state,
        kafka_gateway=kafka_gateway,
        runtime_service=runtime_service,
    )
    terminal_service = TerminalService(
        settings=active_settings,
        state_store=platform_state,
        control_service=control_service,
        runtime_service=runtime_service,
    )
    core_bridge = TradingCoreBridge(
        settings=active_settings,
        state_store=platform_state,
        kafka_gateway=kafka_gateway,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = active_settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.platform_state = platform_state
        app.state.kafka_gateway = kafka_gateway
        app.state.control_service = control_service
        app.state.terminal_service = terminal_service
        app.state.auth_rate_limiter = auth_rate_limiter
        app.state.license_rate_limiter = license_rate_limiter
        app.state.license_service = license_service
        app.state.stripe_service = stripe_service
        app.state.runtime_service = runtime_service

        await init_db_with_retry(
            engine,
            attempts=active_settings.database_connect_retry_attempts,
            delay_seconds=active_settings.database_connect_retry_delay_seconds,
        )
        async with session_factory() as session:
            await ensure_bootstrap_admin(session, active_settings, license_service=license_service)
            await session.commit()

        core_bridge.bind()
        await kafka_gateway.start()
        try:
            yield
        finally:
            await runtime_service.shutdown()
            await kafka_gateway.stop()
            await engine.dispose()

    app = FastAPI(
        title=active_settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {
            "status": "ok",
            "environment": active_settings.environment,
            "kafka_mode": str(getattr(kafka_gateway, "runtime_mode", "unknown")),
            "kafka_status": "degraded" if bool(getattr(kafka_gateway, "is_degraded", False)) else "ready",
        }

    app.include_router(api_router)
    app.include_router(websocket_router)
    return app


app = create_app()
