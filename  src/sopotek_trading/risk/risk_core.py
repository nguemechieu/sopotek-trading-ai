from sopotek_trading.risk.components.correlation_control import CorrelationControl
from sopotek_trading.risk.components.daily_loss_control import DailyLossControl
from sopotek_trading.risk.components.draw_down_control import  DrawdownControl
from sopotek_trading.risk.components.exposure_control import ExposureControl
from sopotek_trading.risk.components.volatility_control import VolatilityControl


class RiskCore:

    def __init__(
            self,
            drawdown=0.2,
            daily=0.05,
            exposure=0.3,
            correlation=0.8,
            volatility=0.05
    ):
        self.drawdown = DrawdownControl(drawdown)
        self.daily = DailyLossControl(daily)
        self.exposure = ExposureControl(exposure)
        self.correlation = CorrelationControl(correlation)
        self.volatility = VolatilityControl(volatility)

    def validate(self, state):

        checks = [
            self.drawdown.check(state["equity"]),
            self.daily.check(state["daily_pnl"], state["equity"]),
            self.exposure.check(state["positions"], state["equity"]),
            self.correlation.check(state["max_correlation"]),
            self.volatility.check(state["forecast_vol"])
        ]

        return all(checks)