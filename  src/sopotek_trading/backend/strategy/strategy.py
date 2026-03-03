import joblib

from sopotek_trading.backend.quant.ml.ml_models_manager import MLModelManager, logger


class Strategy:

    def __init__(self):
        # Load trained model once

        self.name_file = "../sopotek_trading/backend/models/price_model.pkl"
        try :

            self.model = joblib.load(self.name_file)
            logger.info("ML model loaded successfully")
        except Exception as e:
            logger.warning("ML model not loaded: %s", e)
            self.model = None
            self.model_manager = MLModelManager()


    async def generate_signal(self, symbol, df):
     self.model_manager.register_symbol(symbol)

    # First ensure model is trained
     if not self.model_manager.is_trained(symbol):
        return None

     prediction = await self.model_manager.predict(symbol, df)

     if prediction["signal"] == "HOLD":
        return "HOLD"

     return {
        "signal": prediction["signal"],
        "entry_price": df["close"].iloc[-1],
        "stop_price": df["close"].iloc[-1] * 0.99,
        "confidence": prediction.get("confidence",df),
        "volatility": df["close"].pct_change().std()
    }

    def reload_model(self):
        self.model = joblib.load(self.name_file)