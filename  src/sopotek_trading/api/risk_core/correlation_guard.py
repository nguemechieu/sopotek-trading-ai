import numpy as np

class CorrelationGuard:

    def __init__(self, threshold=0.8):
        self.threshold = threshold

    def check(self, returns_df):
        corr = returns_df.corr().values
        avg_corr = np.mean(corr[np.triu_indices_from(corr, 1)])

        if avg_corr > self.threshold:
            return False

        return True