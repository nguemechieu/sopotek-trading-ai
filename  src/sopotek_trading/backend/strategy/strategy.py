import logging
import pandas as pd

from sopotek_trading.backend.quant.ml.ml_models_manager import MLModelManager


class Strategy:

    def __init__(self, controller):

        self.logger = logging.getLogger(__name__)
        self.controller = controller

        # Use a proper models directory
        self.model_manager = MLModelManager(
            controller=self.controller,
            model_dir="models"
        )

    async def generate_signal(self, symbol: str, df: pd.DataFrame):

        if df is None or df.empty:
            return None

        # Ensure symbol is registered
        self.model_manager.register_symbol(symbol)

        # Ensure model is trained
        if not self.model_manager.is_trained(symbol):
            await self.model_manager.train(symbol, df)
            return None  # Wait for next cycle

        # Predict
        prediction = await self.model_manager.predict(symbol, df)

        if prediction is None:
            return None

        signal = prediction.get("signal", "HOLD")

        if signal == "HOLD":
            return None

        entry_price = float(df["close"].iloc[-1])

        return {
            "symbol": symbol,
            "signal": signal,
            "entry_price": entry_price,
            "stop_price": entry_price * 0.99,
            "confidence": float(prediction.get("confidence", 0.5)),
            "volatility": float(df["close"].pct_change().std())
        }