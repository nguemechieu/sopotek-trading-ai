from __future__ import annotations

from dataclasses import asdict

from ..blueprints import ServiceBlueprint


class InstitutionalService:
    def __init__(self, blueprint: ServiceBlueprint) -> None:
        self.blueprint = blueprint

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def describe(self) -> dict[str, object]:
        payload = asdict(self.blueprint)
        payload["publishes"] = [topic.value for topic in self.blueprint.publishes]
        payload["consumes"] = [topic.value for topic in self.blueprint.consumes]
        return payload
