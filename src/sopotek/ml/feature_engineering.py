from __future__ import annotations

from collections.abc import Sequence
from math import nan

import pandas as pd

from sopotek.core.models import Candle

DEFAULT_FEATURE_COLUMNS = [
    "close",
    "return_1",
    "return_5",
    "ema_fast",
    "ema_slow",
    "ema_gap",
    "rsi",
    "volatility",
    "zscore",
    "range_pct",
    "volume_ratio",
    "breakout_up",
    "breakout_down",
    "momentum_3",
    "momentum_10",
]


def candles_to_frame(candles: Sequence[Candle | dict]) -> pd.DataFrame:
    records: list[dict[str, float | str | object]] = []
    for candle in candles:
        if isinstance(candle, Candle):
            records.append(
                {
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "open": float(candle.open),
                    "high": float(candle.high),
                    "low": float(candle.low),
                    "close": float(candle.close),
                    "volume": float(candle.volume),
                    "timestamp": candle.end,
                }
            )
            continue
        payload = dict(candle or {})
        records.append(
            {
                "symbol": str(payload.get("symbol") or ""),
                "timeframe": str(payload.get("timeframe") or "1m"),
                "open": float(payload.get("open") or 0.0),
                "high": float(payload.get("high") or 0.0),
                "low": float(payload.get("low") or 0.0),
                "close": float(payload.get("close") or 0.0),
                "volume": float(payload.get("volume") or 0.0),
                "timestamp": payload.get("end") or payload.get("timestamp"),
            }
        )
    return pd.DataFrame.from_records(records)


def compute_rsi(series, period: int = 14) -> pd.Series:
    values = pd.Series(series, copy=False).astype(float)
    delta = values.diff().fillna(0.0)
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)
    avg_gain = gains.rolling(period, min_periods=max(2, period // 2)).mean()
    avg_loss = losses.rolling(period, min_periods=max(2, period // 2)).mean()
    rs = avg_gain / avg_loss.replace(0.0, nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(~((avg_loss <= 1e-12) & (avg_gain > 0.0)), 100.0)
    rsi = rsi.where(~((avg_gain <= 1e-12) & (avg_loss > 0.0)), 0.0)
    return rsi.fillna(50.0)


def compute_ema(series, span: int = 14) -> pd.Series:
    return pd.Series(series, copy=False).astype(float).ewm(span=span, adjust=False).mean()


def compute_volatility(series, window: int = 20) -> pd.Series:
    values = pd.Series(series, copy=False).astype(float)
    return values.pct_change().rolling(window, min_periods=max(3, window // 2)).std(ddof=0)


def build_features(
    df: pd.DataFrame,
    *,
    fast_window: int = 12,
    slow_window: int = 26,
    rsi_window: int = 14,
    volatility_window: int = 20,
    breakout_window: int = 20,
    dropna: bool = False,
) -> pd.DataFrame:
    working = pd.DataFrame(df).copy()
    if working.empty:
        return working

    if "timestamp" in working.columns:
        working = working.sort_values("timestamp").reset_index(drop=True)

    for column in ("open", "high", "low", "close"):
        if column not in working.columns:
            raise KeyError(f"build_features requires a '{column}' column")
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if "volume" not in working.columns:
        working["volume"] = 0.0
    working["volume"] = pd.to_numeric(working["volume"], errors="coerce").fillna(0.0)

    close = working["close"].astype(float)
    high = working["high"].astype(float)
    low = working["low"].astype(float)
    volume = working["volume"].astype(float)

    working["return_1"] = close.pct_change()
    working["return_5"] = close.pct_change(5)
    working["ema_fast"] = compute_ema(close, fast_window)
    working["ema_slow"] = compute_ema(close, slow_window)
    working["ema_gap"] = (
        (working["ema_fast"] - working["ema_slow"]) / working["ema_slow"].replace(0.0, nan)
    ).fillna(0.0)
    working["rsi"] = compute_rsi(close, rsi_window)
    working["volatility"] = compute_volatility(close, volatility_window).fillna(0.0)

    rolling_mean = close.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).mean()
    rolling_std = close.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).std(ddof=0)
    working["zscore"] = ((close - rolling_mean) / rolling_std.replace(0.0, nan)).fillna(0.0)
    working["range_pct"] = ((high - low) / close.replace(0.0, nan)).fillna(0.0)

    rolling_volume = volume.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).mean()
    working["volume_ratio"] = (volume / rolling_volume.replace(0.0, nan)).fillna(1.0)

    rolling_high = high.rolling(breakout_window, min_periods=max(3, breakout_window // 2)).max().shift(1)
    rolling_low = low.rolling(breakout_window, min_periods=max(3, breakout_window // 2)).min().shift(1)
    working["breakout_up"] = ((close - rolling_high) / rolling_high.replace(0.0, nan)).fillna(0.0)
    working["breakout_down"] = ((rolling_low - close) / close.replace(0.0, nan)).fillna(0.0)
    working["momentum_3"] = close.diff(3).fillna(0.0)
    working["momentum_10"] = close.diff(10).fillna(0.0)

    if dropna:
        required = ["close", "ema_fast", "ema_slow", "rsi", "volatility"]
        working = working.dropna(subset=required).reset_index(drop=True)
    return working


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if pd.isna(numeric):
        return default
    return numeric


def compute_indicator_features(
    candles: Sequence[Candle | dict],
    *,
    fast_window: int = 8,
    slow_window: int = 21,
    rsi_window: int = 14,
    volatility_window: int = 20,
    breakout_window: int = 20,
) -> dict[str, float]:
    frame = build_features(
        candles_to_frame(candles),
        fast_window=fast_window,
        slow_window=slow_window,
        rsi_window=rsi_window,
        volatility_window=volatility_window,
        breakout_window=breakout_window,
        dropna=False,
    )
    if frame.empty:
        return {}

    row = frame.iloc[-1]
    return {column: _safe_float(row.get(column), 0.0 if column != "rsi" else 50.0) for column in DEFAULT_FEATURE_COLUMNS}
