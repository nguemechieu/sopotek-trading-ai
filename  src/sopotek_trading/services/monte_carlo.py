import numpy as np

class MonteCarloSimulator:

    def __init__(self, returns, simulations=1000, horizon=252):
        self.returns = returns
        self.simulations = simulations
        self.horizon = horizon

    def run(self):
        mean = np.mean(self.returns)
        std = np.std(self.returns)

        simulated_paths = []

        for _ in range(self.simulations):
            path = np.random.normal(mean, std, self.horizon)
            simulated_paths.append(np.cumsum(path))

        return np.array(simulated_paths)


#     Usage:
#
# sim = MonteCarloSimulator(strategy_returns)
# paths = sim.run()