import asyncio
import os
import pandas as pd
import ccxt.async_support as ccxt
import alpaca_trade_api as tradeapi
DATA_DIR = "./data/raw"

# ======================================
# CREATE DATA DIRECTORY
# ======================================

os.makedirs(DATA_DIR, exist_ok=True)


# ======================================
# CRYPTO DATA (CCXT)
# ======================================

async def download_crypto(exchange_name, symbol, timeframe="1h", limit=1000):

    exchange_class = getattr(ccxt, exchange_name)

    exchange = exchange_class()

    print(f"Downloading {symbol} from {exchange_name}")

    candles = await exchange.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=limit
    )


    df = pd.DataFrame(
        candles,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    filename = f"{symbol.replace('/','')}_{timeframe}.csv"

    path = os.path.join(DATA_DIR, filename)

    df.to_csv(path, index=False)

    await exchange.close()

    print(f"Saved -> {path}")


# ======================================
# STOCK DATA (ALPACA)
# ======================================

def download_stock(symbol):



    api = tradeapi.REST(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET"),
        "https://paper-api.alpaca.markets",
        api_version="v2"
    )

    bars = api.get_bars(symbol, "1Hour", limit=1000)

    df = bars.df

    path = f"{DATA_DIR}/{symbol}_1h.csv"

    df.to_csv(path)

    print(f"Saved -> {path}")


# ======================================
# FOREX DATA (OANDA)
# ======================================

async def download_forex(symbol):

    import aiohttp

    token = os.getenv("OANDA_TOKEN")

    account = os.getenv("OANDA_ACCOUNT")

    url = f"https://api-fxpractice.oanda.com/v3/instruments/{symbol}/candles"

    params = {
        "granularity": "H1",
        "count": 1000
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    async with aiohttp.ClientSession() as session:

        async with session.get(url, headers=headers, params=params) as resp:

            data = await resp.json()

    candles = []

    for c in data["candles"]:

        candles.append({
            "timestamp": c["time"],
            "open": float(c["mid"]["o"]),
            "high": float(c["mid"]["h"]),
            "low": float(c["mid"]["l"]),
            "close": float(c["mid"]["c"]),
            "volume": c["volume"]
        })

    df = pd.DataFrame(candles)

    path = f"{DATA_DIR}/{symbol}_1h.csv"

    df.to_csv(path, index=False)

    print(f"Saved -> {path}")


# ======================================
# MAIN
# ======================================

async def main():

    # crypto
    await download_crypto("binanceus", "BTC/USDT")
    await download_crypto("binanceus", "XLM/USDT")

    # stocks
    download_stock("AAPL")

    # forex
    await download_forex("EUR_USD")


if __name__ == "__main__":
    asyncio.run(main())