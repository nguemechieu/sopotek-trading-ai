import pandas as pd


class CandleBuffer:

    def __init__(self, max_length=1000):

        self.max_length = max_length
        self.buffers = {}

    # ====================================
    # UPDATE BUFFER
    # ====================================

    def update(self, symbol, candle):

        if symbol not in self.buffers:
            self.buffers[symbol] = []

        self.buffers[symbol].append(candle)

        if len(self.buffers[symbol]) > self.max_length:
            self.buffers[symbol].pop(0)

    # ====================================
    # GET DATAFRAME
    # ====================================

    def get(self, symbol):

        data = self.buffers.get(symbol, [])

        if not data:
            return None

        df = pd.DataFrame(data)

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        return df