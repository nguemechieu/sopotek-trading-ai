from __future__ import annotations

from .ai_agent_service import AIAgentService
from .api_gateway import ApiGatewayService
from .auth_service import AuthService
from .license_subscription_service import LicenseSubscriptionService
from .market_data_service import MarketDataService
from .ml_training_pipeline import MLTrainingPipelineService
from .notification_service import NotificationService
from .portfolio_service import PortfolioService
from .risk_engine_service import RiskEngineService
from .trading_core_service import TradingCoreService
from .user_profile_service import UserProfileService


def build_service_registry() -> dict[str, object]:
    return {
        "api_gateway": ApiGatewayService(),
        "auth_service": AuthService(),
        "user_profile_service": UserProfileService(),
        "license_subscription_service": LicenseSubscriptionService(),
        "trading_core_service": TradingCoreService(),
        "risk_engine_service": RiskEngineService(),
        "portfolio_service": PortfolioService(),
        "market_data_service": MarketDataService(),
        "ai_agent_service": AIAgentService(),
        "ml_training_pipeline": MLTrainingPipelineService(),
        "notification_service": NotificationService(),
    }
