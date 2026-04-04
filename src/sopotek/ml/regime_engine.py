from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from sopotek.core.models import Candle, RegimeSnapshot
from sopotek.ml.feature_engineering import build_features, candles_to_frame

try:
    from sklearn.cluster import KMeans
except Exception:  # pragma: no cover - optional dependency path
    KMeans = None


class RegimeEngine:
    """Cluster-aware market regime detector with a heuristic fallback."""

    VERSION = "regime-v2"
    FEATURE_COLUMNS = [
        "return_1",
        "ema_gap",
        "rsi",
        "volatility",
        "zscore",
        "range_pct",
        "volume_ratio",
        "momentum_3",
        "momentum_10",
    ]

    def __init__(self, *, n_clusters: int = 4, random_state: int = 7) -> None:
        self.n_clusters = max(2, int(n_clusters))
        self.random_state = int(random_state)
        self.model = None
        self.cluster_profiles: dict[int, dict[str, float | str]] = {}

    @property
    def is_fitted(self) -> bool:
        return self.model is not None and bool(self.cluster_profiles)

    def fit(self, frame: pd.DataFrame) -> "RegimeEngine":
        features = self._prepare_frame(frame)
        if features.empty or len(features) < self.n_clusters or KMeans is None:
            self.model = None
            self.cluster_profiles = {}
            return self

        model = KMeans(n_clusters=self.n_clusters, n_init=10, random_state=self.random_state)
        labels = model.fit_predict(features[self.FEATURE_COLUMNS])
        profiles: dict[int, dict[str, float | str]] = {}
        working = features.copy()
        working["cluster_id"] = labels
        for cluster_id, bucket in working.groupby("cluster_id"):
            profiles[int(cluster_id)] = self._cluster_profile(bucket)
        self.model = model
        self.cluster_profiles = profiles
        return self

    def classify_frame(
        self,
        frame: pd.DataFrame,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> RegimeSnapshot:
        features = self._prepare_frame(frame)
        if features.empty:
            return RegimeSnapshot(
                symbol=str(symbol or ""),
                timeframe=str(timeframe or "1m"),
                regime="unknown",
                metadata={"version": self.VERSION, "method": "empty"},
            )

        row = features.iloc[-1]
        cluster_id = self._predict_cluster(row)
        profile = self.cluster_profiles.get(cluster_id if cluster_id is not None else -1, {})
        regime = str(profile.get("regime") or self._heuristic_regime(row)).strip() or "unknown"
        volatility_regime = str(profile.get("volatility_regime") or self._volatility_regime(float(row.get("volatility") or 0.0))).strip() or "unknown"
        preferred_strategy = str(profile.get("preferred_strategy") or self._preferred_strategy(regime, volatility_regime, row)).strip() or None
        return RegimeSnapshot(
            symbol=str(symbol or row.get("symbol") or ""),
            timeframe=str(timeframe or row.get("timeframe") or "1m"),
            regime=regime,
            volatility_regime=volatility_regime,
            trend_strength=float(abs(row.get("ema_gap") or 0.0)),
            momentum=float(row.get("momentum_3") or row.get("momentum_10") or 0.0),
            band_position=float(row.get("zscore") or 0.0),
            atr_pct=float(row.get("range_pct") or 0.0),
            cluster_id=cluster_id,
            preferred_strategy=preferred_strategy,
            metadata={
                "version": self.VERSION,
                "method": "kmeans" if self.is_fitted and cluster_id is not None else "heuristic",
                "cluster_profile": dict(profile),
                "feature_row": {column: float(row.get(column) or 0.0) for column in self.FEATURE_COLUMNS if column in row.index},
            },
            timestamp=row.get("timestamp"),
        )

    def classify_candles(self, candles: list[Candle | dict[str, Any]]) -> RegimeSnapshot:
        if not candles:
            return RegimeSnapshot(symbol="", timeframe="1m", regime="unknown", metadata={"version": self.VERSION, "method": "empty"})
        frame = candles_to_frame(candles)
        latest = candles[-1]
        symbol = latest.symbol if isinstance(latest, Candle) else str(dict(latest or {}).get("symbol") or "")
        timeframe = latest.timeframe if isinstance(latest, Candle) else str(dict(latest or {}).get("timeframe") or "1m")
        return self.classify_frame(frame, symbol=symbol, timeframe=timeframe)

    def to_dict(self, snapshot: RegimeSnapshot) -> dict[str, Any]:
        return asdict(snapshot)

    def _prepare_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        working = pd.DataFrame(frame).copy()
        if working.empty:
            return working
        if not {"open", "high", "low", "close"}.issubset(working.columns):
            return pd.DataFrame()
        enriched = build_features(working, dropna=False)
        for column in self.FEATURE_COLUMNS:
            if column not in enriched.columns:
                enriched[column] = 0.0
        enriched[self.FEATURE_COLUMNS] = enriched[self.FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        return enriched

    def _predict_cluster(self, row: pd.Series) -> int | None:
        if self.model is None:
            return None
        try:
            values = pd.DataFrame([[float(row.get(column) or 0.0) for column in self.FEATURE_COLUMNS]], columns=self.FEATURE_COLUMNS)
            return int(self.model.predict(values)[0])
        except Exception:
            return None

    def _cluster_profile(self, bucket: pd.DataFrame) -> dict[str, float | str]:
        last = bucket.iloc[-1]
        volatility = float(bucket["volatility"].mean() or 0.0)
        regime = self._heuristic_regime(last)
        volatility_regime = self._volatility_regime(volatility)
        return {
            "regime": regime,
            "volatility_regime": volatility_regime,
            "preferred_strategy": self._preferred_strategy(regime, volatility_regime, last),
            "avg_return_1": float(bucket["return_1"].mean() or 0.0),
            "avg_ema_gap": float(bucket["ema_gap"].mean() or 0.0),
            "avg_rsi": float(bucket["rsi"].mean() or 50.0),
            "avg_volatility": volatility,
        }

    def _heuristic_regime(self, row: pd.Series) -> str:
        ema_gap = float(row.get("ema_gap") or 0.0)
        momentum = float(row.get("momentum_3") or row.get("momentum_10") or 0.0)
        rsi = float(row.get("rsi") or 50.0)
        volatility = float(row.get("volatility") or 0.0)
        if volatility >= 0.035 and abs(ema_gap) <= 0.002:
            return "neutral"
        if ema_gap >= 0.0015 and momentum >= 0.0 and rsi >= 52.0:
            return "bullish"
        if ema_gap <= -0.0015 and momentum <= 0.0 and rsi <= 48.0:
            return "bearish"
        return "neutral"

    def _volatility_regime(self, volatility: float) -> str:
        if volatility >= 0.04:
            return "high"
        if volatility >= 0.018:
            return "medium"
        return "low"

    def _preferred_strategy(self, regime: str, volatility_regime: str, row: pd.Series) -> str:
        breakout = max(float(row.get("breakout_up") or 0.0), float(row.get("breakout_down") or 0.0))
        if regime == "bullish" and breakout > 0.0025:
            return "breakout"
        if regime == "bullish":
            return "trend_following"
        if regime == "bearish" and volatility_regime == "high":
            return "ml_agent"
        if regime == "bearish":
            return "mean_reversion"
        if volatility_regime == "high":
            return "ml_agent"
        return "mean_reversion"
