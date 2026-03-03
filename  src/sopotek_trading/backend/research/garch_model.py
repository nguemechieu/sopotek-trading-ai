from arch import arch_model
import numpy as np

def forecast_volatility(returns):
    model = arch_model(returns * 100, vol="GARCH", p=1, q=1)
    fitted = model.fit(disp="off")
    forecast = fitted.forecast(horizon=1)
    return np.sqrt(forecast.variance.values[-1][0]) / 100