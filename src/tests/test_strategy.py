import pandas as pd

from sopotek_trading_ai.src.sopotek_trading_ai.strategy.momentum_strategy import MomentumStrategy



def test_momentum_signal():

    strategy = MomentumStrategy(None)

    data = pd.DataFrame({
        "close": [
            100,101,102,103,104,
            105,106,107,108,109,
            110,111,112,113,114,
            115,116,117,118,119
        ]
    })

    signal = strategy.on_bar(data.iloc[-1])

    assert signal is None or signal["side"] in ["BUY", "SELL"]