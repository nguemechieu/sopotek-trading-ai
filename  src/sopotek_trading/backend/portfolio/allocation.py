def correlation_adjusted_weights(weights, corr_matrix):
    penalty = corr_matrix.mean()
    adjusted = weights / (1 + penalty)
    return adjusted / adjusted.sum()


class CapitalAllocator:

    def __init__(self, total_capital):
        self.total_capital = total_capital

    def equal_weight(self, strategies):
        allocation = self.total_capital / len(strategies)
        return {s: allocation for s in strategies}

    def volatility_weighted(self, vol_dict):
        inv_vol = {k: 1/v for k, v in vol_dict.items()}
        total = sum(inv_vol.values())
        return {k: self.total_capital * (v/total) for k, v in inv_vol.items()}

