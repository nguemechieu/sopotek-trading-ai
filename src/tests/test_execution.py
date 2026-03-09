
from sopotek_trading_ai.src.sopotek_trading_ai.execution.execution_manager import ExecutionManager

class MockBroker:

    async def create_order(self, symbol, side, amount, type="market", price=None):

        return {
            "symbol": symbol,
            "side": side,
            "amount": amount
        }


def test_execution_order():

    broker = MockBroker()

    execution = ExecutionManager(broker)

    order = {
        "symbol": "BTC/USDT",
        "side": "BUY",
        "amount": 0.01
    }

    result = execution._execute(order)

    assert result["symbol"] == "BTC/USDT"