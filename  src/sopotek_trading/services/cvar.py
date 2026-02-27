import numpy as np

def expected_shortfall(returns, confidence=0.95):
    sorted_returns = np.sort(returns)
    cutoff_index = int((1 - confidence) * len(sorted_returns))
    tail_losses = sorted_returns[:cutoff_index]
    return abs(np.mean(tail_losses))