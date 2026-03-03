import numpy as np
import pandas as pd


class MACDStrategy:

    def __init__(
            self,
            fast=12,
            slow=26,
            signal=9,
            risk_reward_ratio=2.0,
    ):

        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.rr_ratio = risk_reward_ratio

        self.last_signal = {}

    # -------------------------------------------------
    # PUBLIC SIGNAL GENERATOR
    # -------------------------------------------------

    async def generate_signal(self, symbol: str, df: pd.DataFrame):

        if df is None or len(df) < self.slow + 5:
            return None

        df = df.copy()

        df["ema_fast"] = df["close"].ewm(
            span=self.fast, adjust=False
        ).mean()

        df["ema_slow"] = df["close"].ewm(
            span=self.slow, adjust=False
        ).mean()

        df["macd"] = df["ema_fast"] - df["ema_slow"]

        df["macd_signal"] = df["macd"].ewm(
            span=self.signal, adjust=False
        ).mean()

        df["histogram"] = df["macd"] - df["macd_signal"]

        # -----------------------------------------
        # Detect crossover
        # -----------------------------------------

        last = df.iloc[-1]
        prev = df.iloc[-2]

        signal_type = None

        # Bullish crossover
        if (
                prev["macd"] < prev["macd_signal"]
                and last["macd"] > last["macd_signal"]
        ):
            signal_type = "BUY"

        # Bearish crossover
        elif (
                prev["macd"] > prev["macd_signal"]
                and last["macd"] < last["macd_signal"]
        ):
            signal_type = "SELL"

        if not signal_type:
            return None

        # Prevent duplicate signal
        if self.last_signal.get(symbol) == signal_type:
            return None

        self.last_signal[symbol] = signal_type

        # -----------------------------------------
        # Risk Management Components
        # -----------------------------------------

        entry_price = float(last["close"])

        volatility = (
            df["close"]
            .pct_change()
            .rolling(20)
            .std()
            .iloc[-1]
        )

        volatility = float(volatility) if not np.isnan(volatility) else 0.01

        stop_distance = entry_price * volatility * 2

        if signal_type == "BUY":
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        # Confidence based on histogram strength
        confidence = min(
            abs(last["histogram"]) * 10,
            1.0
        )

        return {
            "symbol": symbol,
            "signal": signal_type,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "confidence": confidence,
            "volatility": volatility,
        }