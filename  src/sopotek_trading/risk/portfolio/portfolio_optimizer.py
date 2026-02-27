import numpy as np

def markowitz_weights(returns):
    mean_returns = np.mean(returns, axis=0)
    cov_matrix = np.cov(returns.T)

    inv_cov = np.linalg.inv(cov_matrix)
    weights = inv_cov @ mean_returns
    weights /= np.sum(weights)

    return weights

def kelly_fraction(win_prob, win_loss_ratio):
    return win_prob - (1 - win_prob) / win_loss_ratio
#
# Example:
#
# kelly = kelly_fraction(0.55, 2)
# position_size = balance * kelly