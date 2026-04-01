from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split

from sopotek.core.models import TradeFeedback

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional dependency
    XGBClassifier = None


@dataclass(slots=True)
class TrainingReport:
    model_name: str
    sample_count: int
    feature_columns: list[str]
    metrics: dict[str, float] = field(default_factory=dict)


class TradeOutcomeTrainingPipeline:
    """Trains a probability-of-success model from trade feedback records."""

    def __init__(
        self,
        *,
        model_name: str = "trade_success_model",
        model_dir: str | Path = "data/models",
    ) -> None:
        self.model_name = model_name
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model: Any | None = None
        self.feature_columns: list[str] = []
        self.metrics: dict[str, float] = {}

    @property
    def model_path(self) -> Path:
        return self.model_dir / f"{self.model_name}.joblib"

    @property
    def is_fitted(self) -> bool:
        return self.model is not None and bool(self.feature_columns)

    def build_training_frame(self, feedback_rows: list[TradeFeedback | dict[str, Any]]) -> pd.DataFrame:
        records: list[dict[str, float | int]] = []
        for row in feedback_rows:
            feedback = row if isinstance(row, TradeFeedback) else TradeFeedback(**dict(row))
            if not feedback.features:
                continue
            record: dict[str, float | int] = {key: float(value) for key, value in feedback.features.items()}
            record["side_bias"] = 1.0 if str(feedback.side).lower() == "buy" else -1.0
            record["target"] = int(bool(feedback.success))
            if feedback.model_probability is not None:
                record["prior_model_probability"] = float(feedback.model_probability)
            records.append(record)
        return pd.DataFrame.from_records(records)

    def fit_from_feedback(
        self,
        feedback_rows: list[TradeFeedback | dict[str, Any]],
        *,
        model_family: str = "auto",
        test_size: float = 0.25,
        random_state: int = 7,
    ) -> TrainingReport:
        frame = self.build_training_frame(feedback_rows)
        if frame.empty or frame["target"].nunique() < 2:
            raise ValueError("Need at least two labeled trade outcomes to train the ML pipeline.")

        X = frame.drop(columns=["target"]).fillna(0.0)
        y = frame["target"].astype(int)
        self.feature_columns = list(X.columns)
        class_count = int(y.nunique())
        test_fraction = float(test_size)
        if len(frame) < 8:
            test_fraction = 0.5
        test_count = max(int(round(len(frame) * test_fraction)), class_count)
        if test_count >= len(frame):
            test_count = max(1, len(frame) - class_count)
        can_stratify = class_count > 1 and int(y.value_counts().min()) >= 2 and test_count >= class_count

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_count if len(frame) < 20 else test_fraction,
            random_state=random_state,
            stratify=y if can_stratify else None,
        )

        self.model = self._build_model(model_family=model_family, random_state=random_state)
        self.model.fit(X_train, y_train)

        probabilities = self.model.predict_proba(X_test)[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        self.metrics = {
            "accuracy": float(accuracy_score(y_test, predictions)),
            "roc_auc": float(roc_auc_score(y_test, probabilities)) if y_test.nunique() > 1 else 0.5,
            "train_samples": float(len(X_train)),
            "test_samples": float(len(X_test)),
        }
        self.save()
        return TrainingReport(
            model_name=self.model_name,
            sample_count=int(len(frame)),
            feature_columns=list(self.feature_columns),
            metrics=dict(self.metrics),
        )

    def predict_probability(self, features: dict[str, float]) -> float:
        if not self.is_fitted:
            return 0.5
        row = {column: float(features.get(column, 0.0)) for column in self.feature_columns}
        frame = pd.DataFrame([row], columns=self.feature_columns).fillna(0.0)
        probability = float(self.model.predict_proba(frame)[:, 1][0])
        return max(0.0, min(1.0, probability))

    def save(self, path: str | Path | None = None) -> Path:
        if not self.is_fitted:
            raise ValueError("Cannot save an unfitted ML pipeline.")
        target = Path(path) if path is not None else self.model_path
        payload = {
            "model_name": self.model_name,
            "feature_columns": list(self.feature_columns),
            "metrics": dict(self.metrics),
            "model": self.model,
        }
        joblib.dump(payload, target)
        return target

    def load(self, path: str | Path | None = None) -> "TradeOutcomeTrainingPipeline":
        source = Path(path) if path is not None else self.model_path
        payload = joblib.load(source)
        self.model_name = str(payload.get("model_name") or self.model_name)
        self.feature_columns = list(payload.get("feature_columns") or [])
        self.metrics = dict(payload.get("metrics") or {})
        self.model = payload.get("model")
        return self

    def _build_model(self, *, model_family: str, random_state: int):
        family = str(model_family or "auto").strip().lower()
        if family in {"xgboost", "auto"} and XGBClassifier is not None:
            return XGBClassifier(
                n_estimators=60,
                max_depth=3,
                learning_rate=0.08,
                subsample=0.9,
                colsample_bytree=0.9,
                eval_metric="logloss",
                random_state=random_state,
            )
        if family == "tree":
            return RandomForestClassifier(
                n_estimators=120,
                max_depth=5,
                random_state=random_state,
            )
        return GradientBoostingClassifier(random_state=random_state)
