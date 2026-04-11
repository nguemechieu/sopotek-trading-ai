from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class AuthService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["auth_service"])

    async def issue_device_session(self) -> None:
        """Mint JWT, refresh lineage, and OAuth device binding records."""
