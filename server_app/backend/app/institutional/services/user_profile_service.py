from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class UserProfileService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["user_profile_service"])

    async def update_watchlists(self) -> None:
        """Persist operator workspace preferences and broker profile metadata."""
