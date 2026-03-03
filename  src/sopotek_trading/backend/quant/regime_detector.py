import pandas as pd
from sklearn.cluster import KMeans


class RegimeDetector:

    def __init__(self, n_regimes=3):
        self.model = KMeans(n_clusters=n_regimes, random_state=42)

    def fit(self, df):

        returns = df["close"].pct_change()
        vol = returns.rolling(20).std()
        momentum = df["close"].rolling(20).mean()

        features = pd.DataFrame({
            "returns": returns,
            "volatility": vol,
            "momentum": momentum
        }).dropna()

        self.model.fit(features)

        return self.model

    def predict(self, df):

        returns = df["close"].pct_change()
        vol = returns.rolling(20).std()
        momentum = df["close"].rolling(20).mean()

        features = pd.DataFrame({
            "returns": returns,
            "volatility": vol,
            "momentum": momentum
        }).dropna()

        regimes = self.model.predict(features)

        return regimes[-1]