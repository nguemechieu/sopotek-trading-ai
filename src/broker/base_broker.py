from abc import ABC, abstractmethod


class BaseBroker(ABC):

    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def close(self):
        pass

    # ===============================
    # MARKET DATA
    # ===============================

    @abstractmethod
    async def fetch_ticker(self, symbol):
        pass

    @abstractmethod
    async def fetch_orderbook(self, symbol, limit=50):
        pass

    # ===============================
    # TRADING
    # ===============================

    @abstractmethod
    async def create_order(
            self,
            symbol,
            side,
            amount,
            type="market",
            price=None
    ):
        pass

    @abstractmethod
    async def cancel_order(self, order_id, symbol):
        pass

    # ===============================
    # ACCOUNT
    # ===============================

    @abstractmethod
    async def fetch_balance(self):
        pass


    @abstractmethod
    async def fetch_balance(self):
        pass
    @abstractmethod
    async def fetch_order(self, order_id):
        pass
    @abstractmethod
    async  def fetch_symbol(self):
        pass



