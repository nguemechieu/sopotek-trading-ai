import os
import sys
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.chart.chart_widget import ChartWidget
from frontend.ui.panels.orderbook_panel import OrderBookPanel


class DummyController:
    pass


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_chart_widget_supports_fractal_and_zigzag_indicators():
    _app()
    widget = ChartWidget("BTC/USDT", "1h", DummyController())

    fractal_key = widget.add_indicator("Fractal", 5)
    zigzag_key = widget.add_indicator("ZigZag", 5)

    assert fractal_key == "FRACTAL_5"
    assert zigzag_key == "ZIGZAG_5"

    df = pd.DataFrame(
        {
            "timestamp": [1700000000 + i * 60 for i in range(9)],
            "open": [1.0, 1.6, 2.8, 2.0, 1.1, 1.9, 3.2, 2.1, 1.2],
            "high": [1.3, 2.2, 5.0, 2.4, 1.4, 2.5, 6.0, 2.6, 1.5],
            "low": [0.8, 1.1, 2.0, 1.4, 0.4, 1.2, 2.1, 1.3, 0.7],
            "close": [1.1, 1.9, 3.1, 1.7, 0.9, 2.2, 3.8, 1.8, 1.0],
            "volume": [10, 12, 18, 11, 14, 15, 19, 13, 9],
        }
    )

    widget.update_candles(df)

    fractal_highs, fractal_lows = widget.indicator_items[fractal_key]
    zigzag_curve = widget.indicator_items[zigzag_key][0]

    assert len(fractal_highs.points()) >= 2
    assert len(fractal_lows.points()) >= 1

    x_data, y_data = zigzag_curve.getData()
    assert x_data is not None
    assert y_data is not None
    assert len(x_data) >= 3
    assert len(y_data) >= 3


def test_chart_widget_accepts_utc_timestamp_series():
    _app()
    widget = ChartWidget("EUR/USD", "4h", DummyController())

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-03-10T00:00:00+00:00",
                    "2026-03-10T04:00:00+00:00",
                    "2026-03-10T08:00:00+00:00",
                ],
                utc=True,
            ),
            "open": [1.10, 1.11, 1.12],
            "high": [1.12, 1.13, 1.14],
            "low": [1.09, 1.10, 1.11],
            "close": [1.11, 1.12, 1.13],
            "volume": [1000, 1100, 900],
        }
    )

    widget.update_candles(df)

    assert widget._last_x is not None
    assert len(widget._last_x) == 3
    assert widget._last_x[1] > widget._last_x[0]


def test_chart_widget_accepts_strategy_signal_timestamp_strings():
    _app()
    widget = ChartWidget("EUR/USD", "4h", DummyController())

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-03-13T00:00:00+00:00",
                    "2026-03-13T02:00:00+00:00",
                    "2026-03-13T04:00:00+00:00",
                ],
                utc=True,
            ),
            "open": [1.10, 1.11, 1.12],
            "high": [1.12, 1.13, 1.14],
            "low": [1.09, 1.10, 1.11],
            "close": [1.11, 1.12, 1.13],
            "volume": [1000, 1100, 900],
        }
    )

    widget.update_candles(df)
    widget.add_strategy_signal("2026-03-13T02:00:00.000000000Z", 1.12, "BUY")

    points = widget.signal_markers.points()
    assert len(points) == 1
    assert points[0].pos().x() == widget._last_x[1]


def test_chart_widget_maps_strategy_signal_row_index_to_chart_time_axis():
    _app()
    widget = ChartWidget("BTC/USDT", "1h", DummyController())

    df = pd.DataFrame(
        {
            "timestamp": [1700000000 + i * 60 for i in range(4)],
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [10, 12, 14, 16],
        }
    )

    widget.update_candles(df)
    widget.add_strategy_signal(2, 102.5, "SELL")

    points = widget.signal_markers.points()
    assert len(points) == 1
    assert points[0].pos().x() == widget._last_x[2]


