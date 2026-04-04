from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from sopotek.core.models import TradeFeedback
from sopotek.ml.dataset_builder import TARGET_COLUMN, TradeDatasetBuilder
from sopotek.ml.inference_engine import InferenceEngine
from sopotek.ml.model_registry import ModelRegistry
from sopotek.ml.model_trainer import TradeModelTrainer


@dataclass(slots=True)
class TrainingReport:
    model_name: str
    sample_count: int
    feature_columns: list[str]
    metrics: dict[str, float] = field(default_factory=dict)


class TradeOutcomeTrainingPipeline:
    """End-to-end trade outcome pipeline for dataset building, training, and inference."""

    def __init__(
        self,
        *,
        model_name: str = "trade_success_model",
        model_dir: str | Path = "data/models",
        dataset_builder: TradeDatasetBuilder | None = None,
        trainer: TradeModelTrainer | None = None,
        model_registry: ModelRegistry | None = None,
        inference_engine: InferenceEngine | None = None,
    ) -> None:
        self.model_name = str(model_name or "trade_success_model").strip() or "trade_success_model"
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_builder = dataset_builder or TradeDatasetBuilder()
        self.trainer = trainer or TradeModelTrainer(model_name=self.model_name, model_dir=self.model_dir)
        self.model_registry = model_registry or ModelRegistry(self.model_dir)
        self.inference_engine = inference_engine or InferenceEngine()
        self.feature_columns: list[str] = []
        self.metrics: dict[str, float] = {}
        self.model: Any | None = None

    @property
    def model_path(self) -> Path:
        active_path = self.model_registry.resolve_path(self.model_name)
        return active_path or self.trainer.model_path

    @property
    def is_fitted(self) -> bool:
        return self.inference_engine.is_ready

    def build_training_frame(self, feedback_rows: list[TradeFeedback | dict[str, Any]]) -> pd.DataFrame:
        dataset = self.dataset_builder.build_dataset(feedback_rows, dataset_name="trade_feedback")
        return dataset.frame.copy()

    def fit_from_feedback(
        self,
        feedback_rows: list[TradeFeedback | dict[str, Any]],
        *,
        model_family: str = "xgboost",
        test_size: float = 0.25,
        random_state: int = 7,
    ) -> TrainingReport:
        dataset = self.dataset_builder.build_dataset(feedback_rows, dataset_name="trade_feedback")
        frame = dataset.frame
        if frame.empty or frame[TARGET_COLUMN].nunique() < 2:
            raise ValueError("Need at least two labeled trade outcomes to train the ML pipeline.")

        artifact = self.trainer.train(
            dataset,
            model_family=model_family,
            test_size=test_size,
            random_state=random_state,
        )
        self.load(artifact.model_path)
        self.model_registry.register(
            self.model_name,
            artifact.model_path,
            feature_columns=artifact.feature_columns,
            metrics=artifact.metrics,
            metadata=artifact.metadata,
            set_active=True,
        )
        return TrainingReport(
            model_name=self.model_name,
            sample_count=int(len(frame)),
            feature_columns=list(self.feature_columns),
            metrics=dict(self.metrics),
        )

    def predict_probability(self, features: dict[str, float]) -> float:
        return self.inference_engine.predict_probability(features)

    def save(self, path: str | Path | None = None) -> Path:
        if not self.is_fitted:
            raise ValueError("Cannot save an unfitted ML pipeline.")
        payload = {
            "model_name": self.inference_engine.model_name,
            "model_family": self.inference_engine.model_family,
            "feature_columns": list(self.feature_columns),
            "metrics": dict(self.metrics),
            "metadata": dict(self.inference_engine.metadata),
            "model": self.model,
        }
        target = Path(path) if path is not None else self.model_path
        joblib.dump(payload, target)
        return target

    def load(self, path: str | Path | None = None) -> "TradeOutcomeTrainingPipeline":
        source = Path(path) if path is not None else (self.model_registry.resolve_path("latest") or self.model_path)
        payload = joblib.load(source)
        self.inference_engine.load(payload)
        self.model_name = self.inference_engine.model_name
        self.feature_columns = list(self.inference_engine.feature_columns)
        self.metrics = dict(self.inference_engine.metrics)
        self.model = self.inference_engine.model
        return self

    def load_active(self) -> "TradeOutcomeTrainingPipeline":
        active = self.model_registry.resolve_path("latest")
        if active is None:
            raise FileNotFoundError("No active model is registered.")
        return self.load(active)
