import aiohttp

from broker.base_broker import BaseBroker


class OandaBroker(BaseBroker):

    def __init__(self, token, account_id):
        self.token = token
        self.account_id = account_id

        self.base_url = "https://api.fx-trade.oanda.com"

    # ===============================
    # CONNECT
    # ===============================

    async def connect(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    # ===============================
    # TICKER
    # ===============================

    async def fetch_ticker(self, symbol):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing"

        params = {"instruments": symbol}

        headers = {
            "Authorization": f"Bearer {self.token}"
        }

        async with self.session.get(
                url,
                headers=headers,
                params=params
        ) as resp:
            return await resp.json()


    async def fetch_trades(self, symbol):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/trades"
        params = {"instruments": symbol}
        headers = {
            "Authorization": f"Bearer {self.token}"

        }
        async with self.session.get(
            url,
                headers=headers,
            params=params) as resp:
            return await resp.json()


    async def fetch_symbol(self):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/instruments"
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        async with self.session.get(
            url,
                headers=headers
        ) as resp:
            return await resp.json()

    async def fetch_orders(self, symbol):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders"
        headers = {
            "Authorization": f"Bearer {self.token}"

        }
        async with self.session.get(
            url,
                headers=headers
        ) as resp:
            return await resp.json()

    async def create_order(self, symbol, side, type, price, quantity , order_type,stop_loss, take_profit,slippage):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders"
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        async with self.session.post(
            url,
                headers=headers,
            data={
                "symbol": symbol,
                "side": side,
                "type": type,
                "price": price,
                "quantity": quantity,
                "order_type": order_type,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "slippage": slippage
            }
        ) as resp:
            return await resp.json()


    async def cancel_order(self, symbol, order_id):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        async with self.session.get(
            url,
                headers=headers

        ) as resp:
            return await resp.json()

    async def cancel_all_orders(self):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders"
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        async with self.session.get(
            url,
                headers=headers
        ) as resp:
            return await resp.json()

    async def fetch_ticker(self,symbol):
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing"
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        async with self.session.get(
            url,
                headers=headers,
            params={"instruments": symbol}
        ) as resp:
            return await resp.json()