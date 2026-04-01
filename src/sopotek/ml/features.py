from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from sopotek.core.models import Candle


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
    frame = candles_to_frame(candles)
    if frame.empty:
        return {}

    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)

    returns = close.pct_change().fillna(0.0)
    ema_fast = close.ewm(span=fast_window, adjust=False).mean()
    ema_slow = close.ewm(span=slow_window, adjust=False).mean()

    delta = close.diff().fillna(0.0)
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)
    avg_gain = gains.rolling(rsi_window, min_periods=max(2, rsi_window // 2)).mean()
    avg_loss = losses.rolling(rsi_window, min_periods=max(2, rsi_window // 2)).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(~((avg_loss <= 1e-12) & (avg_gain > 0.0)), 100.0)
    rsi = rsi.where(~((avg_gain <= 1e-12) & (avg_loss > 0.0)), 0.0)
    rsi = rsi.fillna(50.0)

    rolling_mean = close.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).mean()
    rolling_std = close.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).std(ddof=0).replace(0.0, pd.NA)
    zscore = ((close - rolling_mean) / rolling_std).fillna(0.0)

    realized_vol = returns.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).std(ddof=0).fillna(0.0)
    rolling_high = high.rolling(breakout_window, min_periods=max(3, breakout_window // 2)).max().shift(1)
    rolling_low = low.rolling(breakout_window, min_periods=max(3, breakout_window // 2)).min().shift(1)
    range_pct = ((high - low) / close.replace(0.0, pd.NA)).fillna(0.0)
    volume_ratio = (volume / volume.rolling(volatility_window, min_periods=max(3, volatility_window // 2)).mean().replace(0.0, pd.NA)).fillna(1.0)

    last_close = _safe_float(close.iloc[-1], 0.0)
    last_ema_fast = _safe_float(ema_fast.iloc[-1], last_close)
    last_ema_slow = _safe_float(ema_slow.iloc[-1], last_close)
    breakout_high_ref = _safe_float(rolling_high.iloc[-1], last_close)
    breakout_low_ref = _safe_float(rolling_low.iloc[-1], last_close)

    return {
        "close": last_close,
        "return_1": _safe_float(returns.iloc[-1], 0.0),
        "return_5": _safe_float(close.pct_change(5).iloc[-1], 0.0),
        "ema_fast": last_ema_fast,
        "ema_slow": last_ema_slow,
        "ema_gap": _safe_float((last_ema_fast - last_ema_slow) / max(abs(last_ema_slow), 1e-9), 0.0),
        "rsi": _safe_float(rsi.iloc[-1], 50.0),
        "volatility": _safe_float(realized_vol.iloc[-1], 0.0),
        "zscore": _safe_float(zscore.iloc[-1], 0.0),
        "range_pct": _safe_float(range_pct.iloc[-1], 0.0),
        "volume_ratio": _safe_float(volume_ratio.iloc[-1], 1.0),
        "breakout_up": _safe_float((last_close - breakout_high_ref) / max(abs(breakout_high_ref), 1e-9), 0.0),
        "breakout_down": _safe_float((breakout_low_ref - last_close) / max(abs(breakout_low_ref), 1e-9), 0.0),
        "momentum_3": _safe_float(close.diff(3).iloc[-1], 0.0),
        "momentum_10": _safe_float(close.diff(10).iloc[-1], 0.0),
    }
