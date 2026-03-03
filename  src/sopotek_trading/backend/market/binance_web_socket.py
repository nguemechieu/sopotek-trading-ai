import json

import websockets


class BinanceWebSocket:

    def __init__(self, symbols, timeframe,
                 on_candle_callback,
                 on_ticker_callback):

        self.symbols = [
            s.lower().replace("/", "") for s in symbols
        ]

        self.timeframe = timeframe
        self.on_candle_callback = on_candle_callback
        self.on_ticker_callback = on_ticker_callback

        self.base_url = "wss://stream.binance.us:9443/stream"

        self.running = True

    # ======================================================
    # START
    # ======================================================

    async def start(self):

        streams = []

        # Candle streams
        for symbol in self.symbols:
            streams.append(
                f"{symbol}@kline_{self.timeframe}"
            )

        # Bid/Ask streams
        for symbol in self.symbols:
            streams.append(
                f"{symbol}@bookTicker"
            )

        url = f"{self.base_url}?streams={'/'.join(streams)}"

        async with websockets.connect(url, ping_interval=20) as ws:

            while self.running:

                message = await ws.recv()
                data = json.loads(message)

                if "data" not in data:
                    continue

                payload = data["data"]

                # -----------------------------
                # Handle Candle
                # -----------------------------
                if payload.get("e") == "kline":

                    k = payload["k"]

                    # only closed candle
                    if not k["x"]:
                        continue

                    symbol = payload["s"]

                    if symbol.endswith("USDT"):
                        symbol = symbol[:-4] + "/USDT"

                    candle = {
                        "timestamp": k["t"],
                        "open": float(k["o"]),
                        "high": float(k["h"]),
                        "low": float(k["l"]),
                        "close": float(k["c"]),
                        "volume": float(k["v"]),
                    }

                    await self.on_candle_callback(symbol, candle)

                # -----------------------------
                # Handle BookTicker
                # -----------------------------
                elif payload.get("e") == "bookTicker":

                    symbol = payload["s"]

                    if symbol.endswith("USDT"):
                        symbol = symbol[:-4] + "/USDT"

                    bid = float(payload["b"])
                    ask = float(payload["a"])

                    await self.on_ticker_callback(symbol, bid, ask)

    def stop(self):
        self.running = False