def test_chart_widget_exposes_depth_and_market_info_tabs():
    _app()
    widget = ChartWidget("BTC/USDT", "1h", DummyController())

    df = pd.DataFrame(
        {
            "timestamp": [1700000000 + i * 60 for i in range(5)],
            "open": [100.0, 101.0, 102.0, 101.5, 103.0],
            "high": [101.0, 102.0, 103.5, 103.0, 104.0],
            "low": [99.5, 100.5, 101.2, 100.8, 102.4],
            "close": [100.8, 101.7, 102.4, 102.8, 103.6],
            "volume": [12, 18, 14, 17, 22],
        }
    )
    widget.update_candles(df)
    widget.update_price_lines(103.4, 103.8, last=103.6)
    widget.update_orderbook_heatmap(
        bids=[[103.4, 2.0], [103.2, 1.5], [103.0, 1.2]],
        asks=[[103.8, 1.0], [104.0, 1.6], [104.2, 2.1]],
    )

    tab_labels = [widget.market_tabs.tabText(index) for index in range(widget.market_tabs.count())]
    assert "Candlestick" in tab_labels
    assert "Depth Chart" in tab_labels
    assert "Market Info" in tab_labels
    assert widget.market_info_cards["Spread"].text() != "-"

    bid_x, bid_y = widget.depth_bid_curve.getData()
    ask_x, ask_y = widget.depth_ask_curve.getData()
    assert bid_x is not None and len(bid_x) == 3
    assert bid_y is not None and len(bid_y) == 3
    assert ask_x is not None and len(ask_x) == 3
    assert ask_y is not None and len(ask_y) == 3


def test_chart_widget_populates_advanced_header_metrics():
    _app()
    widget = ChartWidget("EUR/USD", "4h", DummyController())

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-03-12T10:00:00+00:00",
                    "2026-03-12T14:00:00+00:00",
                    "2026-03-12T18:00:00+00:00",
                ],
                utc=True,
            ),
            "open": [1.1000, 1.1020, 1.1030],
            "high": [1.1030, 1.1045, 1.1060],
            "low": [1.0990, 1.1010, 1.1020],
            "close": [1.1015, 1.1035, 1.1050],
            "volume": [1000, 1200, 900],
        }
    )

    widget.update_candles(df)
    widget.update_price_lines(1.1048, 1.1052, last=1.1050)

    assert widget.instrument_label.text() == "EUR/USD  4H"
    assert "Bid 1.1048" in widget.market_micro_label.text()
    assert "Ask 1.1052" in widget.market_micro_label.text()
    assert "Spread 0.00040000" in widget.market_micro_label.text()
    assert "T 2026-03-12 18:00 UTC" in widget.ohlcv_label.text()


def test_orderbook_panel_shows_recent_market_trades():
    _app()
    panel = OrderBookPanel()
    panel.update_recent_trades(
        [
            {
                "time": "2026-03-12T10:05:00+00:00",
                "side": "buy",
                "price": 103.55,
                "amount": 0.75,
                "notional": 77.6625,
            },
            {
                "time": "2026-03-12T10:05:02+00:00",
                "side": "sell",
                "price": 103.45,
                "amount": 0.40,
                "notional": 41.38,
            },
        ]
    )

    assert panel.tabs.count() == 2
    assert panel.tabs.tabText(1) == "Recent Trades"
    assert panel.recent_trades_table.item(0, 1).text() == "BUY"
    assert panel.recent_trades_table.item(1, 1).text() == "SELL"


def test_chart_widget_resolves_hovered_news_event_details():
    _app()
    widget = ChartWidget("BTC/USDT", "1h", DummyController())

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-03-12T10:00:00+00:00",
                    "2026-03-12T11:00:00+00:00",
                    "2026-03-12T12:00:00+00:00",
                    "2026-03-12T13:00:00+00:00",
                ],
                utc=True,
            ),
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.5, 104.0],
            "low": [99.5, 100.4, 101.4, 102.2],
            "close": [100.8, 101.7, 103.1, 103.7],
            "volume": [10, 14, 12, 16],
        }
    )
    widget.update_candles(df)
    widget.set_news_events(
        [
            {
                "timestamp": "2026-03-12T12:00:00+00:00",
                "title": "CPI surprise cools risk sentiment",
                "source": "Macro Wire",
                "summary": "Inflation data came in below expectations and traders quickly repriced rate-cut odds.",
                "impact": "high",
                "sentiment_score": 0.35,
            }
        ]
    )

    assert widget._visible_news_events
    event = widget._visible_news_events[0]
    hovered = widget._nearest_news_event(event["x"], event["y"])

    assert hovered is not None
    assert hovered["headline"] == "CPI surprise cools risk sentiment"
    assert "Macro Wire" in widget._news_hover_html(hovered)
    assert widget._nearest_news_event(event["x"] + 10_000_000.0, event["y"]) is None
