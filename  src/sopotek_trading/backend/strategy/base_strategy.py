class BaseStrategy:

    def __init__(self, name="BaseStrategy"):
        self.name = name

    def generate_signal(self, df):
        """
        Must return:
        {
            "signal": "BUY" / "SELL" / "HOLD",
            "confidence": float
        }
        """
        raise NotImplementedError