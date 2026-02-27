import numpy as np

def historical_var(returns, confidence=0.95):
    sorted_returns = np.sort(returns)
    index = int((1 - confidence) * len(sorted_returns))
    return abs(sorted_returns[index])


# Example:
#
# var_95 = historical_var(daily_returns, 0.95)
#
# Interpretation:
#
# “We expect to lose no more than $X on 95% of days.”