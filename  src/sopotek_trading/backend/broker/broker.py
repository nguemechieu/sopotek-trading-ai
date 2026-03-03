import pandas as pd


class Broker:

    def __init__(self, adapter, logger=None):
        """
        adapter: instance of BaseBroker
        """
        self.adapter = adapter
        self.logger = logger

    # -------------------------------
    # Connection
    # -------------------------------

    async def connect(self):
        await self.adapter.connect()

    async def close(self):
        await self.adapter.close()

    # -------------------------------
    # Account
    # -------------------------------

    async def fetch_balance(self):
        return await self.adapter.fetch_balance()

    async def fetch_positions(self):
        return await self.adapter.fetch_positions()

    # -------------------------------
    # Market Data
    # -------------------------------

    async def fetch_ticker(self, symbol):
        return await self.adapter.fetch_ticker(symbol)

    async def fetch_ohlcv(self, symbol, timeframe,limit)->pd.DataFrame:
        return await self.adapter.fetch_ohlcv(symbol, timeframe,limit)

    # -------------------------------
    # Execution
    # -------------------------------

    async def create_order(self, symbol, side, order_type, amount, price, stop_loss,
                           take_profit):
        if self.logger:
            self.logger.info(
                f"Executing {side} {amount} {symbol}"
            )

        return await self.adapter.create_order(symbol=symbol, side=side, order_type=order_type, amount=amount,
                                               price=price,stop_loss=stop_loss, take_profit=take_profit)

    async def cancel_order(self, order_id, symbol):
        return await self.adapter.cancel_order(order_id, symbol)

    async def fetch_symbols(self):

        return  await self.adapter.fetch_symbols()