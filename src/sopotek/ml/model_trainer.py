from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from sopotek.ml.dataset_builder import TARGET_COLUMN, TrainingDataset

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional dependency
    XGBClassifier = None


@dataclass(slots=True)
class ModelTrainingArtifact:
    model_name: str
    model_family: str
    model_path: Path
    sample_count: int
    feature_columns: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class TradeModelTrainer:
    """Train, evaluate, and persist trade-outcome classifiers."""

    def __init__(self, *, model_name: str = "trade_success_model", model_dir: str | Path = "data/models") -> None:
        self.model_name = str(model_name or "trade_success_model").strip() or "trade_success_model"
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    @property
    def model_path(self) -> Path:
        return self.model_dir / f"{self.model_name}.joblib"

    def train(
        self,
        dataset: TrainingDataset | pd.DataFrame | str | Path,
        *,
        model_family: str = "xgboost",
        test_size: float = 0.2,
        random_state: int = 7,
        model_path: str | Path | None = None,
    ) -> ModelTrainingArtifact:
        frame, feature_columns = self._coerce_dataset(dataset)
        if frame.empty or TARGET_COLUMN not in frame.columns:
            raise ValueError("Training dataset must include at least one row and a 'target' column.")
        if frame[TARGET_COLUMN].nunique() < 2:
            raise ValueError("Need at least two classes to train the ML model.")

        X = frame[feature_columns].fillna(0.0)
        y = frame[TARGET_COLUMN].astype(int)
        X_train, X_test, y_train, y_test, split_name = self._split_dataset(
            X,
            y,
            test_size=test_size,
            random_state=random_state,
        )

        model, resolved_family = self._build_model(model_family=model_family, random_state=random_state)
        model.fit(X_train, y_train)

        probabilities = model.predict_proba(X_test)[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        metrics = {
            "accuracy": float(accuracy_score(y_test, predictions)),
            "precision": float(precision_score(y_test, predictions, zero_division=0)),
            "recall": float(recall_score(y_test, predictions, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_test, probabilities)) if y_test.nunique() > 1 else 0.5,
            "train_samples": float(len(X_train)),
            "test_samples": float(len(X_test)),
        }

        target = Path(model_path) if model_path is not None else self.model_path
        payload = {
            "model_name": self.model_name,
            "model_family": resolved_family,
            "feature_columns": list(feature_columns),
            "metrics": dict(metrics),
            "metadata": {
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "split_strategy": split_name,
            },
            "model": model,
        }
        joblib.dump(payload, target)
        return ModelTrainingArtifact(
            model_name=self.model_name,
            model_family=resolved_family,
            model_path=target,
            sample_count=int(len(frame)),
            feature_columns=list(feature_columns),
            metrics=metrics,
            metadata=dict(payload["metadata"]),
        )

    def _coerce_dataset(self, dataset: TrainingDataset | pd.DataFrame | str | Path) -> tuple[pd.DataFrame, list[str]]:
        if isinstance(dataset, TrainingDataset):
            return dataset.frame.copy(), list(dataset.feature_columns)
        if isinstance(dataset, (str, Path)):
            frame = pd.read_csv(dataset)
        else:
            frame = pd.DataFrame(dataset).copy()
        if TARGET_COLUMN not in frame.columns:
            raise KeyError("Dataset must include a 'target' column.")
        feature_columns = [column for column in frame.columns if column != TARGET_COLUMN]
        return frame, feature_columns

    def _split_dataset(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        *,
        test_size: float,
        random_state: int,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str]:
        sample_count = len(X)
        test_count = 1 if sample_count < 6 else max(int(round(sample_count * float(test_size))), 1)
        test_count = min(test_count, sample_count - 1)
        X_train = X.iloc[:-test_count]
        X_test = X.iloc[-test_count:]
        y_train = y.iloc[:-test_count]
        y_test = y.iloc[-test_count:]
        if y_train.nunique() >= 2 and y_test.nunique() >= 1:
            split_name = "chronological_small" if sample_count < 6 else "chronological"
            return X_train, X_test, y_train, y_test, split_name

        can_stratify = int(y.value_counts().min()) >= 2 and y.nunique() >= 2
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_count if sample_count < 20 else float(test_size),
            random_state=random_state,
            shuffle=True,
            stratify=y if can_stratify else None,
        )
        return X_train, X_test, y_train, y_test, "stratified_shuffle"

    def _build_model(self, *, model_family: str, random_state: int):
        family = str(model_family or "xgboost").strip().lower()
        if family in {"xgboost", "auto"} and XGBClassifier is not None:
            return (
                XGBClassifier(
                    n_estimators=200,
                    max_depth=5,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    eval_metric="logloss",
                    random_state=random_state,
                    n_jobs=1,
                    verbosity=0,
                ),
                "xgboost",
            )
        if family in {"random_forest", "tree"}:
            return (
                RandomForestClassifier(
                    n_estimators=160,
                    max_depth=6,
                    random_state=random_state,
                ),
                "random_forest",
            )
        return GradientBoostingClassifier(random_state=random_state), "gradient_boosting"
