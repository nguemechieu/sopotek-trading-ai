import numpy as np

class SimpleRLAllocator:

    def __init__(self, num_assets):
        self.weights = np.ones(num_assets) / num_assets

    def update(self, rewards, learning_rate=0.01):
        gradient = rewards - np.mean(rewards)
        self.weights += learning_rate * gradient
        self.weights = np.clip(self.weights, 0, None)
        self.weights /= np.sum(self.weights)

        return self.weights