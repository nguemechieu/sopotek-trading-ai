import pandas as pd


class DataHandler:

    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.pointer = 0

    def has_next(self):
        return self.pointer < len(self.data)

    def next_bar(self):
        row = self.data.iloc[self.pointer]
        self.pointer += 1
        return row

    def current_window(self, lookback=100):
        start = max(0, self.pointer - lookback)
        return self.data.iloc[start:self.pointer]