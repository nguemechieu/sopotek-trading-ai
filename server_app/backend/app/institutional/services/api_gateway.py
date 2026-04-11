from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class ApiGatewayService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["api_gateway"])

    async def route_desktop_command(self) -> None:
        """Validate auth/session state, then dispatch an operator command onto Kafka."""
