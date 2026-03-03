# brokers/ccxt_broker.py

import asyncio
import socket
from abc import ABC

import aiohttp
import ccxt.async_support as ccxt
import pandas as pd

from sopotek_trading.backend.broker.base_broker import BaseBroker


class CCXTBroker(BaseBroker, ABC):

    def __init__(
            self,
            exchange_name,
            api_key=None,
            secret=None,
            mode="live",
            rate_limiter=None,
            logger=None,
    ):
        self.ohlcv = pd.DataFrame(columns=[
             "time", "open", "high", "low", "close", "volume"
        ])
        self.mode = mode
        self.logger = logger
        self.rate_limiter = rate_limiter
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.secret = secret

        self.session = None
        self.exchange = None

        self._connected = False
        self._health_task = None
        self._reconnect_lock = asyncio.Lock()

    # ==========================================================
    # CONNECT WITH EXPONENTIAL RETRY
    # ==========================================================




    async def connect(self, max_retries=5):

     retry = 0

     while retry < max_retries:
        try:
            exchange_class = getattr(ccxt, self.exchange_name)

            # Create exchange FIRST
            self.exchange = exchange_class({
                "apiKey": self.api_key,
                "secret": self.secret,
                "enableRateLimit": True,
                "options": {
                    "adjustForTimeDifference": True,
                    "recvWindow": 10000,
                },
            })


            # 🔥 FORCE IPv4 at transport layer

            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            self.exchange.session = aiohttp.ClientSession(connector=connector)

            # 🔥 Sync clock with Binance
            await self.exchange.load_time_difference()



            # Now load markets with retry
            await self._load_markets_with_retry()

            self._connected = True

            if self.logger:
                self.logger.info(f"{self.exchange_name} connected.")

            self._health_task = asyncio.create_task(self._health_monitor())
            return

        except Exception as e:
            retry += 1
            wait_time = 2 ** retry
            if self.logger:
                self.logger.warning(
                    f"Connection attempt {retry} failed: {e}. Retrying in {wait_time}s"
                )
            await asyncio.sleep(wait_time)

            raise Exception("Max connection retries exceeded.")

    # ==========================================================
    # LOAD MARKETS WITH EXPONENTIAL BACKOFF
    # ==========================================================

    async def _load_markets_with_retry(self, retries=5):

        for attempt in range(retries):
            try:
                await self.exchange.load_markets()
                return
            except Exception as e:
                delay = 2 ** attempt
                if self.logger:
                    self.logger.warning(
                        f"load_markets failed (attempt {attempt+1}): {e}. Retrying in {delay}s"
                    )
                await asyncio.sleep(delay)

        raise Exception("Failed to load markets after retries.")

    # ==========================================================
    # HEALTH MONITOR
    # ==========================================================

    async def _health_monitor(self, interval=20):
        """
        Runs in background and checks if exchange is responsive.
        If not, triggers reconnect.
        """
        while True:
            await asyncio.sleep(interval)

            try:
                if not self._connected:
                    continue

                # Lightweight ping call
                await self.exchange.fetch_time()

                if self.logger:
                    self.logger.debug("Broker health check OK.")

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Health check failed: {e}")
                await self._reconnect()

    # ==========================================================
    # AUTO RECONNECT
    # ==========================================================

    async def _reconnect(self):

        async with self._reconnect_lock:

            if self.logger:
                self.logger.warning("Reconnecting broker...")

            self._connected = False

            await self.close()

            await self.connect()

    # ==========================================================
    # STANDARD METHODS (UNCHANGED)
    # ==========================================================

    async def fetch_balance(self):
        raw_balance = await self.exchange.fetch_balance()

        total = raw_balance.get("total", self.ohlcv)
        free = raw_balance.get("free", self.ohlcv)
        used = raw_balance.get("used", self.ohlcv)

        currency = next(iter(total.keys()), None)
        equity = float(total.get(currency, self.ohlcv))

        return {
            "equity": equity,
            "free": float(free.get(currency, self.ohlcv)),
            "used": float(used.get(currency, self.ohlcv)),
            "currency": currency,
        }

    async def fetch_ticker(self, symbol):
        return await self.exchange.fetch_ticker(symbol)

    async def fetch_ohlcv(self, symbol, timeframe,limit):
        return await self.exchange.fetch_ohlcv(symbol, timeframe,limit)

    async def fetch_order_book(self, symbol):
        return await self.exchange.fetch_order_book(symbol)

    async def create_order(self, symbol, side, order_type, amount=0.0, price=None,stop_loss=None, take_profit=None):

        if self.mode == "paper":
            return {"id": "paper_order", "status": "filled"}

        if self.rate_limiter:
            await self.rate_limiter.wait()

        return await self.exchange.create_order(symbol=symbol, side=side,
                                                order_type=order_type,
                                                amount=amount, price=price,stop_loss=stop_loss,take_profit=take_profit)

    async def cancel_order(self, order_id: str, symbol: str):
        return await self.exchange.cancel_order(order_id, symbol)

    async def fetch_positions(self):
        if hasattr(self.exchange, "fetch_positions"):
            return await self.exchange.fetch_positions()
        return []

    # ==========================================================
    # CLEAN SHUTDOWN
    # ==========================================================

    async def close(self):

     self._connected = False

     if self._health_task:
        self._health_task.cancel()

     try:
        if self.exchange:
            if hasattr(self.exchange, "session"):
                await self.exchange.session.close()
            await self.exchange.close()

        if self.logger:
            self.logger.info(f"{self.exchange_name} connection closed.")

     except Exception as e:
        if self.logger:
            self.logger.warning(f"Shutdown error: {e}")


    async def fetch_realized_pnl(self) -> float:
      return 0.0
    async def fetch_unrealized_pnl(self):
        if hasattr(self.exchange, "fetch_positions"):
            positions = await self.exchange.fetch_positions()
            total = 0.0
            for pos in positions: total += float(pos.get("unrealizedPnl", self.ohlcv))
            return total
        return 0.0

    async def fetch_symbols(self):
        if not self.exchange.markets:
            await self.exchange.load_markets()

        return self.exchange.symbols
