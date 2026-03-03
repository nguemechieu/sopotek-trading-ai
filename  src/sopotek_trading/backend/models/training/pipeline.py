import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange


def build_features_and_labels(df: pd.DataFrame):

    df = df.copy()

    df["ema50"] = EMAIndicator(df["close"], 50).ema_indicator()
    df["ema200"] = EMAIndicator(df["close"], 200).ema_indicator()
    df["rsi"] = RSIIndicator(df["close"], 14).rsi()

    atr = AverageTrueRange(df["high"], df["low"], df["close"], 14)
    df["atr"] = atr.average_true_range()

    df["returns"] = df["close"].pct_change()
    df["future_return"] = df["close"].shift(-5) / df["close"] - 1

    # Label:
    # 1 = upward move
    # -1 = downward move
    # 0 = neutral
    df["label"] = 0
    df.loc[df["future_return"] > 0.01, "label"] = 1
    df.loc[df["future_return"] < -0.01, "label"] = -1

    df.dropna(inplace=True)

    features = df[["close", "ema50", "ema200", "rsi", "atr", "returns"]]
    labels = df["label"]

    return features, labels