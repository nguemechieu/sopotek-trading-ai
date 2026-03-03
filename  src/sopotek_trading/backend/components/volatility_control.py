class VolatilityControl:

    def __init__(self, volatility_limit):
        self.volatility_limit = volatility_limit

    def check(self, forecast_vol):
        return forecast_vol <= self.volatility_limit