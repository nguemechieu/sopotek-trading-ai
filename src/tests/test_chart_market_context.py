import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.chart.chart_widget import ChartWidget


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _controller():
    return SimpleNamespace(broker=None, config=None)


def test_chart_background_context_flags_fast_printing_aggressive_buying_and_trend_strength():
    _app()
    widget = ChartWidget("BTC/USDT", "tick", _controller())
    frame = pd.DataFrame(
        {
            "timestamp": [1700000000, 1700000060, 1700000120, 1700000180, 1700000240, 1700000270, 1700000285, 1700000292],
            "open": [100.0, 101.0, 102.0, 103.0, 105.0, 107.0, 110.0, 113.0],
            "high": [101.3, 102.3, 103.4, 105.5, 107.6, 110.5, 113.6, 116.4],
            "low": [99.5, 100.4, 101.5, 102.4, 104.1, 106.3, 109.1, 112.1],
            "close": [101.0, 102.0, 103.1, 105.0, 107.0, 110.0, 113.0, 116.0],
            "volume": [100.0, 104.0, 109.0, 118.0, 130.0, 220.0, 270.0, 320.0],
        }
    )

    widget.update_candles(frame)

    background_text = widget.background_context_label.text()
    details_html = widget.market_info_details.toHtml()

    assert "Fast bar printing" in background_text
    assert "Aggressive buying" in background_text
    assert "Trend strength" in background_text
    assert "Long bullish candles" in details_html
    assert "Repeated higher highs / higher lows" in details_html


def test_chart_background_context_flags_slow_printing_rejection_and_resistance_pressure():
    _app()
    widget = ChartWidget("EUR/USD", "tick", _controller())
    frame = pd.DataFrame(
        {
            "timestamp": [1700000000, 1700000030, 1700000060, 1700000090, 1700000180, 1700000300, 1700000480, 1700000720],
            "open": [100.0, 102.0, 104.0, 106.0, 107.10, 107.30, 107.40, 107.50],
            "high": [102.0, 104.1, 106.0, 108.0, 110.00, 110.10, 109.95, 110.05],
            "low": [99.4, 101.3, 103.2, 105.1, 106.60, 106.90, 107.00, 106.95],
            "close": [101.4, 103.4, 105.4, 106.8, 107.20, 107.25, 107.35, 107.30],
            "volume": [150.0, 145.0, 140.0, 136.0, 95.0, 80.0, 72.0, 65.0],
        }
    )

    widget.update_candles(frame)

    background_text = widget.background_context_label.text()
    details_html = widget.market_info_details.toHtml()

    assert "Slow bar printing" in background_text
    assert "Rejection / indecision" in background_text
    assert "Resistance pressure" in background_text
    assert "Small candles with long wicks" in details_html
    assert "Repeated failures at one level" in details_html
