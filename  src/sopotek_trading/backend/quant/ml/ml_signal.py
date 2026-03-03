import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras import Input
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras.models import Sequential
from tensorflow.python.keras.models import load_model


def _add_features(df):

    df = df.copy()

    # Log returns
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))

    # Rolling volatility (20-period)
    df["volatility"] = df["log_return"].rolling(20).std()

    df = df.dropna()

    return df


class MLSignal:

    def __init__(self):
        self.model = None
        self.scaler = MinMaxScaler()
        self.is_trained = False
        self.lookback = 50






    def _prepare_data(self, df):

        df = _add_features(df)

        if len(df) <= self.lookback:
            raise ValueError("Not enough data for LSTM training.")

        features = df[["close", "volatility"]].values

        scaled = self.scaler.fit_transform(features)

        x, y = [], []

        for i in range(self.lookback, len(scaled)):
            x.append(scaled[i - self.lookback:i])
            y.append(scaled[i][0])  # predict close price only

        return np.array(x), np.array(y)

    def train(self, df):

        x, y = self._prepare_data(df)

        self.model = Sequential([
            Input(shape=(self.lookback, 2)),  # 2 features now
            LSTM(64),
            Dense(1)
        ])

        self.model.compile(optimizer="adam", loss="mse")

        early_stop = EarlyStopping(
            monitor="val_loss",
            patience=3,
            restore_best_weights=True
        )

        self.model.fit(
            x,
            y,
            epochs=30,
            batch_size=32,
            validation_split=0.2,
            callbacks=[early_stop],
            verbose=0
        )

        self.is_trained = True

    def predict(self, df):

        if not self.is_trained:
            raise Exception("Model must be trained before prediction.")

        df = _add_features(df)

        if len(df) <= self.lookback:
            return {"signal": "HOLD", "confidence": 0.0, "volatility": 0.0}

        features = df[["close", "volatility"]].values
        scaled = self.scaler.transform(features)

        x = scaled[-self.lookback:]
        x = np.reshape(x, (1, self.lookback, 2))

        prediction = self.model.predict(x, verbose=0)

        # Only inverse-transform close column
        dummy = np.zeros((1, 2))
        dummy[0][0] = prediction[0][0]
        predicted_close = self.scaler.inverse_transform(dummy)[0][0]

        current_price = df["close"].iloc[-1]
        current_volatility = df["volatility"].iloc[-1]

        delta = abs(predicted_close - current_price) / current_price
        confidence = min(delta * 50, 1.0)

        if predicted_close > current_price * 1.002:
            signal = "BUY"
        elif predicted_close < current_price * 0.998:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "signal": signal,
            "confidence": float(confidence),
            "volatility": float(current_volatility),
            "predicted_price": float(predicted_close),
            "current_price": float(current_price)
        }

    def save(self, path):
        self.model.save(path)

    def load(self, path):
     self.model = load_model(path)