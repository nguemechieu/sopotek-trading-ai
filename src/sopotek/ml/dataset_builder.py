from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from sopotek.core.models import TradeFeedback
from sopotek.ml.feature_engineering import DEFAULT_FEATURE_COLUMNS

TARGET_COLUMN = "target"
_META_COLUMNS = {
    "symbol",
    "strategy_name",
    "side",
    "timeframe",
    "timestamp",
    "entry_price",
    "exit_price",
    "pnl",
    "success",
    "model_name",
    "model_probability",
    "metadata",
    "features",
    "target",
}


@dataclass(slots=True)
class TrainingDataset:
    frame: pd.DataFrame
    feature_columns: list[str]
    target_column: str = TARGET_COLUMN
    metadata: dict[str, Any] = field(default_factory=dict)

    def X_y(self) -> tuple[pd.DataFrame, pd.Series]:
        if self.frame.empty:
            return pd.DataFrame(columns=self.feature_columns), pd.Series(name=self.target_column, dtype="int64")
        return self.frame[self.feature_columns].copy(), self.frame[self.target_column].astype(int)


def build_trade_dataset(
    trades: pd.DataFrame | list[TradeFeedback | dict[str, Any]],
    *,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    builder = TradeDatasetBuilder(feature_columns=feature_columns)
    return builder.build_dataset(trades).frame


class TradeDatasetBuilder:
    """Converts trade feedback records into ML-ready supervised datasets."""

    def __init__(self, *, feature_columns: list[str] | None = None) -> None:
        self.preferred_feature_columns = list(feature_columns or DEFAULT_FEATURE_COLUMNS)

    def build_dataset(
        self,
        trades: pd.DataFrame | list[TradeFeedback | dict[str, Any]],
        *,
        dataset_name: str = "trade_feedback",
    ) -> TrainingDataset:
        frame = self._coerce_frame(trades)
        if frame.empty:
            return TrainingDataset(pd.DataFrame(columns=[TARGET_COLUMN]), [], metadata={"dataset_name": dataset_name, "samples": 0})

        frame = frame.sort_values("timestamp").reset_index(drop=True) if "timestamp" in frame.columns else frame.reset_index(drop=True)
        feature_columns = self._resolve_feature_columns(frame)
        dataset_frame = frame[feature_columns + [TARGET_COLUMN]].dropna().reset_index(drop=True)
        metadata = {
            "dataset_name": dataset_name,
            "samples": int(len(dataset_frame)),
            "feature_count": int(len(feature_columns)),
        }
        if "timestamp" in frame.columns and not frame.empty:
            metadata["start_timestamp"] = str(frame["timestamp"].iloc[0])
            metadata["end_timestamp"] = str(frame["timestamp"].iloc[-1])
        return TrainingDataset(dataset_frame, feature_columns, metadata=metadata)

    def export_csv(
        self,
        path: str | Path,
        trades: pd.DataFrame | list[TradeFeedback | dict[str, Any]],
        *,
        dataset_name: str = "trade_feedback",
    ) -> Path:
        dataset = self.build_dataset(trades, dataset_name=dataset_name)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        dataset.frame.to_csv(target, index=False)
        return target

    def _coerce_frame(self, trades: pd.DataFrame | list[TradeFeedback | dict[str, Any]]) -> pd.DataFrame:
        if isinstance(trades, pd.DataFrame):
            return self._from_dataframe(trades)
        return self._from_feedback_rows(list(trades or []))

    def _from_feedback_rows(self, feedback_rows: list[TradeFeedback | dict[str, Any]]) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for row in feedback_rows:
            feedback = row if isinstance(row, TradeFeedback) else TradeFeedback(**dict(row))
            pnl = float(feedback.pnl)
            record: dict[str, Any] = {
                "symbol": feedback.symbol,
                "strategy_name": feedback.strategy_name,
                "side": feedback.side,
                "timeframe": feedback.timeframe,
                "timestamp": feedback.timestamp,
                "entry_price": float(feedback.entry_price),
                "exit_price": float(feedback.exit_price),
                "pnl": pnl,
                "success": bool(feedback.success),
                "model_name": feedback.model_name,
                "model_probability": feedback.model_probability,
                "side_bias": 1.0 if str(feedback.side).lower() == "buy" else -1.0,
                TARGET_COLUMN: int(bool(feedback.success) if feedback.success is not None else pnl > 0),
            }
            if feedback.model_probability is not None:
                record["prior_model_probability"] = float(feedback.model_probability)
            for key, value in dict(feedback.features or {}).items():
                try:
                    record[str(key)] = float(value)
                except Exception:
                    continue
            records.append(record)
        return pd.DataFrame.from_records(records)

    def _from_dataframe(self, trades: pd.DataFrame) -> pd.DataFrame:
        frame = trades.copy()
        if "features" in frame.columns:
            expanded = frame["features"].apply(self._feature_payload).apply(pd.Series)
            frame = pd.concat([frame.drop(columns=["features"]), expanded], axis=1)
        if "features_json" in frame.columns:
            expanded = frame["features_json"].apply(self._feature_payload).apply(pd.Series)
            frame = pd.concat([frame.drop(columns=["features_json"]), expanded], axis=1)

        if TARGET_COLUMN not in frame.columns:
            if "success" in frame.columns:
                frame[TARGET_COLUMN] = frame["success"].astype(bool).astype(int)
            elif "pnl" in frame.columns:
                frame[TARGET_COLUMN] = (pd.to_numeric(frame["pnl"], errors="coerce").fillna(0.0) > 0).astype(int)
            elif {"entry_price", "exit_price"}.issubset(frame.columns):
                pnl = pd.to_numeric(frame["exit_price"], errors="coerce") - pd.to_numeric(frame["entry_price"], errors="coerce")
                frame["pnl"] = pnl
                frame[TARGET_COLUMN] = (pnl.fillna(0.0) > 0).astype(int)
            else:
                raise KeyError("Dataset requires one of: target, success, pnl, or entry_price/exit_price")

        if "side" in frame.columns and "side_bias" not in frame.columns:
            frame["side_bias"] = frame["side"].apply(lambda value: 1.0 if str(value).lower() == "buy" else -1.0)
        if "model_probability" in frame.columns and "prior_model_probability" not in frame.columns:
            frame["prior_model_probability"] = pd.to_numeric(frame["model_probability"], errors="coerce")

        for column in frame.columns:
            if column in _META_COLUMNS:
                continue
            frame[column] = pd.to_numeric(frame[column], errors="ignore")
        return frame

    def _resolve_feature_columns(self, frame: pd.DataFrame) -> list[str]:
        preferred = [column for column in self.preferred_feature_columns if column in frame.columns]
        numeric_columns = [
            column
            for column in frame.columns
            if column not in _META_COLUMNS and pd.api.types.is_numeric_dtype(frame[column])
        ]
        extras = [column for column in numeric_columns if column not in preferred]
        return preferred + extras

    def _feature_payload(self, payload: Any) -> dict[str, Any]:
        if payload in (None, "", {}):
            return {}
        if isinstance(payload, dict):
            return dict(payload)
        try:
            if pd.isna(payload):
                return {}
        except Exception:
            pass
        try:
            import json

            decoded = json.loads(str(payload))
        except Exception:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
