# strategy/strategy.py

import pandas as pd
import numpy as np

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange


class Strategy:

    def __init__(self, model=None):

        self.model = model

        # Strategy parameters
        self.rsi_period = 14
        self.ema_fast = 20
        self.ema_slow = 50
        self.atr_period = 14

        self.min_confidence = 0.55

    # ==========================================================
    # FEATURE ENGINEERING
    # ==========================================================

    def compute_features(self, candles):
        if not candles:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

        normalized = []
        for row in candles:
            if isinstance(row, (list, tuple)) and len(row) >= 6:
                normalized.append(list(row[:6]))

        if not normalized:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

        df = pd.DataFrame(
            normalized,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=numeric_cols, inplace=True)

        if len(df) < max(self.ema_slow, self.atr_period, self.rsi_period):
            return pd.DataFrame(columns=df.columns)

        # Indicators
        df["rsi"] = RSIIndicator(df["close"], self.rsi_period).rsi()

        df["ema_fast"] = EMAIndicator(
            df["close"], self.ema_fast
        ).ema_indicator()

        df["ema_slow"] = EMAIndicator(
            df["close"], self.ema_slow
        ).ema_indicator()

        df["atr"] = AverageTrueRange(
            df["high"],
            df["low"],
            df["close"],
            self.atr_period
        ).average_true_range()

        df.dropna(inplace=True)

        return df

    # ==========================================================
    # SIGNAL GENERATION
    # ==========================================================

    def generate_signal(self, candles):

        df = self.compute_features(candles)

        if df.empty:
            return None

        row = df.iloc[-1]

        # Trend
        trend_up = row["ema_fast"] > row["ema_slow"]
        trend_down = row["ema_fast"] < row["ema_slow"]

        # RSI
        rsi = row["rsi"]

        # =========================
        # BUY SIGNAL
        # =========================

        if trend_up and rsi < 35:

            return {
                "side": "buy",
                "amount": 1,
                "confidence": 0.60,
                "reason": "EMA trend up + RSI oversold"
            }

        # =========================
        # SELL SIGNAL
        # =========================

        if trend_down and rsi > 65:

            return {
                "side": "sell",
                "amount": 1,
                "confidence": 0.60,
                "reason": "EMA trend down + RSI overbought"
            }

        return None

    # ==========================================================
    # AI SIGNAL
    # ==========================================================

    def generate_ai_signal(self, candles):

        if self.model is None:
            return None

        df = self.compute_features(candles)

        if df.empty:
            return None

        features = df.iloc[-1][[
            "rsi",
            "ema_fast",
            "ema_slow",
            "atr",
            "volume"
        ]].values.reshape(1, -1)

        prob = self.model.predict_proba(features)[0]

        confidence = max(prob)

        if confidence < self.min_confidence:
            return None

        side = "buy" if prob[1] > prob[0] else "sell"

        return {
            "side": side,
            "amount": 1,
            "confidence": float(confidence),
            "reason": "AI model prediction"
        }
