class RiskCore:

    def __init__(self, drawdown, daily, exposure, correlation, volatility):
        self.drawdown = drawdown
        self.daily = daily
        self.exposure = exposure
        self.correlation = correlation
        self.volatility = volatility

    def validate(self, state):
        checks = [
            self.drawdown.check(state["equity"]),
            self.daily.update(state["pnl"]),
            self.exposure.check(state["positions"]),
            self.correlation.check(state["returns_df"]),
            self.volatility.check(state["forecast_vol"])
        ]

        return all(checks)

#
#     Now before any trade:
#
# if not risk_core.validate(current_state):
#     halt_trading()
#
# That is institutional discipline.