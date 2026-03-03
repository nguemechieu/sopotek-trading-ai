import csv
import os


class FeatureLogger:

    def __init__(self, filepath="training_data.csv"):
        self.filepath = filepath

        if not os.path.exists(filepath):
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "price",
                    "rsi",
                    "ema50",
                    "ema200",
                    "atr",
                    "signal",
                    "future_return"
                ])

    def log(self, features):

        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(features)