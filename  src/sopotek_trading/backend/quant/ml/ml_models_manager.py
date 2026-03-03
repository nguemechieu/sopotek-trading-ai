import asyncio
import logging
import os

from sopotek_trading.backend.quant.ml.ml_signal import MLSignal

logger = logging.getLogger(__name__)


class MLModelManager:

    def __init__(self, model_dir="models"):

        self.logger = logger

        # FIXED: must be dict
        self.models = {}
        self.training_status = {}
        self.locks = {}

        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)

    # --------------------------------------------------
    # REGISTER SYMBOL
    # --------------------------------------------------

    def register_symbol(self, symbol):

        if symbol in self.models:
            return

        self.models[symbol] = None
        self.training_status[symbol] = False
        self.locks[symbol] = asyncio.Lock()

        self._load_model(symbol)

    # --------------------------------------------------
    # MODEL PATH
    # --------------------------------------------------

    def _model_path(self, symbol):

        safe_symbol = symbol.replace("/", "_")
        return os.path.join(
            self.model_dir,
            f"{safe_symbol}.keras"
        )

    # --------------------------------------------------
    # LOAD MODEL
    # --------------------------------------------------

    def _load_model(self, symbol):

        path = self._model_path(symbol)

        if not os.path.exists(path):
            self.logger.info(f"No saved model for {symbol}")
            return

        try:
            model = MLSignal()
            model.load(path)

            self.models[symbol] = model
            self.training_status[symbol] = True

            self.logger.info(f"Model loaded for {symbol}")

        except Exception as e:
            self.logger.error(
                f"Failed loading model {symbol}: {e}"
            )

    # --------------------------------------------------
    # SAVE MODEL
    # --------------------------------------------------

    def _save_model(self, symbol):

        path = self._model_path(symbol)

        try:
            self.models[symbol].save(path)
            self.logger.info(f"Model saved for {symbol}")
        except Exception as e:
            self.logger.error(
                f"Failed saving model {symbol}: {e}"
            )

    # --------------------------------------------------
    # TRAIN
    # --------------------------------------------------

    async def train(self, symbol, data):

        async with self.locks[symbol]:

            model = self.models.get(symbol)

            if model is None:
                model = MLSignal()

            model.train(data)

            self.models[symbol] = model
            self.training_status[symbol] = True

            self._save_model(symbol)

    # --------------------------------------------------
    # STATUS
    # --------------------------------------------------

    def is_trained(self, symbol):
        return self.training_status.get(symbol, False)

    # --------------------------------------------------
    # GET MODEL
    # --------------------------------------------------

    def get_model(self, symbol):
        return self.models.get(symbol)

    # --------------------------------------------------
    # PREDICT
    # --------------------------------------------------

    async def predict(self, symbol, df):

        model = self.models.get(symbol)

        if model is None:
            self.logger.warning(
                f"Prediction requested but model not trained for {symbol}"
            )
            return None

        return model.predict(df)