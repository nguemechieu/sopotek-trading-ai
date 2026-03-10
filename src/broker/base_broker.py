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

    async def fetch_tickers(self, symbols=None):
        raise NotImplementedError("fetch_tickers is not implemented for this broker")

    async def fetch_orderbook(self, symbol, limit=50):
        raise NotImplementedError("fetch_orderbook is not implemented for this broker")

    async def fetch_order_book(self, symbol, limit=50):
        return await self.fetch_orderbook(symbol, limit=limit)

    async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        raise NotImplementedError("fetch_ohlcv is not implemented for this broker")

    async def fetch_trades(self, symbol, limit=None):
        raise NotImplementedError("fetch_trades is not implemented for this broker")

    async def fetch_my_trades(self, symbol=None, limit=None):
        raise NotImplementedError("fetch_my_trades is not implemented for this broker")

    async def fetch_markets(self):
        raise NotImplementedError("fetch_markets is not implemented for this broker")

    async def fetch_currencies(self):
        raise NotImplementedError("fetch_currencies is not implemented for this broker")

    async def fetch_status(self):
        raise NotImplementedError("fetch_status is not implemented for this broker")

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
        price=None,
        params=None,
    ):
        pass

    @abstractmethod
    async def cancel_order(self, order_id, symbol=None):
        pass

    async def cancel_all_orders(self, symbol=None):
        raise NotImplementedError("cancel_all_orders is not implemented for this broker")

    # ===============================
    # ACCOUNT
    # ===============================

    @abstractmethod
    async def fetch_balance(self):
        pass

    async def fetch_positions(self, symbols=None):
        raise NotImplementedError("fetch_positions is not implemented for this broker")

    async def fetch_position(self, symbol):
        positions = await self.fetch_positions(symbols=[symbol])
        if isinstance(positions, list):
            for position in positions:
                if isinstance(position, dict) and position.get("symbol") == symbol:
                    return position
        return None

    async def fetch_order(self, order_id, symbol=None):
        raise NotImplementedError("fetch_order is not implemented for this broker")

    async def fetch_orders(self, symbol=None, limit=None):
        raise NotImplementedError("fetch_orders is not implemented for this broker")

    async def fetch_open_orders(self, symbol=None, limit=None):
        raise NotImplementedError("fetch_open_orders is not implemented for this broker")

    async def fetch_closed_orders(self, symbol=None, limit=None):
        raise NotImplementedError("fetch_closed_orders is not implemented for this broker")

    async def fetch_symbol(self):
        raise NotImplementedError("fetch_symbol is not implemented for this broker")

    async def fetch_symbols(self):
        return await self.fetch_symbol()

    async def withdraw(self, code, amount, address, tag=None, params=None):
        raise NotImplementedError("withdraw is not implemented for this broker")

    async def fetch_deposit_address(self, code, params=None):
        raise NotImplementedError("fetch_deposit_address is not implemented for this broker")
