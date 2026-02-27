class VolatilityGuard:

    def __init__(self, max_vol):
        self.max_vol = max_vol

    def check(self, forecast_vol):
        return forecast_vol <= self.max_vol