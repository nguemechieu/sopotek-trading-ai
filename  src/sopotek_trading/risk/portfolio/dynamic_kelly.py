def dynamic_kelly(win_prob, win_loss_ratio, volatility, max_fraction=0.25):
    base_kelly = win_prob - (1 - win_prob) / win_loss_ratio

    # Reduce Kelly when volatility is high
    adjusted = base_kelly / (1 + volatility * 10)

    return min(max(adjusted, 0), max_fraction)
#
#
# Usage:
#
# fraction = dynamic_kelly(
#     win_prob=0.55,
#     win_loss_ratio=2,
#     volatility=predicted_vol
# )
# position_size = account_balance * fraction
  #
# This prevents:
#
# Overbetting in volatile markets
#
# Blowups from naive Kelly sizing
#
# 🔥 What You Now Have
#
# You’ve implemented:
#
# CVaR (tail risk control)
#
# Regime switching logic
#
# GARCH volatility forecasting
#
# Adaptive reinforcement allocation
#
# Volatility-adjusted Kelly sizing
#
# This is institutional-level risk science.