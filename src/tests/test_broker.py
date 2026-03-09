import pytest
from sopotek_trading_ai.src.sopotek_trading_ai.broker.ccxt_broker import CCXTBroker



@pytest.mark.asyncio
async def test_fetch_ticker():

    broker = CCXTBroker("binance")

    await broker.connect()

    ticker = await broker.fetch_ticker("BTC/USDT")

    assert ticker is not None
    assert "symbol" in ticker or "last" in ticker

    await broker.close()


@pytest.mark.asyncio
async def test_fetch_order_book():

    broker = CCXTBroker("binance")

    await broker.connect()

    orderbook = await broker.fetch_order_book("BTC/USDT")

    assert "bids" in orderbook
    assert "asks" in orderbook

    await broker.close()