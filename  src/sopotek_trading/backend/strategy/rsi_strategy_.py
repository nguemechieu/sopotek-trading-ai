import numpy as np
import pandas as pd


class RSIStrategy:

    def __init__(
            self,
            period=14,
            oversold=30,
            overbought=70,
    ):

        self.period = period
        self.oversold = oversold
        self.overbought = overbought

        self.last_signal = {}

    # -------------------------------------------------
    # SIGNAL GENERATOR
    # -------------------------------------------------

    async def generate_signal(self, symbol: str, df: pd.DataFrame):

        if df is None or len(df) < self.period + 5:
            return None

        df = df.copy()

        # -----------------------------------------
        # RSI Calculation
        # -----------------------------------------

        delta = df["close"].diff()

        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gain).rolling(self.period).mean()
        avg_loss = pd.Series(loss).rolling(self.period).mean()

        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        prev = df.iloc[-2]

        signal_type = None

        # -----------------------------------------
        # Oversold Reversal
        # -----------------------------------------

        if prev["rsi"] < self.oversold and last["rsi"] > self.oversold:
            signal_type = "BUY"

        # -----------------------------------------
        # Overbought Reversal
        # -----------------------------------------

        elif prev["rsi"] > self.overbought and last["rsi"] < self.overbought:
            signal_type = "SELL"

        if not signal_type:
            return None

        # Prevent duplicate signals
        if self.last_signal.get(symbol) == signal_type:
            return None

        self.last_signal[symbol] = signal_type

        # -----------------------------------------
        # Risk Components
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

        # Confidence based on RSI extreme distance
        if signal_type == "BUY":
            confidence = min(
                (self.oversold - prev["rsi"]) / self.oversold,
                1.0
            )
        else:
            confidence = min(
                (prev["rsi"] - self.overbought) / 30,
                1.0
            )

        confidence = max(confidence, 0.1)

        return {
            "symbol": symbol,
            "signal": signal_type,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "confidence": confidence,
            "volatility": volatility,
        }