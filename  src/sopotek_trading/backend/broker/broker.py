import asyncio
import pandas as pd


class Broker:

    def __init__(self, adapter, logger=None, max_retries=3,controller=None):


        self.adapter = adapter
        self.logger = logger
        self.max_retries = max_retries
        self.orderbook_signal = controller.orderbook_signal




    # ======================================
    # Internal Retry Wrapper
    # ======================================

    async def _safe_call(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)

            except Exception as e:

                if self.logger:
                    self.logger.warning(
                        f"Broker error (attempt {attempt+1}): {e}"
                    )

                if attempt == self.max_retries - 1:
                    raise

                await asyncio.sleep(1)
        return None

    # ======================================
    # Connection
    # ======================================

    async def connect(self):
        await self._safe_call(self.adapter.connect)

    async def close(self):
        await self._safe_call(self.adapter.close)

    # ======================================
    # Account
    # ======================================

    async def fetch_balance(self):
        return await self._safe_call(self.adapter.fetch_balance)

    async def fetch_positions(self):
        return await self._safe_call(self.adapter.fetch_positions)

    # ======================================
    # Market Data
    # ======================================

    async def fetch_ticker(self, symbol):
        return await self._safe_call(
            self.adapter.fetch_ticker,
            symbol
        )

    async def fetch_ohlcv(self, symbol, timeframe, limit) -> pd.DataFrame:
        df = await self._safe_call(
            self.adapter.fetch_ohlcv,
            symbol,
            timeframe,
            limit
        )

        if df is None or df.empty:
            raise ValueError(f"No OHLCV data for {symbol}")

        return df

    async def fetch_symbols(self):
        return await self._safe_call(self.adapter.fetch_symbols)

    # ======================================
    # Execution
    # ======================================

    async def create_order(
            self,
            symbol,
            side,
            order_type,
            amount,
            price=None,
            stop_loss=None,
            take_profit=None
    ):

        if amount <= 0:
            raise ValueError("Order amount must be > 0")

        if self.logger:
            self.logger.info(
                f"Executing {side.upper()} {amount} {symbol}"
            )

        return await self._safe_call(
            self.adapter.create_order,
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    async def cancel_order(self, order_id, symbol):
        return await self._safe_call(
            self.adapter.cancel_order,
            order_id,
            symbol
        )
    async def cancel_all_orders(self, symbol):
        return await self._safe_call(symbol
                                     )
    async def start_orderbook_stream(self, symbol):

     async def emit_to_ui(sym, bids, asks):
        self.orderbook_signal.emit(sym, bids, asks)

     await self.adapter.stream_orderbook(symbol, emit_to_ui)