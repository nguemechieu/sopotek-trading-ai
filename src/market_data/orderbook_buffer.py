class OrderBookBuffer:

    def __init__(self):
        self.books = {}

    # ====================================
    # UPDATE ORDERBOOK
    # ====================================

    def update(self, symbol, bids, asks):
        self.books[symbol] = {
            "bids": bids,
            "asks": asks
        }

    # ====================================
    # GET ORDERBOOK
    # ====================================

    def get(self, symbol):
        return self.books.get(symbol, None)
