import asyncio
import json
import websockets


class BinanceWebSocket:

    def __init__(self, symbols, event_bus):
        self.symbols = symbols
        self.bus = event_bus

        self.url = "wss://stream.binance.com:9443/ws"

    async def connect(self):
        streams = "/".join(
            f"{s.replace('/', '').lower()}@ticker"
            for s in self.symbols
        )

        url = f"{self.url}/{streams}"

        async with websockets.connect(url) as ws:
            while True:
                msg = await ws.recv()

                data = json.loads(msg)

                await self.bus.publish({
                    "type": "MARKET_TICK",
                    "data": data
                })
