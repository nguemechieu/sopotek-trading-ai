import aiohttp
import asyncio


class OandaWebSocket:

    def __init__(self, token, account_id):
        self.token = token
        self.account_id = account_id

    async def stream(self):
        url = f"https://stream-fxpractice.oanda.com/v3/accounts/{self.account_id}/pricing/stream"

        headers = {
            "Authorization": f"Bearer {self.token}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                async for line in resp.content:
                    print(line)
