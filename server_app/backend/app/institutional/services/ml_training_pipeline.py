from __future__ import annotations

from ..blueprints import SERVICE_BLUEPRINTS
from .base import InstitutionalService


class MLTrainingPipelineService(InstitutionalService):
    def __init__(self) -> None:
        super().__init__(SERVICE_BLUEPRINTS["ml_training_pipeline"])

    async def launch_retraining_cycle(self) -> None:
        """Build features, backtest, retrain, evaluate, and promote a model artifact."""
