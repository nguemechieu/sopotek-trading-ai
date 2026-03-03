# brokers/oanda_broker.py

import asyncio
from abc import ABC

import oandapyV20
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.pricing as pricing
import oandapyV20.endpoints.orders as orders

from sopotek_trading.backend.broker.base_broker import BaseBroker


class OandaBroker(BaseBroker, ABC):

    def __init__(
            self,
            api_key,
            account_id,
            mode="live",
            rate_limiter=None,
            logger=None,
    ):
        self.client = oandapyV20.API(access_token=api_key)
        self.account_id = account_id
        self.mode = mode
        self.rate_limiter = rate_limiter
        self.logger = logger

    # -------------------------------------------------
    # CONNECT
    # -------------------------------------------------

    async def connect(self):
        if self.logger:
            self.logger.info("OANDA broker connected.")
        return True

    # -------------------------------------------------
    # BALANCE (Normalized)
    # -------------------------------------------------

    async def fetch_balance(self):

        if self.rate_limiter:
            await self.rate_limiter.wait()

        loop = asyncio.get_running_loop()

        r = accounts.AccountDetails(self.account_id)

        response = await loop.run_in_executor(
            None,
            lambda: self.client.request(r)
        )

        account = response["account"]

        equity = float(account["NAV"])
        balance = float(account["balance"])
        currency = account["currency"]

        return {
            "equity": equity,
            "free": balance,
            "used": equity - balance,
            "currency": currency,
        }

    # -------------------------------------------------
    # TICKER
    # -------------------------------------------------

    async def fetch_ticker(self, symbol):

        instrument = self._normalize_symbol(symbol)

        if self.rate_limiter:
            await self.rate_limiter.wait()

        loop = asyncio.get_running_loop()

        r = pricing.PricingInfo(
            accountID=self.account_id,
            params={"instruments": instrument},
        )

        response = await loop.run_in_executor(
            None,
            lambda: self.client.request(r)
        )

        price_data = response["prices"][0]

        return {
            "bid": float(price_data["bids"][0]["price"]),
            "ask": float(price_data["asks"][0]["price"]),
        }

    # -------------------------------------------------
    # ORDER
    # -------------------------------------------------

    async def create_order(
            self,
            symbol,
            side,
            order_type,
            amount,
            price=None,
    ):

        if self.mode == "paper":
            if self.logger:
                self.logger.info("Paper OANDA order executed.")
            return {"id": "paper_order", "status": "filled"}

        instrument = self._normalize_symbol(symbol)

        units = amount if side.lower() == "buy" else -amount

        order_data = {
            "order": {
                "instrument": instrument,
                "units": str(units),
                "type": "MARKET",
                "positionFill": "DEFAULT",
            }
        }

        if self.rate_limiter:
            await self.rate_limiter.wait()

        loop = asyncio.get_running_loop()

        r = orders.OrderCreate(
            accountID=self.account_id,
            data=order_data,
        )

        response = await loop.run_in_executor(
            None,
            lambda: self.client.request(r)
        )

        return response

    # -------------------------------------------------
    # SYMBOL NORMALIZATION
    # -------------------------------------------------

    def _normalize_symbol(self, symbol):
        # BTC/USDT -> BTC_USDT
        # EUR/USD -> EUR_USD
        return symbol.replace("/", "_").upper()

    # -------------------------------------------------
    # CLOSE
    # -------------------------------------------------

    async def close(self):
        if self.logger:
            self.logger.info("OANDA broker closed.")
        return True