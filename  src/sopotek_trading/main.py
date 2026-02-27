import os
import socket
import uuid

from dotenv import load_dotenv
from sopotek_trading.app import SopotekTrading

load_dotenv()

def force_ipv4():
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = getaddrinfo_ipv4

force_ipv4()

if __name__ == "__main__":

    exchange = os.getenv("EXCHANGE", "binanceus")
    api_key = os.getenv("API_KEY")
    secret = os.getenv("API_SECRET")

    if not api_key or not secret:
        raise Exception("Missing API credentials")

    app = SopotekTrading(exchange, api_key, secret)



    result = app.run_trade(
        symbol="BTC/USDT",
        side="buy",
        amount=0.001
    )

    print(result)