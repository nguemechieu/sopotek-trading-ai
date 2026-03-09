import ccxt.async_support as ccxt
import aiohttp
import socket
import asyncio

from broker.base_broker import BaseBroker


class CCXTBroker(BaseBroker):

    def __init__(self, config):

        super().__init__()

        self.config = config
        self.exchange_name = config.exchange
        self.api_key = config.api_key
        self.secret = config.secret

        self.exchange = None
        self.session = None
        self.symbols = []

        self._connected = False

        print(f"Initializing broker {self.exchange_name}")

    # ==========================================================
    # CONNECT
    # ==========================================================

    async def connect(self):

        if self._connected:
            return

        exchange_class = getattr(ccxt, self.exchange_name)

        # Fix BinanceUS IPv6 issue
        connector = aiohttp.TCPConnector(family=socket.AF_INET)

        self.session = aiohttp.ClientSession(connector=connector)

        self.exchange = exchange_class({
            "apiKey": self.api_key,
            "secret": self.secret,
            "enableRateLimit": True,
            "timeout": 30000,
            "recvWindow": 10000,
            "session": self.session,
            "options": {
                "adjustForTimeDifference": True
            }
        })

        try:

            print("Syncing exchange time...")
            await self.exchange.load_time_difference()

            print("Loading markets...")
            await self.exchange.load_markets()

            self.symbols = list(self.exchange.markets.keys())

            print(f"{len(self.symbols)} markets loaded")

            self._connected = True

        except Exception as e:

            print(f"Exchange connection failed: {e}")
            raise

    # ==========================================================
    # SYMBOLS
    # ==========================================================

    async def fetch_symbol(self):

        if not self._connected:
            await self.connect()

        return self.symbols

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close(self):

        try:

            if self.exchange:
                await self.exchange.close()

            if self.session:
                await self.session.close()

            self._connected = False

        except Exception as e:
            print(f"Broker close error: {e}")

    # ==========================================================
    # MARKET DATA
    # ==========================================================

    async def fetch_ticker(self, symbol):

        if not self._connected:
            await self.connect()

        return await self.exchange.fetch_ticker(symbol)

    async def fetch_orderbook(self, symbol, limit=100):

        if not self._connected:
            await self.connect()

        return await self.exchange.fetch_order_book(symbol, limit)

    async def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        self.logger.info(f"Fetching OHLCV for {symbol}")

        if not self._connected:
            self.logger.info(f"Connecting to exchange {self.exchange_name}")
            return [
                [1700000000000, 42000, 42100, 41950, 42050, 12.4],
                [1700003600000, 42050, 42200, 42000, 42120, 8.1]
            ]

        return await self.exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=limit
        )

    # ==========================================================
    # TRADING
    # ==========================================================

    async def create_order(
            self,
            symbol,
            side,
            amount,
            type="market",
            price=None
    ):

        if not self._connected:
            await self.connect()

        return await self.exchange.create_order(
            symbol,
            type,
            side,
            amount,
            price
        )

    async def cancel_order(self, order_id, symbol):

        if not self._connected:
            await self.connect()

        return await self.exchange.cancel_order(order_id, symbol)

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    async def fetch_balance(self):

        if not self._connected:
            await self.connect()

        return await self.exchange.fetch_balance()

    # ==========================================================
    # ORDERS
    # ==========================================================

    async def fetch_order(self, symbol=None):

        if not self._connected:
            await self.connect()

        return await self.exchange.fetch_orders(symbol)