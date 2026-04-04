from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd


class InferenceEngine:
    """Runtime trade filter backed by a persisted classification model."""

    def __init__(self, model_path: str | Path | None = None, *, threshold: float = 0.7) -> None:
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.model = None
        self.model_name = "trade_success_model"
        self.model_family = "unknown"
        self.feature_columns: list[str] = []
        self.metrics: dict[str, float] = {}
        self.metadata: dict[str, Any] = {}
        if model_path is not None:
            self.load(model_path)

    @property
    def is_ready(self) -> bool:
        return self.model is not None and bool(self.feature_columns)

    def load(self, model_path: str | Path | dict[str, Any]) -> "InferenceEngine":
        payload = dict(model_path) if isinstance(model_path, dict) else joblib.load(model_path)
        self.model = payload.get("model")
        self.model_name = str(payload.get("model_name") or self.model_name)
        self.model_family = str(payload.get("model_family") or self.model_family)
        self.feature_columns = list(payload.get("feature_columns") or [])
        self.metrics = dict(payload.get("metrics") or {})
        self.metadata = dict(payload.get("metadata") or {})
        return self

    def predict_probability(self, features: dict[str, float]) -> float:
        if not self.is_ready:
            return 0.5
        row = {column: float(features.get(column, 0.0)) for column in self.feature_columns}
        frame = pd.DataFrame([row], columns=self.feature_columns).fillna(0.0)
        probability = float(self.model.predict_proba(frame)[:, 1][0])
        return max(0.0, min(1.0, probability))

    def predict(self, features: dict[str, float]) -> float:
        return self.predict_probability(features)

    def should_trade(self, features: dict[str, float], *, threshold: float | None = None) -> bool:
        limit = self.threshold if threshold is None else max(0.0, min(1.0, float(threshold)))
        return self.predict_probability(features) >= limit
