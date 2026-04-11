from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sopotek.ml.dataset_builder import TARGET_COLUMN, TradeDatasetBuilder, TrainingDataset, build_trade_dataset
    from sopotek.ml.feature_engineering import (
        DEFAULT_FEATURE_COLUMNS,
        build_features,
        candles_to_frame,
        compute_ema,
        compute_indicator_features,
        compute_rsi,
        compute_volatility,
    )
    from sopotek.ml.filter import MLFilterEngine
    from sopotek.ml.inference_engine import InferenceEngine
    from sopotek.ml.model_registry import ModelRegistry, RegisteredModel
    from sopotek.ml.model_trainer import ModelTrainingArtifact, TradeModelTrainer
    from sopotek.ml.pipeline import TradeOutcomeTrainingPipeline, TrainingReport
    from sopotek.ml.regime_engine import RegimeEngine
    from sopotek.ml.retraining_scheduler import RetrainingScheduler, retrain_loop

__all__ = [
    "DEFAULT_FEATURE_COLUMNS",
    "InferenceEngine",
    "MLFilterEngine",
    "ModelRegistry",
    "ModelTrainingArtifact",
    "RegisteredModel",
    "RegimeEngine",
    "RetrainingScheduler",
    "TARGET_COLUMN",
    "TradeDatasetBuilder",
    "TradeModelTrainer",
    "TradeOutcomeTrainingPipeline",
    "TrainingDataset",
    "TrainingReport",
    "build_features",
    "build_trade_dataset",
    "candles_to_frame",
    "compute_ema",
    "compute_indicator_features",
    "compute_rsi",
    "compute_volatility",
    "retrain_loop",
]

_LAZY_EXPORTS = {
    "TARGET_COLUMN": ("sopotek.ml.dataset_builder", "TARGET_COLUMN"),
    "TradeDatasetBuilder": ("sopotek.ml.dataset_builder", "TradeDatasetBuilder"),
    "TrainingDataset": ("sopotek.ml.dataset_builder", "TrainingDataset"),
    "build_trade_dataset": ("sopotek.ml.dataset_builder", "build_trade_dataset"),
    "DEFAULT_FEATURE_COLUMNS": ("sopotek.ml.feature_engineering", "DEFAULT_FEATURE_COLUMNS"),
    "build_features": ("sopotek.ml.feature_engineering", "build_features"),
    "candles_to_frame": ("sopotek.ml.feature_engineering", "candles_to_frame"),
    "compute_ema": ("sopotek.ml.feature_engineering", "compute_ema"),
    "compute_indicator_features": ("sopotek.ml.feature_engineering", "compute_indicator_features"),
    "compute_rsi": ("sopotek.ml.feature_engineering", "compute_rsi"),
    "compute_volatility": ("sopotek.ml.feature_engineering", "compute_volatility"),
    "MLFilterEngine": ("sopotek.ml.filter", "MLFilterEngine"),
    "InferenceEngine": ("sopotek.ml.inference_engine", "InferenceEngine"),
    "ModelRegistry": ("sopotek.ml.model_registry", "ModelRegistry"),
    "RegisteredModel": ("sopotek.ml.model_registry", "RegisteredModel"),
    "ModelTrainingArtifact": ("sopotek.ml.model_trainer", "ModelTrainingArtifact"),
    "TradeModelTrainer": ("sopotek.ml.model_trainer", "TradeModelTrainer"),
    "TradeOutcomeTrainingPipeline": ("sopotek.ml.pipeline", "TradeOutcomeTrainingPipeline"),
    "TrainingReport": ("sopotek.ml.pipeline", "TrainingReport"),
    "RegimeEngine": ("sopotek.ml.regime_engine", "RegimeEngine"),
    "RetrainingScheduler": ("sopotek.ml.retraining_scheduler", "RetrainingScheduler"),
    "retrain_loop": ("sopotek.ml.retraining_scheduler", "retrain_loop"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
