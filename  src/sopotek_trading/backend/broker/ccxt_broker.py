# brokers/ccxt_broker.py

import asyncio
import logging
import socket
from abc import ABC
from typing import Optional

import aiohttp
import ccxt.async_support as ccxt

from sopotek_trading.backend.broker.base_broker import BaseBroker


class CCXTBroker(BaseBroker, ABC):

    def __init__(
            self,config
    ):

        if config is None:

            raise(
                "Config file can't be None or empty."
            )

        self.logger = logging.getLogger(__name__)
        self.paper_balance = None
        self.paper_order_id = None
        self.paper_positions = None
        self.config = config
        self.api_key =config.get("api_key")
        self.secret = config.get("secret")
        self.mode = config.get("mode")
        self.rate_limiter = config.get("rate_limiter")
        self.exchange_name = config.get("exchange_name")
        self.exchange = None
        self.session = None
        self._connected = False
        self._health_task = None
        if self.mode == "paper":
         self.paper_balance = config.get("paper_balance", 10000.0)
         self.paper_order_id = 0
         self.paper_positions = {}
        else:
         self.paper_balance = None
         self.paper_order_id = None
         self.paper_positions = None
        self._reconnect_lock = asyncio.Lock()

    # ==========================================================
    # CONNECT
    # ==========================================================

    async def connect(self, max_retries=5):

        if self._connected:
            return

        retry = 0

        while retry < max_retries:

            try:
                exchange_class = getattr(ccxt, self.exchange_name)
                self.exchange = exchange_class({

                    "apiKey": self.api_key,
                    "secret": self.secret,
                    "enableRateLimit": True,
                })


                # SAFE: set defaultType AFTER creation
                self.exchange.options["defaultType"] = self.config['exchange_options']

                # Force IPv4
                connector = aiohttp.TCPConnector(
                    family=socket.AF_INET
                )
                self.session = aiohttp.ClientSession(
                    connector=connector
                )
                self.exchange.session = self.session

                await self.exchange.load_markets()

                # Sync time if supported
                if hasattr(self.exchange, "load_time_difference"):
                    await self.exchange.load_time_difference()

                self._connected = True

                if self.logger:
                    self.logger.info(
                        f"{self.exchange_name} connected."
                    )

                self._health_task = asyncio.create_task(
                    self._health_monitor()
                )

                return

            except Exception as e:

                retry += 1
                wait = 2 ** retry

                if self.logger:
                    self.logger.warning(
                        f"Connection failed ({retry}/{max_retries}): {e}. Retrying in {wait}s"
                    )

                await asyncio.sleep(wait)

        raise Exception("Max connection retries exceeded.")

    # ==========================================================
    # HEALTH MONITOR
    # ==========================================================

    async def _health_monitor(self, interval=20):

     while self._connected:
        await asyncio.sleep(interval)

        try:
            await self.exchange.fetch_time()

        except Exception as e:
            self.logger.warning(
                "error",e
            )
            asyncio.create_task(self._reconnect())


    # ==========================================================
    # RECONNECT
    # ==========================================================

    async def _reconnect(self):

        async with self._reconnect_lock:

            if self.logger:
                self.logger.warning("Reconnecting...")

            await self.close()

            try:
                await self.connect()
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Reconnect failed: {e}"
                    )

    # ==========================================================
    # BALANCE
    # ==========================================================

    async def fetch_balance(self, base_currency="USDT"):

     raw = await self.exchange.fetch_balance()

     total = raw.get("total", {})
     free = raw.get("free", {})
     used = raw.get("used", {})

     equity = float(total.get(base_currency, 0.0))
     free_amt = float(free.get(base_currency, 0.0))
     used_amt = float(used.get(base_currency, 0.0))

     return {
        "equity": equity,
        "free": free_amt,
        "used": used_amt,
        "currency": base_currency,
    }
    # ==========================================================
    # MARKET DATA
    # ==========================================================

    async def fetch_ticker(self, symbol):
        return await self.exchange.fetch_ticker(symbol)

    async def fetch_ohlcv(self, symbol, timeframe, limit=500):
        return await self.exchange.fetch_ohlcv(
            symbol, timeframe, limit=limit
        )

    async def fetch_order_book(self, symbol):
        return await self.exchange.fetch_order_book(symbol)

    async def fetch_symbols(self):

        if not self.exchange.markets:
            await self.exchange.load_markets()

        return self.exchange.symbols

    # ==========================================================
    # TRADING
    # ==========================================================

    async def create_order(
            self,
            symbol: str,
            side: str,
            order_type: str,
            amount: float,
            price: Optional[float] = None,
            stop_loss: Optional[float] = None,
            take_profit: Optional[float] = None
    ):

     if amount <= 0:
        raise ValueError("Order amount must be > 0")

     if self.mode == "paper":
        return self._simulate_order(
            symbol, side, amount, price
        )

     if self.rate_limiter:
        await self.rate_limiter.wait()

     params = {}

     if stop_loss:
        params["stopLoss"] = stop_loss

     if take_profit:
        params["takeProfit"] = take_profit

     return await self.exchange.create_order(
        symbol=symbol,
        type=order_type,
        side=side,
        amount=amount,
        price=price,
        params=params
    )

    async def cancel_order(self, order_id, symbol):
        return await self.exchange.cancel_order(
            order_id, symbol
        )

    async def fetch_positions(self):

        if hasattr(self.exchange, "fetch_positions"):
            return await self.exchange.fetch_positions()

        return []

    # ==========================================================
    # PNL
    # ==========================================================

    async def fetch_unrealized_pnl(self):

        if not hasattr(self.exchange, "fetch_positions"):
            return 0.0

        positions = await self.exchange.fetch_positions()

        total = 0.0
        for pos in positions:
            total += float(pos.get("unrealizedPnl", 0.0))

        return total

    async def fetch_realized_pnl(self):
        return 0.0

    # ==========================================================
    # SHUTDOWN
    # ==========================================================

    async def close(self):

     self._connected = False

     current_task = asyncio.current_task()

     if self._health_task and self._health_task != current_task:
        self._health_task.cancel()
        await asyncio.gather(
            self._health_task,
            return_exceptions=True
        )

     try:
        if self.session:
            await self.session.close()

        if self.exchange:
            await self.exchange.close()

        if self.logger:
            self.logger.info(
                f"{self.exchange_name} closed."
            )

     except Exception as e:
        if self.logger:
            self.logger.warning(
                f"Shutdown error: {e}"
            )

    def _simulate_order(self, symbol, side, amount, price):

     if price is None or price <= 0:
        raise ValueError("Paper trading requires a valid price")

     self.paper_order_id += 1
     order_id = f"paper_{self.paper_order_id}"


     cost = amount * price
     self.paper_order_id += 1
     position = self.paper_positions.get(symbol)

    # =========================
    # BUY
    # =========================
     if side.lower() == "buy":

        if self.paper_balance < cost:
            raise ValueError("Insufficient paper balance")

        self.paper_balance -= cost

        if position:
            # Average price update
            total_amount = position["amount"] + amount
            avg_price = (
                                (position["amount"] * position["entry_price"]) +
                                (amount * price)
                        ) / total_amount

            position["amount"] = total_amount
            position["entry_price"] = avg_price
        else:
            self.paper_positions[symbol] = {
                "amount": amount,
                "entry_price": price
            }

    # =========================
    # SELL
    # =========================
     elif side.lower() == "sell":

        if not position or position["amount"] < amount:
            raise ValueError("No position to sell")

        pnl = (price - position["entry_price"]) * amount

        self.paper_balance += cost
        self.paper_balance += pnl

        position["amount"] -= amount

        if position["amount"] == 0:
            del self.paper_positions[symbol]

     else:
        raise ValueError("Invalid side")

     return {
        "id": order_id,
        "status": "filled",
        "symbol": symbol,
        "side": side,
        "price": price,
        "amount": amount,
        "remaining": 0,
        "paper_balance": self.paper_balance
    }