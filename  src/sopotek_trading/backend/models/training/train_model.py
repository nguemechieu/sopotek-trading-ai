import pandas as pd

from sopotek_trading.backend.quant.ml.ml_signal import MLSignal


async def train_model(self, symbol):

    ohlcv = await self.broker.fetch_ohlcv(symbol, self.time_frame)
    if not ohlcv:
        return

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    model = MLSignal()
    model.train(df)

    self.models[symbol] = model

    self.logger.info("Model trained for %s", symbol)