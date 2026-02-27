import websocket
import json


def process_market_data(data):
    pass


def on_message(ws=None, message=None):
    data = json.loads(message)
    process_market_data(data)
ws = websocket.WebSocketApp(
    "wss://stream.binance.com:9443/ws/btcusdt@trade",
    on_message=on_message
)


ws.run_forever()