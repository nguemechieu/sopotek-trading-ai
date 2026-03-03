import numpy as np
import pandas as pd

class CorrelationModel:

    def __init__(self, returns_df: pd.DataFrame):
        """
        returns_df columns = assets
        rows = time
        """
        self.returns = returns_df

    def correlation_matrix(self):
        return self.returns.corr()

    def rolling_correlation(self, window=60):
        return self.returns.rolling(window).corr()

    def average_correlation(self):
        corr = self.correlation_matrix()
        return corr.values[np.triu_indices_from(corr, k=1)].mean()
#
#
#     Example Usage
# corr_model = CorrelationModel(returns_df)
# matrix = corr_model.correlation_matrix()
# avg_corr = corr_model.average_correlation()

# if avg_corr > 0.75:
#     reduce_total_exposure()