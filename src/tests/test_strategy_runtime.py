from strategy.strategy import Strategy


def test_compute_features_returns_empty_frame_for_invalid_candles():
    strategy = Strategy()

    df = strategy.compute_features([{"bad": "shape"}, ["too", "short"]])

    assert df.empty
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_generate_signal_skips_short_ohlcv_history():
    strategy = Strategy()
    candles = [
        [1700000000000 + i * 3600000, 100 + i, 101 + i, 99 + i, 100.5 + i, 10 + i]
        for i in range(10)
    ]

    assert strategy.generate_signal(candles) is None
