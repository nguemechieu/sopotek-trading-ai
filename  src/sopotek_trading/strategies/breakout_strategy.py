from basestrategy.base_strategy import BaseStrategy


class RSIStrategy(BaseStrategy):

    def generate_signal(self, market_data):
        if market_data["rsi"] < 30:
            return "BUY"
        elif market_data["rsi"] > 70:
            return "SELL"
        return "HOLD"