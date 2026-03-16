import html
from datetime import datetime, timezone

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph import DateAxisItem, InfiniteLine, PlotWidget, ScatterPlotItem, SignalProxy, TextItem, mkPen

from frontend.ui.chart.chart_items import CandlestickItem
from frontend.ui.chart.indicator_utils import (
    accumulation_distribution,
    accelerator,
    adx,
    alligator,
    atr,
    awesome,
    bears_power,
    bollinger,
    bulls_power,
    cci,
    demarker,
    ema,
    envelopes,
    force_index,
    gator,
    ichimoku,
    lwma,
    macd,
    market_facilitation_index,
    momentum,
    money_flow_index,
    obv,
    parabolic_sar,
    rsi,
    rvi,
    sma,
    smma,
    standard_deviation,
    stochastic,
    true_range,
    williams_r,
)


class ChartWidget(QWidget):
    sigMouseMoved = QtCore.Signal(object)
    sigTradeLevelRequested = QtCore.Signal(dict)
    sigTradeLevelChanged = QtCore.Signal(dict)
    sigTradeContextAction = QtCore.Signal(dict)

    def __init__(self, symbol: str, timeframe: str, controller, candle_up_color: str = "#26a69a", candle_down_color: str = "#ef5350"):
        super().__init__()
        self.controller = controller
        self.symbol = symbol
        self.timeframe = timeframe
        self.candle_up_color = candle_up_color
        self.candle_down_color = candle_down_color
        self._last_candles = None
        self.show_bid_ask_lines = True
        self._last_bid = None
        self._last_ask = None

        self.indicators = []
        self.indicator_items = {}
        self.indicator_panes = {}
        self.heatmap_buffer = []
        self.max_heatmap_rows = 220
        self.max_heatmap_levels = 120
        self._last_heatmap_price_range = None
        self._last_df = None
        self._last_x = None
        self._last_candle_stats = None
        self._watermark_initialized = False
        self._auto_fit_pending = True
        self._last_view_context = None
        self.default_visible_bars = 120
        self.chart_background = "#11161f"
        self.panel_background = "#171d29"
        self.grid_color = (130, 142, 160, 34)
        self.axis_color = "#9aa4b2"
        self.muted_text = "#728198"
        self._last_price_change = None
        self._news_events = []
        self._news_items = []
        self._visible_news_events = []
        self._trade_overlay_updating = False
        self._trade_overlay_state = {"side": "buy", "entry": None, "stop_loss": None, "take_profit": None}
        self._last_orderbook_bids = []
        self._last_orderbook_asks = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        self.info_bar = QFrame()
        self.info_bar.setStyleSheet(
            """
            QFrame {
                background-color: #171d29;
                border: 1px solid #273142;
                border-radius: 12px;
            }
            """
        )
        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(14, 10, 14, 10)
        info_layout.setSpacing(12)

        left_info = QVBoxLayout()
        left_info.setContentsMargins(0, 0, 0, 0)
        left_info.setSpacing(2)

        self.instrument_label = QLabel()
        self.instrument_label.setStyleSheet("color: #f6f8fb; font-weight: 800; font-size: 15px;")
        left_info.addWidget(self.instrument_label)

        self.market_meta_label = QLabel()
        self.market_meta_label.setStyleSheet("color: #728198; font-size: 11px;")
        left_info.addWidget(self.market_meta_label)
        info_layout.addLayout(left_info, 2)

        center_info = QVBoxLayout()
        center_info.setContentsMargins(0, 0, 0, 0)
        center_info.setSpacing(2)

        self.market_stats_label = QLabel()
        self.market_stats_label.setStyleSheet("color: #32d296; font-weight: 800; font-size: 15px;")
        center_info.addWidget(self.market_stats_label)

        self.market_micro_label = QLabel()
        self.market_micro_label.setStyleSheet("color: #9aa4b2; font-size: 11px;")
        center_info.addWidget(self.market_micro_label)
        info_layout.addLayout(center_info, 3)

        self.ohlcv_label = QLabel()
        self.ohlcv_label.setStyleSheet("color: #dde5ef; font-weight: 700; font-size: 11px;")
        self.ohlcv_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(self.ohlcv_label, 3)

        layout.addWidget(self.info_bar)

        self.market_tabs = QTabWidget()
        self.market_tabs.setDocumentMode(True)
        self.market_tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #273142;
                background-color: #11161f;
                border-radius: 14px;
            }
            QTabBar::tab {
                background-color: #171d29;
                color: #8e9bab;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #1f2735;
                color: #f6f8fb;
            }
            """
        )
        layout.addWidget(self.market_tabs, 1)

        self.candlestick_page = QWidget()
        candlestick_layout = QVBoxLayout(self.candlestick_page)
        candlestick_layout.setContentsMargins(0, 0, 0, 0)
        candlestick_layout.setSpacing(0)

        self.splitter = QSplitter(QtCore.Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)
        self.splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: #1a2230;
                border-top: 1px solid #2b3748;
                border-bottom: 1px solid #2b3748;
            }
            QSplitter::handle:hover {
                background-color: #243042;
            }
            """
        )
        candlestick_layout.addWidget(self.splitter)
        self.market_tabs.addTab(self.candlestick_page, "Candlestick")

        date_axis_top = DateAxisItem(orientation="bottom")
        self.price_plot = PlotWidget(axisItems={"bottom": date_axis_top})
        self.price_plot.setLabel("right", "Price")
        self.price_plot.hideAxis("left")
        self.price_plot.showAxis("right")
        self.price_plot.hideAxis("bottom")
        self.price_plot.setMinimumHeight(360)
        self.splitter.addWidget(self.price_plot)

        self.candle_item = CandlestickItem(
            body_width=60.0,
            up_color=self.candle_up_color,
            down_color=self.candle_down_color,
        )
        self.price_plot.addItem(self.candle_item)

        self.ema_curve = self.price_plot.plot(pen=mkPen("#42a5f5", width=1.8))
        self.ema_curve.setVisible(False)

        self.signal_markers = ScatterPlotItem()
        self.news_markers = ScatterPlotItem()
        self.trade_scatter = ScatterPlotItem()
        self.price_plot.addItem(self.signal_markers)
        self.price_plot.addItem(self.news_markers)
        self.price_plot.addItem(self.trade_scatter)

        date_axis_mid = DateAxisItem(orientation="bottom")
        self.volume_plot = PlotWidget(axisItems={"bottom": date_axis_mid})
        self.volume_plot.setXLink(self.price_plot)
        self.volume_plot.setLabel("left", "Volume")
        self.volume_plot.hideAxis("right")
        self.volume_plot.hideAxis("bottom")
        self.volume_plot.setMinimumHeight(120)
        self.splitter.addWidget(self.volume_plot)

        self.volume_bars = pg.BarGraphItem(x=[], height=[], width=60.0, brush="#5c6bc0")
        self.volume_plot.addItem(self.volume_bars)

        date_axis_bottom = DateAxisItem(orientation="bottom")
        self.heatmap_plot = PlotWidget(axisItems={"bottom": date_axis_bottom})
        self.heatmap_plot.setXLink(self.price_plot)
        self.heatmap_plot.setLabel("left", "Orderbook")
        self.heatmap_plot.setLabel("bottom", "Gregorian Time")
        self.heatmap_plot.setMinimumHeight(120)
        self.splitter.addWidget(self.heatmap_plot)

        self.heatmap_image = pg.ImageItem()
        colormap = pg.colormap.get("inferno")
        self.heatmap_image.setLookupTable(colormap.getLookupTable())
        self.heatmap_plot.addItem(self.heatmap_image)

        self.depth_page = QWidget()
        depth_layout = QVBoxLayout(self.depth_page)
        depth_layout.setContentsMargins(10, 10, 10, 10)
        depth_layout.setSpacing(8)

        self.depth_summary_label = QLabel("Depth chart will populate when live order book data arrives.")
        self.depth_summary_label.setStyleSheet("color: #8e9bab; font-size: 12px;")
        depth_layout.addWidget(self.depth_summary_label)

        self.depth_plot = PlotWidget()
        self.depth_plot.setMinimumHeight(360)
        self._style_plot(self.depth_plot, left_label="Cumulative Size", bottom_label="Price", show_bottom=True)
        self.depth_bid_curve = self.depth_plot.plot(
            [],
            [],
            pen=mkPen("#26a69a", width=2.2),
            stepMode="right",
            fillLevel=0,
            brush=(38, 166, 154, 70),
        )
        self.depth_ask_curve = self.depth_plot.plot(
            [],
            [],
            pen=mkPen("#ef5350", width=2.2),
            stepMode="right",
            fillLevel=0,
            brush=(239, 83, 80, 70),
        )
        depth_layout.addWidget(self.depth_plot, 1)
        self.market_tabs.addTab(self.depth_page, "Depth Chart")

        self.market_info_page = QWidget()
        info_tab_layout = QVBoxLayout(self.market_info_page)
        info_tab_layout.setContentsMargins(10, 10, 10, 10)
        info_tab_layout.setSpacing(10)

        self.market_info_summary = QLabel("Market details will update with ticker, candle, and order book context.")
        self.market_info_summary.setWordWrap(True)
        self.market_info_summary.setStyleSheet(
            "color: #ecf2f8; background-color: #171d29; border: 1px solid #273142; "
            "border-radius: 12px; padding: 12px; font-size: 12px; font-weight: 600;"
        )
        info_tab_layout.addWidget(self.market_info_summary)

        metrics_widget = QWidget()
        metrics_layout = QGridLayout(metrics_widget)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setHorizontalSpacing(10)
        metrics_layout.setVerticalSpacing(10)
        self.market_info_cards = {}
        for index, key in enumerate(
            ["Last", "Mid", "Spread", "Best Bid", "Best Ask", "Range", "Visible Vol", "Depth Bias"]
        ):
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background-color: #171d29; border: 1px solid #273142; border-radius: 12px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            title = QLabel(key)
            title.setStyleSheet("color: #8e9bab; font-size: 12px;")
            value = QLabel("-")
            value.setStyleSheet("color: #f6f8fb; font-size: 16px; font-weight: 700;")
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            metrics_layout.addWidget(card, index // 4, index % 4)
            self.market_info_cards[key] = value
        info_tab_layout.addWidget(metrics_widget)

        self.market_info_details = QTextBrowser()
        self.market_info_details.setStyleSheet(
            "QTextBrowser { background-color: #171d29; color: #dde5ef; border: 1px solid #273142; border-radius: 12px; padding: 12px; }"
        )
        info_tab_layout.addWidget(self.market_info_details, 1)
        self.market_tabs.addTab(self.market_info_page, "Market Info")

        self._style_plot(self.price_plot, right_label="Price", show_bottom=False)
        self._style_plot(self.volume_plot, left_label="Volume", show_bottom=False)
        self._style_plot(self.heatmap_plot, left_label="Orderbook", bottom_label="Time", show_bottom=True)

        self.v_line = InfiniteLine(angle=90, movable=False, pen=mkPen((142, 164, 196, 90), width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.h_line = InfiniteLine(angle=0, movable=False, pen=mkPen((142, 164, 196, 90), width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.price_plot.addItem(self.v_line, ignoreBounds=True)
        self.price_plot.addItem(self.h_line, ignoreBounds=True)

        # Live price lines
        self.bid_line = InfiniteLine(
            angle=0,
            movable=False,
            pen=mkPen("#26a69a", width=1, style=QtCore.Qt.PenStyle.DashLine),
            label="Bid {value:.6f}",
            labelOpts={"position": 0.98, "color": "#26a69a", "fill": (11, 18, 32, 160)},
        )
        self.ask_line = InfiniteLine(
            angle=0,
            movable=False,
            pen=mkPen("#ef5350", width=1, style=QtCore.Qt.PenStyle.DashLine),
            label="Ask {value:.6f}",
            labelOpts={"position": 0.98, "color": "#ef5350", "fill": (11, 18, 32, 160)},
        )
        self.last_line = InfiniteLine(
            angle=0,
            movable=False,
            pen=mkPen("#32d296", width=1.15),
            label="{value:.6f}",
            labelOpts={"position": 0.98, "color": "#ffffff", "fill": (50, 210, 150, 205)},
        )

        for line in (self.bid_line, self.ask_line, self.last_line):
            line.setVisible(False)
            self.price_plot.addItem(line, ignoreBounds=True)

        self.trade_entry_line = self._create_trade_overlay_line("#2a7fff", "Entry {value:.6f}", "entry")
        self.trade_stop_line = self._create_trade_overlay_line("#ef5350", "SL {value:.6f}", "stop_loss")
        self.trade_take_line = self._create_trade_overlay_line("#32d296", "TP {value:.6f}", "take_profit")

        self.text_item = TextItem(
            html="",
            anchor=(0.0, 1.0),
            border=mkPen((76, 92, 115, 210)),
            fill=pg.mkBrush(23, 29, 41, 238),
        )
        self.price_plot.addItem(self.text_item)

        self.news_hover_item = TextItem(
            html="",
            anchor=(0.0, 1.0),
            border=mkPen((244, 162, 97, 180), width=1),
            fill=pg.mkBrush(23, 29, 41, 240),
        )
        self.news_hover_item.setZValue(20)
        self.news_hover_item.setVisible(False)
        self.price_plot.addItem(self.news_hover_item)

        self.watermark_item = TextItem(
            html="",
            anchor=(0.5, 0.5),
            border=None,
            fill=None,
        )
        self.watermark_item.setZValue(-10)
        self.price_plot.addItem(self.watermark_item)
        self.price_plot.getPlotItem().vb.sigRangeChanged.connect(self._update_watermark_position)

        self.proxy = SignalProxy(self.price_plot.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved)
        self.price_plot.scene().sigMouseClicked.connect(self._mouse_clicked)
        self.price_plot.scene().sigMouseClicked.connect(self._mouse_clicked)

        self.splitter.setStretchFactor(0, 8)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setSizes([720, 170, 170])

        self._update_chart_header()
        self._refresh_market_panels()
        self._update_watermark_html()

    def _style_plot(self, plot, left_label=None, right_label=None, bottom_label=None, show_bottom=False):
        plot.setBackground(self.chart_background)
        plot.showGrid(x=True, y=True, alpha=0.16)
        plot.setMenuEnabled(False)
        plot.hideButtons()

        item = plot.getPlotItem()
        item.layout.setContentsMargins(6, 6, 10, 6)

        if left_label:
            plot.setLabel("left", left_label)
        if right_label:
            plot.setLabel("right", right_label)
        if bottom_label:
            plot.setLabel("bottom", bottom_label)

        axis_names = ("left", "right", "bottom", "top")
        for axis_name in axis_names:
            axis = item.getAxis(axis_name)
            axis.setTextPen(pg.mkColor(self.axis_color))
            axis.setPen(pg.mkPen(self.axis_color, width=1))
            axis.setStyle(tickLength=-6, autoExpandTextSpace=False)
            try:
                axis.setGrid(48)
            except Exception:
                pass

        plot.showAxis("bottom") if show_bottom else plot.hideAxis("bottom")
        if right_label:
            plot.showAxis("right")

        item.vb.setBackgroundColor(pg.mkColor(self.chart_background))

    def _create_indicator_pane(self, key: str, label: str):
        existing = self.indicator_panes.get(key)
        if existing is not None:
            return existing

        axis = DateAxisItem(orientation="bottom")
        pane = PlotWidget(axisItems={"bottom": axis})
        pane.setXLink(self.price_plot)
        pane.hideAxis("right")
        pane.setMinimumHeight(120)
        self._style_plot(pane, left_label=label, show_bottom=False)
        self.splitter.insertWidget(max(self.splitter.count() - 1, 1), pane)
        self.indicator_panes[key] = pane

        current_sizes = self.splitter.sizes()
        if len(current_sizes) >= self.splitter.count():
            current_sizes.insert(max(len(current_sizes) - 1, 1), 130)
            self.splitter.setSizes(current_sizes[: self.splitter.count()])
        return pane

    def _create_curve(self, plot, color: str, width: float = 1.4, style=None):
        pen = mkPen(color, width=width)
        if style is not None:
            pen.setStyle(style)
        return plot.plot(pen=pen)

    def _create_histogram(self, plot, brush="#5c6bc0"):
        item = pg.BarGraphItem(x=[], height=[], width=1.0, y0=0, brush=brush)
        plot.addItem(item)
        return item

    def _set_histogram_data(self, item, x, values, width, brushes=None):
        if brushes is None:
            item.setOpts(x=x, height=values, width=width, y0=0)
        else:
            item.setOpts(x=x, height=values, width=width, y0=0, brushes=brushes)

    def _add_reference_line(self, plot, y_value: float, color: str = "#5d6d8a"):
        line = InfiniteLine(
            angle=0,
            movable=False,
            pen=mkPen(color, width=1, style=QtCore.Qt.PenStyle.DashLine),
        )
        line.setPos(y_value)
        plot.addItem(line, ignoreBounds=True)
        return line

    def _create_trade_overlay_line(self, color: str, label: str, level: str):
        line = InfiniteLine(
            angle=0,
            movable=True,
            pen=mkPen(color, width=1.35, style=QtCore.Qt.PenStyle.DashLine),
            label=label,
            labelOpts={"position": 0.98, "color": color, "fill": (11, 18, 32, 185)},
        )
        line.setVisible(False)
        line._trade_level = level
        line.sigPositionChangeFinished.connect(lambda item=line: self._handle_trade_line_moved(item))
        self.price_plot.addItem(line, ignoreBounds=True)
        return line

    def _handle_trade_line_moved(self, line):
        if self._trade_overlay_updating:
            return
        try:
            price = float(line.value())
        except Exception:
            return
        if not np.isfinite(price) or price <= 0:
            return
        level = getattr(line, "_trade_level", "")
        if not level:
            return
        self._trade_overlay_state[level] = price
        self.sigTradeLevelChanged.emit(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "level": level,
                "price": price,
            }
        )

    def set_trade_overlay(self, entry=None, stop_loss=None, take_profit=None, side="buy"):
        self._trade_overlay_updating = True
        try:
            normalized_side = str(side or "buy").strip().lower() or "buy"
            self._trade_overlay_state = {
                "side": normalized_side,
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }

            entry_color = "#32d296" if normalized_side == "buy" else "#ef5350"
            self.trade_entry_line.setPen(mkPen(entry_color, width=1.4, style=QtCore.Qt.PenStyle.DashLine))
            self.trade_entry_line.label.fill = pg.mkBrush(pg.mkColor(entry_color))
            self.trade_entry_line.label.setColor(pg.mkColor("#ffffff"))

            for line, value in (
                (self.trade_entry_line, entry),
                (self.trade_stop_line, stop_loss),
                (self.trade_take_line, take_profit),
            ):
                numeric = None
                try:
                    if value not in (None, ""):
                        numeric = float(value)
                except Exception:
                    numeric = None
                if numeric is not None and np.isfinite(numeric) and numeric > 0:
                    line.setPos(numeric)
                    line.setVisible(True)
                else:
                    line.setVisible(False)
        finally:
            self._trade_overlay_updating = False

    def clear_trade_overlay(self):
        self.set_trade_overlay(
            entry=None,
            stop_loss=None,
            take_profit=None,
            side=self._trade_overlay_state.get("side", "buy"),
        )

    def _sync_view_context(self):
        context = (self.symbol, self.timeframe)
        if context != self._last_view_context:
            self._last_view_context = context
            self._auto_fit_pending = True
            self.heatmap_buffer.clear()
            self._last_heatmap_price_range = None
            self.heatmap_image.clear()
            self._last_orderbook_bids = []
            self._last_orderbook_asks = []
            self.depth_bid_curve.setData([], [])
            self.depth_ask_curve.setData([], [])
            self.depth_summary_label.setText("Depth chart will populate when live order book data arrives.")

    def _should_fit_chart_view(self, x):
        if self._auto_fit_pending:
            return True

        if x is None or len(x) == 0:
            return False

        try:
            x_range, _y_range = self.price_plot.viewRange()
        except Exception:
            return True

        if len(x_range) < 2 or not np.isfinite(x_range[0]) or not np.isfinite(x_range[1]):
            return True

        min_x = float(x[0])
        max_x = float(x[-1])
        visible_span = float(x_range[1]) - float(x_range[0])
        full_span = max(max_x - min_x, 1e-9)

        if visible_span <= 0:
            return True

        if float(x_range[1]) < min_x or float(x_range[0]) > max_x:
            return True

        # If the viewport is effectively the entire history, fit to a more useful recent window.
        if visible_span >= full_span * 0.98:
            return True

        return False

    def _visible_slice_start(self, x):
        if x is None or len(x) == 0:
            return 0
        visible_bars = min(len(x), self.default_visible_bars)
        return max(0, len(x) - visible_bars)

    def _build_candle_stats(self, df, x):
        if df is None or len(df) == 0 or x is None or len(x) == 0:
            return None

        start_index = self._visible_slice_start(x)
        visible = df.iloc[start_index:].copy()
        if visible.empty:
            return None

        open_values = visible["open"].astype(float).to_numpy()
        high_values = visible["high"].astype(float).to_numpy()
        low_values = visible["low"].astype(float).to_numpy()
        close_values = visible["close"].astype(float).to_numpy()
        volume_values = visible["volume"].astype(float).to_numpy()
        visible_x = np.asarray(x[start_index:], dtype=float)

        finite_high = high_values[np.isfinite(high_values)]
        finite_low = low_values[np.isfinite(low_values)]
        finite_close = close_values[np.isfinite(close_values)]
        finite_volume = volume_values[np.isfinite(volume_values)]

        if len(finite_high) == 0 or len(finite_low) == 0 or len(finite_close) == 0:
            return None

        first_open = float(open_values[0])
        last_close = float(close_values[-1])
        variation = ((last_close - first_open) / first_open * 100.0) if abs(first_open) > 1e-12 else 0.0

        return {
            "start_index": start_index,
            "x": visible_x,
            "min_price": float(np.min(finite_low)),
            "max_price": float(np.max(finite_high)),
            "max_volume": float(np.max(finite_volume)) if len(finite_volume) else 0.0,
            "average_close": float(np.mean(finite_close)),
            "cumulative_volume": float(np.sum(finite_volume)) if len(finite_volume) else 0.0,
            "last_price": last_close,
            "variation_pct": variation,
        }

    def _fit_chart_view(self, stats, width):
        if not stats:
            return

        visible_x = np.asarray(stats["x"], dtype=float)
        if len(visible_x) == 0:
            return

        min_x = float(visible_x[0] - (width * 2.0))
        max_x = float(visible_x[-1] + (width * 2.0))
        min_y = float(stats["min_price"])
        max_y = float(stats["max_price"])
        y_span = max(max_y - min_y, max(abs(max_y) * 0.02, 1e-9))
        y_pad = y_span * 0.10

        price_vb = self.price_plot.getPlotItem().vb
        price_vb.enableAutoRange(x=False, y=False)
        price_vb.setXRange(min_x, max_x, padding=0.0)
        price_vb.setYRange(min_y - y_pad, max_y + y_pad, padding=0.0)

        volume_vb = self.volume_plot.getPlotItem().vb
        volume_vb.enableAutoRange(x=False, y=False)
        volume_vb.setYRange(0.0, max(float(stats["max_volume"]) * 1.15, 1.0), padding=0.0)

        self._auto_fit_pending = False

    def _mouse_moved(self, evt):
        pos = evt[0]
        if not self.price_plot.sceneBoundingRect().contains(pos):
            self.news_hover_item.setVisible(False)
            return

        mouse_point = self.price_plot.getPlotItem().vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()

        self.v_line.setPos(x)
        self.h_line.setPos(y)
        row = self._row_for_x(x)
        self.text_item.setHtml(self._hover_html(row, y))
        self.text_item.setPos(x, y)
        self._update_ohlcv_for_x(x)
        self._update_news_hover(x, y)

    def _update_news_hover(self, x_value, y_value):
        event = self._nearest_news_event(x_value, y_value)
        if event is None:
            self.news_hover_item.setVisible(False)
            return

        self.news_hover_item.setHtml(self._news_hover_html(event))
        self.news_hover_item.setPos(float(event["x"]), float(event["y"]))
        self.news_hover_item.setVisible(True)

    def _nearest_news_event(self, x_value, y_value):
        events = list(self._visible_news_events or [])
        if not events:
            return None

        try:
            x_range, y_range = self.price_plot.viewRange()
        except Exception:
            return None

        x_span = abs(float(x_range[1]) - float(x_range[0])) if len(x_range) >= 2 else 0.0
        y_span = abs(float(y_range[1]) - float(y_range[0])) if len(y_range) >= 2 else 0.0
        x_threshold = max(x_span * 0.02, 60.0)
        y_threshold = max(y_span * 0.06, 1e-6)

        closest = None
        closest_score = None
        for event in events:
            dx = abs(float(event.get("x", 0.0)) - float(x_value))
            dy = abs(float(event.get("y", 0.0)) - float(y_value))
            if dx > x_threshold or dy > y_threshold:
                continue
            score = dx + (dy * 0.5)
            if closest is None or score < closest_score:
                closest = event
                closest_score = score
        return closest

    def _news_hover_html(self, event):
        headline = str(event.get("headline") or "News event")
        source = str(event.get("source") or "News Feed")
        summary = str(event.get("summary") or "").strip()
        impact = str(event.get("impact") or "-")
        sentiment = str(event.get("sentiment") or "-")
        time_text = str(event.get("time") or "")
        summary_html = ""
        if summary:
            trimmed = summary[:180] + ("..." if len(summary) > 180 else "")
            summary_html = (
                f"<div style='color: #d7e8ff; font-size: 10px; margin-top: 3px;'>"
                f"{html.escape(trimmed)}</div>"
            )
        return (
            "<div style='padding: 6px 8px;'>"
            f"<div style='color: #ffd166; font-size: 10px; font-weight: 700;'>{html.escape(source)} | {html.escape(time_text)}</div>"
            f"<div style='color: #f8fbff; font-size: 11px; font-weight: 700; margin-top: 2px;'>{html.escape(headline)}</div>"
            f"{summary_html}"
            f"<div style='color: #9ec1ff; font-size: 10px; margin-top: 3px;'>Impact {html.escape(impact)} | Sentiment {html.escape(sentiment)}</div>"
            "</div>"
        )

    def _mouse_clicked(self, event):
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self._show_trade_context_menu(event)
            return
        try:
            is_double = bool(event.double())
        except Exception:
            is_double = False
        if not is_double:
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        pos = event.scenePos()
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return

        mouse_point = self.price_plot.getPlotItem().vb.mapSceneToView(pos)
        price = float(mouse_point.y())
        if not np.isfinite(price) or price <= 0:
            return

        self.sigTradeLevelRequested.emit(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "price": price,
                "x": float(mouse_point.x()),
            }
        )
        try:
            event.accept()
        except Exception:
            pass

    def _show_trade_context_menu(self, event):
        pos = event.scenePos()
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return

        mouse_point = self.price_plot.getPlotItem().vb.mapSceneToView(pos)
        price = float(mouse_point.y())
        if not np.isfinite(price) or price <= 0:
            return

        menu = QMenu(self)
        buy_limit = menu.addAction("Buy Limit Here")
        sell_limit = menu.addAction("Sell Limit Here")
        menu.addSeparator()
        set_entry = menu.addAction("Set Entry Here")
        set_stop = menu.addAction("Set Stop Loss Here")
        set_take = menu.addAction("Set Take Profit Here")
        menu.addSeparator()
        clear_levels = menu.addAction("Clear Trade Levels")
        chosen = menu.exec(event.screenPos().toPoint())
        if chosen is None:
            return

        mapping = {
            buy_limit: "buy_limit",
            sell_limit: "sell_limit",
            set_entry: "set_entry",
            set_stop: "set_stop_loss",
            set_take: "set_take_profit",
            clear_levels: "clear_levels",
        }
        action_name = mapping.get(chosen)
        if not action_name:
            return

        self.sigTradeContextAction.emit(
            {
                "action": action_name,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "price": price,
            }
        )
        try:
            event.accept()
        except Exception:
            pass

    def _active_broker_name(self):
        broker = getattr(self.controller, "broker", None)
        if broker is not None:
            name = getattr(broker, "exchange_name", None)
            if name:
                return str(name)

        config = getattr(self.controller, "config", None)
        broker_config = getattr(config, "broker", None)
        if broker_config is not None:
            exchange = getattr(broker_config, "exchange", None)
            if exchange:
                return str(exchange)

        return "Broker"

    def _symbol_parts(self):
        if "/" not in str(self.symbol):
            return str(self.symbol).upper(), ""
        base, quote = str(self.symbol).upper().split("/", 1)
        return base, quote

    def _timeframe_description(self):
        mapping = {
            "1m": "1 minute chart",
            "5m": "5 minute chart",
            "15m": "15 minute chart",
            "30m": "30 minute chart",
            "1h": "1 hour chart",
            "4h": "4 hour chart",
            "1d": "1 day chart",
            "1w": "1 week chart",
            "1mn": "1 month chart",
        }
        return mapping.get(str(self.timeframe).lower(), f"{self.timeframe} chart")

    def _update_chart_header(self):
        base, quote = self._symbol_parts()
        broker_name = self._active_broker_name().upper()
        self.instrument_label.setText(f"{self.symbol.upper()}  {self.timeframe.upper()}")

        stats = self._last_candle_stats or {}
        if quote:
            description = f"{broker_name}  |  {base} quoted in {quote}"
        else:
            description = f"{broker_name}  |  {self._timeframe_description()}"

        bid = self._format_numeric_value(self._last_bid)
        ask = self._format_numeric_value(self._last_ask)
        spread = None
        if bid is not None and ask is not None and ask >= bid:
            spread = ask - bid

        if stats:
            last_price = self._format_metric(stats.get("last_price", 0.0))
            variation = float(stats.get("variation_pct", 0.0))
            cumulative_volume = self._format_volume(stats.get("cumulative_volume", 0.0))
            positive = variation >= 0
            change_color = "#2db784" if positive else "#d75462"
            prefix = "+" if positive else ""
            self.market_stats_label.setText(f"{last_price}  {prefix}{variation:.2f}%")
            self.market_stats_label.setStyleSheet(
                f"color: {change_color}; font-weight: 800; font-size: 15px;"
            )
            self.market_meta_label.setText(
                f"{description}  |  Avg {self._format_metric(stats.get('average_close', 0.0))}  |  "
                f"Range {self._format_metric(stats.get('min_price', 0.0), 4)} - {self._format_metric(stats.get('max_price', 0.0), 4)}"
            )
            self.market_micro_label.setText(
                f"Bid {self._format_metric(bid, 8)}  |  Ask {self._format_metric(ask, 8)}  |  "
                f"Spread {self._format_metric(spread, 8)}  |  Visible Vol {cumulative_volume}"
            )
        else:
            self.market_stats_label.setText(self._timeframe_description())
            self.market_stats_label.setStyleSheet("color: #8e9bab; font-weight: 700; font-size: 14px;")
            self.market_meta_label.setText(description)
            self.market_micro_label.setText(
                f"Bid {self._format_metric(bid, 8)}  |  Ask {self._format_metric(ask, 8)}  |  Spread {self._format_metric(spread, 8)}"
            )

    def _update_watermark_html(self):
        base, quote = self._symbol_parts()
        description = f"{base} / {quote}" if quote else base
        self.watermark_item.setHtml(
            (
                "<div style='text-align:center;'>"
                f"<div style='color: rgba(246,248,251,0.08); font-size: 40px; font-weight: 800; letter-spacing: 1px;'>{self.symbol.upper()}</div>"
                f"<div style='color: rgba(154,164,178,0.10); font-size: 22px; font-weight: 700;'>{self.timeframe.upper()}</div>"
                f"<div style='color: rgba(114,129,152,0.12); font-size: 11px; text-transform: uppercase;'>{description}</div>"
                "</div>"
            )
        )

    def refresh_context_display(self):
        self._update_chart_header()
        self._refresh_market_panels()
        self._update_watermark_html()
        self._update_watermark_position()

    def _refresh_market_panels(self):
        self._update_depth_chart()
        self._update_market_info()

    def _update_depth_chart(self):
        bids = []
        asks = []
        for level in self._last_orderbook_bids or []:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price = self._format_numeric_value(level[0])
                size = self._format_numeric_value(level[1])
                if price is not None and size is not None and price > 0 and size > 0:
                    bids.append((price, size))
        for level in self._last_orderbook_asks or []:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price = self._format_numeric_value(level[0])
                size = self._format_numeric_value(level[1])
                if price is not None and size is not None and price > 0 and size > 0:
                    asks.append((price, size))

        if not bids and not asks:
            self.depth_bid_curve.setData([], [])
            self.depth_ask_curve.setData([], [])
            return

        if bids:
            bids = sorted(bids, key=lambda item: item[0], reverse=True)
            bid_prices = np.array([price for price, _size in bids], dtype=float)
            bid_sizes = np.cumsum(np.array([size for _price, size in bids], dtype=float))
            self.depth_bid_curve.setData(bid_prices, bid_sizes)
        else:
            self.depth_bid_curve.setData([], [])

        if asks:
            asks = sorted(asks, key=lambda item: item[0])
            ask_prices = np.array([price for price, _size in asks], dtype=float)
            ask_sizes = np.cumsum(np.array([size for _price, size in asks], dtype=float))
            self.depth_ask_curve.setData(ask_prices, ask_sizes)
        else:
            self.depth_ask_curve.setData([], [])

        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None
        spread_text = "-"
        if best_bid is not None and best_ask is not None and best_ask >= best_bid:
            spread_text = self._format_metric(best_ask - best_bid, 8)
        self.depth_summary_label.setText(
            f"Best bid {self._format_metric(best_bid, 8)} | Best ask {self._format_metric(best_ask, 8)} | Spread {spread_text}"
        )

    def _update_market_info(self):
        stats = self._last_candle_stats or {}
        bid = self._format_numeric_value(self._last_bid)
        ask = self._format_numeric_value(self._last_ask)
        last_price = self._format_numeric_value(stats.get("last_price")) if stats else None
        if last_price is None:
            if bid is not None and ask is not None:
                last_price = (bid + ask) / 2.0
            else:
                last_price = bid or ask

        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        spread = None
        if bid is not None and ask is not None and ask >= bid:
            spread = ask - bid

        bid_depth = sum(max(0.0, self._format_numeric_value(level[1]) or 0.0) for level in self._last_orderbook_bids or [] if isinstance(level, (list, tuple)) and len(level) >= 2)
        ask_depth = sum(max(0.0, self._format_numeric_value(level[1]) or 0.0) for level in self._last_orderbook_asks or [] if isinstance(level, (list, tuple)) and len(level) >= 2)
        depth_bias = None
        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            depth_bias = ((bid_depth - ask_depth) / total_depth) * 100.0

        range_text = "-"
        if stats:
            range_text = (
                f"{self._format_metric(stats.get('min_price'), 6)} - "
                f"{self._format_metric(stats.get('max_price'), 6)}"
            )

        card_values = {
            "Last": self._format_metric(last_price, 8),
            "Mid": self._format_metric(mid, 8),
            "Spread": self._format_metric(spread, 8),
            "Best Bid": self._format_metric(bid, 8),
            "Best Ask": self._format_metric(ask, 8),
            "Range": range_text,
            "Visible Vol": self._format_volume(stats.get("cumulative_volume", 0.0)) if stats else "-",
            "Depth Bias": "-" if depth_bias is None else f"{depth_bias:+.2f}%",
        }
        for key, value_label in self.market_info_cards.items():
            value_label.setText(card_values.get(key, "-"))

        base, quote = self._symbol_parts()
        headline = f"{self.symbol.upper()} on {self._active_broker_name().upper()} | {self.timeframe.upper()} context"
        if stats and stats.get("variation_pct") is not None:
            headline += f" | Visible move {float(stats.get('variation_pct') or 0.0):+.2f}%"
        self.market_info_summary.setText(headline)

        detail_lines = [
            f"<h3>{self.symbol.upper()}</h3>",
            (
                f"<p><b>Market structure:</b> {base} / {quote if quote else 'quote unavailable'} | "
                f"<b>Broker:</b> {self._active_broker_name().upper()} | "
                f"<b>Timeframe:</b> {self.timeframe.upper()}</p>"
            ),
            (
                f"<p><b>Visible range:</b> {range_text} | "
                f"<b>Average close:</b> {self._format_metric(stats.get('average_close'), 8) if stats else '-'} | "
                f"<b>Visible volume:</b> {self._format_volume(stats.get('cumulative_volume', 0.0)) if stats else '-'}</p>"
            ),
            (
                f"<p><b>Order book:</b> bid depth {self._format_volume(bid_depth)} | "
                f"ask depth {self._format_volume(ask_depth)} | "
                f"spread {self._format_metric(spread, 8)} | "
                f"mid {self._format_metric(mid, 8)}</p>"
            ),
        ]
        if depth_bias is not None:
            tilt = "buyers" if depth_bias > 0 else "sellers" if depth_bias < 0 else "balanced flow"
            detail_lines.append(
                f"<p><b>Depth tilt:</b> {tilt} with a {depth_bias:+.2f}% balance versus the opposing side.</p>"
            )
        self.market_info_details.setHtml("".join(detail_lines))

    def _format_numeric_value(self, value):
        try:
            numeric = float(value)
        except Exception:
            return None
        if not np.isfinite(numeric):
            return None
        return numeric

    def _update_watermark_position(self, *_args):
        try:
            x_range, y_range = self.price_plot.viewRange()
            center_x = (float(x_range[0]) + float(x_range[1])) / 2.0
            center_y = (float(y_range[0]) + float(y_range[1])) / 2.0
            self.watermark_item.setPos(center_x, center_y)
            self._watermark_initialized = True
        except Exception:
            return

    def _format_metric(self, value, digits=6):
        try:
            numeric = float(value)
        except Exception:
            return "-"
        if abs(numeric) >= 1000:
            return f"{numeric:,.2f}"
        if abs(numeric) >= 1:
            return f"{numeric:,.{min(digits, 4)}f}"
        return f"{numeric:,.{digits}f}"

    def _format_volume(self, value):
        try:
            numeric = float(value)
        except Exception:
            return "-"
        if numeric >= 1_000_000_000:
            return f"{numeric / 1_000_000_000:.2f}B"
        if numeric >= 1_000_000:
            return f"{numeric / 1_000_000:.2f}M"
        if numeric >= 1_000:
            return f"{numeric / 1_000:.2f}K"
        return f"{numeric:.2f}"

    def _format_time_label(self, value):
        if value in (None, ""):
            return "-"

        try:
            if hasattr(value, "to_pydatetime"):
                dt = value.to_pydatetime()
            elif isinstance(value, datetime):
                dt = value
            elif isinstance(value, (int, float, np.integer, np.floating)):
                numeric = float(value)
                if abs(numeric) > 1e11:
                    numeric = numeric / 1000.0
                dt = datetime.fromtimestamp(numeric, tz=timezone.utc)
            else:
                text = str(value).strip()
                if not text:
                    return "-"
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return str(value)

    def _set_ohlcv_from_row(self, row):
        if row is None:
            self.ohlcv_label.setText("Time -  O -  H -  L -  C -  Chg -  V -")
            return

        open_price = self._format_numeric_value(row.get("open", 0.0))
        close_price = self._format_numeric_value(row.get("close", 0.0))
        delta = None
        if open_price is not None and close_price is not None:
            delta = close_price - open_price
        prefix = "+" if delta is not None and delta >= 0 else ""
        self.ohlcv_label.setText(
            "  ".join(
                [
                    f"T {self._format_time_label(row.get('timestamp'))}",
                    f"O {self._format_metric(row.get('open', 0.0))}",
                    f"H {self._format_metric(row.get('high', 0.0))}",
                    f"L {self._format_metric(row.get('low', 0.0))}",
                    f"C {self._format_metric(row.get('close', 0.0))}",
                    f"Chg {prefix}{self._format_metric(delta, 6)}",
                    f"V {self._format_volume(row.get('volume', 0.0))}",
                ]
            )
        )

    def _row_for_x(self, x_value):
        if self._last_df is None or self._last_x is None or len(self._last_x) == 0:
            return None

        try:
            index = int(np.nanargmin(np.abs(self._last_x - float(x_value))))
        except Exception:
            index = len(self._last_df) - 1

        if index < 0 or index >= len(self._last_df):
            return None
        return self._last_df.iloc[index]

    def _hover_html(self, row, y_value):
        if row is None:
            return f"<span style='color:#f6f8fb'>Price {y_value:.6f}</span>"

        open_price = self._format_numeric_value(row.get("open", 0.0))
        close_price = self._format_numeric_value(row.get("close", 0.0))
        delta = None
        if open_price is not None and close_price is not None:
            delta = close_price - open_price
        delta_color = "#2db784" if (delta or 0.0) >= 0 else "#d75462"
        delta_prefix = "+" if delta is not None and delta >= 0 else ""
        return (
            "<div style='padding: 6px 8px;'>"
            f"<div style='color: #9aa4b2; font-size: 10px; font-weight: 700;'>{html.escape(self._format_time_label(row.get('timestamp')))}</div>"
            f"<div style='color: #f6f8fb; font-size: 11px; margin-top: 2px;'>Cursor {y_value:.6f}</div>"
            f"<div style='color: #dde5ef; font-size: 10px; margin-top: 3px;'>"
            f"O {self._format_metric(row.get('open', 0.0))}  "
            f"H {self._format_metric(row.get('high', 0.0))}  "
            f"L {self._format_metric(row.get('low', 0.0))}  "
            f"C {self._format_metric(row.get('close', 0.0))}</div>"
            f"<div style='color: {delta_color}; font-size: 10px; font-weight: 700; margin-top: 3px;'>"
            f"Bar change {delta_prefix}{self._format_metric(delta, 6)}  |  Volume {self._format_volume(row.get('volume', 0.0))}</div>"
            "</div>"
        )

    def _update_ohlcv_for_x(self, x_value):
        self._set_ohlcv_from_row(self._row_for_x(x_value))

    def _extract_time_axis(self, df):
        if "timestamp" not in df.columns:
            return np.arange(len(df), dtype=float)

        ts = df["timestamp"]

        try:
            import pandas as pd

            # Numeric epoch input
            if pd.api.types.is_numeric_dtype(ts):
                x = pd.to_numeric(ts, errors="coerce").to_numpy(dtype=float)
                if len(x) > 0:
                    median = np.nanmedian(np.abs(x))
                    if median > 1e11:  # likely milliseconds
                        x = x / 1000.0
                return x

            dt = pd.to_datetime(ts, errors="coerce", utc=True)
            x = (dt.astype("int64") / 1e9).to_numpy(dtype=float)
            if np.isnan(x).all():
                return np.arange(len(df), dtype=float)
            return x
        except Exception:
            return np.arange(len(df), dtype=float)

    def _infer_candle_width(self, x):
        if len(x) < 2:
            return 60.0

        diffs = np.diff(x)
        diffs = diffs[np.isfinite(diffs)]
        diffs = diffs[np.abs(diffs) > 0]
        if len(diffs) == 0:
            return 60.0

        step = float(np.median(np.abs(diffs)))
        return max(min(step * 0.64, step * 0.8), 1e-6)

    def _resolve_signal_x(self, index):
        try:
            numeric = float(index)
        except Exception:
            numeric = None

        if numeric is not None and np.isfinite(numeric):
            if self._last_x is not None and len(self._last_x) > 0:
                rounded = int(round(numeric))
                if abs(numeric - rounded) <= 1e-6 and 0 <= rounded < len(self._last_x):
                    return float(self._last_x[rounded])
            return numeric

        timestamp_text = str(index or "").strip()
        if not timestamp_text:
            return None

        try:
            import pandas as pd

            parsed = pd.to_datetime(timestamp_text, errors="coerce", utc=True)
            if pd.isna(parsed):
                return None
            return float(parsed.timestamp())
        except Exception:
            return None

    def update_orderbook_heatmap(self, bids, asks):
        self._last_orderbook_bids = list(bids or [])
        self._last_orderbook_asks = list(asks or [])
        self._refresh_market_panels()
        if not bids and not asks:
            return

        parsed_levels = []
        for level in (bids or [])[: self.max_heatmap_levels]:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                try:
                    price = float(level[0])
                    volume = float(level[1])
                    if np.isfinite(price) and np.isfinite(volume) and volume > 0:
                        parsed_levels.append((price, volume))
                except Exception:
                    continue

        for level in (asks or [])[: self.max_heatmap_levels]:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                try:
                    price = float(level[0])
                    volume = float(level[1])
                    if np.isfinite(price) and np.isfinite(volume) and volume > 0:
                        parsed_levels.append((price, volume))
                except Exception:
                    continue

        if not parsed_levels:
            return

        prices = np.array([price for price, _volume in parsed_levels], dtype=float)
        volumes = np.array([volume for _price, volume in parsed_levels], dtype=float)

        price_min = float(np.min(prices))
        price_max = float(np.max(prices))

        last_close = None
        if self._last_df is not None and not self._last_df.empty and "close" in self._last_df.columns:
            try:
                last_close = float(self._last_df["close"].iloc[-1])
            except Exception:
                last_close = None

        raw_span = max(price_max - price_min, 1e-9)
        anchor_price = last_close if last_close is not None and np.isfinite(last_close) else float(np.mean(prices))
        padding = max(raw_span * 0.2, abs(anchor_price) * 0.0015, 1e-6)
        grid_min = min(price_min, anchor_price - padding)
        grid_max = max(price_max, anchor_price + padding)

        previous_range = self._last_heatmap_price_range
        if previous_range is not None:
            prev_min, prev_max = previous_range
            grid_min = min(grid_min, float(prev_min))
            grid_max = max(grid_max, float(prev_max))
        self._last_heatmap_price_range = (grid_min, grid_max)

        if not np.isfinite(grid_min) or not np.isfinite(grid_max) or grid_max <= grid_min:
            return

        price_axis = np.linspace(grid_min, grid_max, self.max_heatmap_levels)
        column = np.zeros(self.max_heatmap_levels, dtype=float)
        for price, volume in parsed_levels:
            index = int(np.searchsorted(price_axis, price, side="left"))
            index = max(0, min(self.max_heatmap_levels - 1, index))
            column[index] += volume

        column_max = float(np.max(column))
        if column_max > 0:
            column /= column_max

        self.heatmap_buffer.append(column)
        if len(self.heatmap_buffer) > self.max_heatmap_rows:
            self.heatmap_buffer.pop(0)

        matrix = np.array(self.heatmap_buffer, dtype=float).T
        if matrix.size == 0:
            return

        matrix_max = float(np.nanmax(matrix))
        if matrix_max > 0:
            matrix = matrix / matrix_max

        if self._last_x is not None and len(self._last_x) >= 2:
            diffs = np.diff(self._last_x)
            diffs = diffs[np.isfinite(diffs)]
            diffs = diffs[np.abs(diffs) > 0]
            step = float(np.median(np.abs(diffs))) if len(diffs) else 60.0
            x_end = float(self._last_x[-1]) + (step * 0.5)
        elif self._last_x is not None and len(self._last_x) == 1:
            step = 60.0
            x_end = float(self._last_x[-1]) + (step * 0.5)
        else:
            step = 1.0
            x_end = float(matrix.shape[1])

        x_start = x_end - (step * matrix.shape[1])
        rect = QtCore.QRectF(
            x_start,
            grid_min,
            max(step * matrix.shape[1], 1e-6),
            max(grid_max - grid_min, 1e-9),
        )

        self.heatmap_image.setImage(np.flipud(matrix), autoLevels=False, levels=(0.0, 1.0))
        self.heatmap_image.setRect(rect)
        self.heatmap_plot.setYRange(grid_min, grid_max, padding=0.02)

    def add_strategy_signal(self, index, price, signal):
        x_value = self._resolve_signal_x(index)
        try:
            y_value = float(price)
        except Exception:
            return

        if x_value is None or not np.isfinite(y_value):
            return

        normalized_signal = str(signal or "").strip().upper()
        if normalized_signal == "BUY":
            self.signal_markers.addPoints(x=[x_value], y=[y_value], symbol="t1", brush="#26a69a", size=12)
        elif normalized_signal == "SELL":
            self.signal_markers.addPoints(x=[x_value], y=[y_value], symbol="t", brush="#ef5350", size=12)

    def clear_news_events(self):
        self._news_events = []
        self._visible_news_events = []
        self.news_markers.setData([], [])
        self.news_hover_item.setVisible(False)
        for item in list(self._news_items):
            try:
                self.price_plot.removeItem(item)
            except Exception:
                pass
        self._news_items = []

    def set_news_events(self, events):
        self._news_events = list(events or [])
        self._render_news_events()

    def _render_news_events(self):
        self.news_markers.setData([], [])
        self.news_hover_item.setVisible(False)
        self._visible_news_events = []
        for item in list(self._news_items):
            try:
                self.price_plot.removeItem(item)
            except Exception:
                pass
        self._news_items = []

        if self._last_x is None or self._last_df is None or len(self._last_x) == 0 or not self._news_events:
            return

        try:
            high_values = self._last_df["high"].astype(float).to_numpy()
            price_anchor = float(np.nanmax(high_values))
            low_anchor = float(np.nanmin(self._last_df["low"].astype(float).to_numpy()))
        except Exception:
            return

        visible_min = float(np.nanmin(self._last_x))
        visible_max = float(np.nanmax(self._last_x))
        price_span = max(price_anchor - low_anchor, 1e-6)
        marker_y = price_anchor + (price_span * 0.03)

        xs = []
        ys = []
        tooltips = []
        visible_events = []

        for event in self._news_events[:12]:
            timestamp_text = str(event.get("timestamp", "") or "")
            try:
                event_dt = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
            except Exception:
                continue
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            x_value = float(event_dt.timestamp())
            if x_value < visible_min or x_value > visible_max:
                continue
            xs.append(x_value)
            ys.append(marker_y)
            headline = str(event.get("title", "") or "News event")
            source = str(event.get("source", "") or "News Feed")
            summary = str(event.get("summary", "") or "").strip()
            impact = event.get("impact", "")
            sentiment = event.get("sentiment_score", "")
            timestamp_label = event_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            tooltip_parts = [f"{source} | {timestamp_label}", headline]
            if summary:
                tooltip_parts.append(summary)
            if impact not in ("", None) or sentiment not in ("", None):
                tooltip_parts.append(f"Impact {impact} | Sentiment {sentiment}")
            tooltips.append("\n".join(str(part) for part in tooltip_parts if str(part).strip()))
            visible_events.append(
                {
                    "x": x_value,
                    "y": marker_y,
                    "headline": headline,
                    "source": source,
                    "time": timestamp_label,
                    "summary": summary,
                    "impact": impact,
                    "sentiment": sentiment,
                }
            )

        if not xs:
            return

        self.news_markers.setData(
            x=xs,
            y=ys,
            symbol="d",
            size=9,
            brush=pg.mkBrush("#ffd166"),
            pen=mkPen("#f4a261", width=1.1),
            data=tooltips,
        )
        self._visible_news_events = visible_events

        for event in visible_events[:5]:
            x_value = float(event["x"])
            line = InfiniteLine(
                pos=x_value,
                angle=90,
                movable=False,
                pen=mkPen((244, 162, 97, 70), width=1, style=QtCore.Qt.PenStyle.DotLine),
            )
            self.price_plot.addItem(line, ignoreBounds=True)
            self._news_items.append(line)

            label = TextItem(
                html=(
                    "<div style='background-color: rgba(11,18,32,0.92); color: #f8fbff; "
                    "padding: 4px 7px; border: 1px solid rgba(244,162,97,0.55); border-radius: 6px;'>"
                    f"<div style='color: #ffd166; font-size: 10px; font-weight: 700;'>{event['source']} | {event['time']}</div>"
                    f"<div style='color: #f8fbff; font-size: 11px; font-weight: 600;'>{event['headline'][:68]}{'...' if len(event['headline']) > 68 else ''}</div>"
                    f"<div style='color: #9ec1ff; font-size: 10px;'>Impact {event['impact']} | Sentiment {event['sentiment']}</div>"
                    "</div>"
                ),
                anchor=(0.0, 1.0),
                border=None,
                fill=None,
            )
            label.setPos(x_value, marker_y)
            self.price_plot.addItem(label)
            self._news_items.append(label)

    def _pivot_window(self, period: int) -> int:
        return max(2, int(period) // 2)

    def _build_fractal_points(self, high, low, x, period: int):
        window = self._pivot_window(period)
        upper_x = []
        upper_y = []
        lower_x = []
        lower_y = []

        for index in range(window, len(x) - window):
            high_slice = high.iloc[index - window: index + window + 1]
            low_slice = low.iloc[index - window: index + window + 1]

            current_high = float(high.iloc[index])
            current_low = float(low.iloc[index])

            if np.isfinite(current_high) and current_high >= float(high_slice.max()):
                upper_x.append(float(x[index]))
                upper_y.append(current_high)

            if np.isfinite(current_low) and current_low <= float(low_slice.min()):
                lower_x.append(float(x[index]))
                lower_y.append(current_low)

        return (np.array(upper_x, dtype=float), np.array(upper_y, dtype=float)), (
            np.array(lower_x, dtype=float),
            np.array(lower_y, dtype=float),
        )

    def _build_zigzag_points(self, high, low, x, period: int):
        window = self._pivot_window(period)
        candidates = []

        for index in range(window, len(x) - window):
            high_slice = high.iloc[index - window: index + window + 1]
            low_slice = low.iloc[index - window: index + window + 1]
            current_high = float(high.iloc[index])
            current_low = float(low.iloc[index])

            if np.isfinite(current_high) and current_high >= float(high_slice.max()):
                candidates.append((index, "H", current_high))

            if np.isfinite(current_low) and current_low <= float(low_slice.min()):
                candidates.append((index, "L", current_low))

        if not candidates:
            return np.array([], dtype=float), np.array([], dtype=float)

        candidates.sort(key=lambda item: item[0])
        pivots = []

        for candidate in candidates:
            if not pivots:
                pivots.append(candidate)
                continue

            last_index, last_kind, last_price = pivots[-1]
            current_index, current_kind, current_price = candidate

            if current_kind == last_kind:
                if current_kind == "H" and current_price >= last_price:
                    pivots[-1] = candidate
                elif current_kind == "L" and current_price <= last_price:
                    pivots[-1] = candidate
                continue

            if current_index == last_index:
                more_extreme = (
                    current_kind == "H" and current_price >= last_price
                ) or (
                    current_kind == "L" and current_price <= last_price
                )
                if more_extreme:
                    pivots[-1] = candidate
                continue

            pivots.append(candidate)

        zz_x = np.array([float(x[index]) for index, _kind, _price in pivots], dtype=float)
        zz_y = np.array([float(price) for _index, _kind, price in pivots], dtype=float)
        return zz_x, zz_y

    def _build_fibonacci_overlay(self):
        levels = [
            (0.0, "#90caf9"),
            (0.236, "#4fc3f7"),
            (0.382, "#26a69a"),
            (0.5, "#ffd54f"),
            (0.618, "#ffb74d"),
            (0.786, "#ef5350"),
            (1.0, "#ce93d8"),
        ]
        curves = []
        labels = []
        for ratio, color in levels:
            curve = self._create_curve(
                self.price_plot,
                color,
                1.0 if ratio not in {0.0, 1.0} else 1.2,
                QtCore.Qt.PenStyle.DashLine,
            )
            label = TextItem(
                html="",
                anchor=(1.0, 0.5),
                border=None,
                fill=pg.mkBrush(11, 18, 32, 160),
            )
            self.price_plot.addItem(label)
            curves.append(curve)
            labels.append(label)
        return {"curves": curves, "labels": labels, "levels": levels}

    def add_indicator(self, name: str, period: int = 20):
        indicator = (name or "").strip().upper()
        period = max(2, int(period))
        aliases = {
            "MOVING AVERAGE": "SMA",
            "MA": "SMA",
            "EXPONENTIAL MOVING AVERAGE": "EMA",
            "WEIGHTED MOVING AVERAGE": "LWMA",
            "LINEAR WEIGHTED MOVING AVERAGE": "LWMA",
            "WMA": "LWMA",
            "SMOOTHED MOVING AVERAGE": "SMMA",
            "BOLLINGER": "BB",
            "BOLLINGER BANDS": "BB",
            "AVERAGE DIRECTIONAL MOVEMENT INDEX": "ADX",
            "AVERAGE TRUE RANGE": "ATR",
            "PARABOLIC SAR": "SAR",
            "STANDARD DEVIATION": "STDDEV",
            "ACCELERATOR OSCILLATOR": "AC",
            "AWESOME OSCILLATOR": "AO",
            "STOCHASTIC OSCILLATOR": "STOCHASTIC",
            "WILLIAMS' PERCENT RANGE": "WPR",
            "WILLIAMS PERCENT RANGE": "WPR",
            "ACCUMULATION/DISTRIBUTION": "AD",
            "ACCUMULATION DISTRIBUTION": "AD",
            "MONEY FLOW INDEX": "MFI",
            "ON BALANCE VOLUME": "OBV",
            "MARKET FACILITATION INDEX": "BW_MFI",
            "GATOR OSCILLATOR": "GATOR",
            "DONCHIAN CHANNEL": "DONCHIAN",
            "DONCHIAN CHANNELS": "DONCHIAN",
            "KELTNER CHANNEL": "KELTNER",
            "KELTNER CHANNELS": "KELTNER",
            "FIBONACCI": "FIBO",
            "FIBONACCI RETRACEMENT": "FIBO",
            "FIBO": "FIBO",
            "FRACTALS": "FRACTAL",
            "ZIG ZAG": "ZIGZAG",
        }
        indicator = aliases.get(indicator, indicator)

        if indicator in {"SMA", "EMA", "SMMA", "LWMA", "VWAP"}:
            key = f"{indicator}_{period}"
            if key in self.indicator_items:
                return key
            color_map = {
                "SMA": "#ffd54f",
                "EMA": "#80deea",
                "SMMA": "#b39ddb",
                "LWMA": "#ff8a65",
                "VWAP": "#81c784",
            }
            self.indicator_items[key] = [self._create_curve(self.price_plot, color_map.get(indicator, "#ffd54f"), 1.6)]
            self.indicators.append({"type": indicator, "period": period, "key": key})
            return key

        if indicator in {"BB", "ENVELOPES", "DONCHIAN", "KELTNER"}:
            key = f"{indicator}_{period}"
            if key in self.indicator_items:
                return key
            if indicator == "BB":
                items = [
                    self._create_curve(self.price_plot, "#ffb74d", 1.4),
                    self._create_curve(self.price_plot, "#ab47bc", 1.1),
                    self._create_curve(self.price_plot, "#ab47bc", 1.1),
                ]
            elif indicator == "ENVELOPES":
                items = [
                    self._create_curve(self.price_plot, "#90caf9", 1.3),
                    self._create_curve(self.price_plot, "#4fc3f7", 1.0),
                    self._create_curve(self.price_plot, "#4fc3f7", 1.0),
                ]
            elif indicator == "DONCHIAN":
                items = [
                    self._create_curve(self.price_plot, "#64b5f6", 1.1),
                    self._create_curve(self.price_plot, "#90caf9", 1.0, QtCore.Qt.PenStyle.DashLine),
                    self._create_curve(self.price_plot, "#64b5f6", 1.1),
                ]
            else:
                items = [
                    self._create_curve(self.price_plot, "#ffcc80", 1.2),
                    self._create_curve(self.price_plot, "#ce93d8", 1.0),
                    self._create_curve(self.price_plot, "#ce93d8", 1.0),
                ]
            self.indicator_items[key] = items
            self.indicators.append({"type": indicator, "period": period, "key": key})
            return key

        if indicator in {"ICHIMOKU", "ALLIGATOR"}:
            key = indicator
            if key in self.indicator_items:
                return key
            if indicator == "ICHIMOKU":
                items = [
                    self._create_curve(self.price_plot, "#ffca28", 1.2),
                    self._create_curve(self.price_plot, "#42a5f5", 1.2),
                    self._create_curve(self.price_plot, "#66bb6a", 1.0),
                    self._create_curve(self.price_plot, "#ef5350", 1.0),
                    self._create_curve(self.price_plot, "#b39ddb", 1.0),
                ]
            else:
                items = [
                    self._create_curve(self.price_plot, "#42a5f5", 1.3),
                    self._create_curve(self.price_plot, "#ef5350", 1.3),
                    self._create_curve(self.price_plot, "#66bb6a", 1.3),
                ]
            self.indicator_items[key] = items
            self.indicators.append({"type": indicator, "period": period, "key": key})
            return key

        if indicator == "SAR":
            key = "SAR"
            if key in self.indicator_items:
                return key
            scatter = ScatterPlotItem()
            self.price_plot.addItem(scatter)
            self.indicator_items[key] = [scatter]
            self.indicators.append({"type": "SAR", "period": period, "key": key})
            return key

        if indicator == "FRACTAL":
            key = f"FRACTAL_{period}"
            if key in self.indicator_items:
                return key
            upper = ScatterPlotItem()
            lower = ScatterPlotItem()
            self.price_plot.addItem(upper)
            self.price_plot.addItem(lower)
            self.indicator_items[key] = [upper, lower]
            self.indicators.append({"type": "FRACTAL", "period": period, "key": key})
            return key

        if indicator == "ZIGZAG":
            key = f"ZIGZAG_{period}"
            if key in self.indicator_items:
                return key
            curve = self._create_curve(self.price_plot, "#f06292", 1.8)
            self.indicator_items[key] = [curve]
            self.indicators.append({"type": "ZIGZAG", "period": period, "key": key})
            return key

        if indicator == "FIBO":
            key = f"FIBO_{period}"
            if key in self.indicator_items:
                return key
            self.indicator_items[key] = self._build_fibonacci_overlay()
            self.indicators.append({"type": "FIBO", "period": period, "key": key})
            return key

        if indicator == "VOLUMES":
            key = "VOLUMES"
            if key not in self.indicator_items:
                self.indicator_items[key] = []
                self.indicators.append({"type": "VOLUMES", "period": period, "key": key})
            return key

        pane_label_map = {
            "ADX": "ADX",
            "ATR": "ATR",
            "STDDEV": "StdDev",
            "AC": "Accelerator",
            "AO": "Awesome",
            "CCI": "CCI",
            "DEMARKER": "DeMarker",
            "MACD": "MACD",
            "MOMENTUM": "Momentum",
            "OSMA": "OsMA",
            "RSI": "RSI",
            "RVI": "RVI",
            "STOCHASTIC": "Stochastic",
            "WPR": "Williams %R",
            "AD": "A/D",
            "MFI": "Money Flow",
            "OBV": "OBV",
            "BULLS POWER": "Bulls Power",
            "BEARS POWER": "Bears Power",
            "FORCE INDEX": "Force Index",
            "GATOR": "Gator",
            "BW_MFI": "Market Facilitation",
        }
        lower_indicator = indicator
        if lower_indicator in pane_label_map:
            key = f"{lower_indicator}_{period}" if lower_indicator in {
                "ADX",
                "ATR",
                "STDDEV",
                "CCI",
                "DEMARKER",
                "MOMENTUM",
                "RSI",
                "STOCHASTIC",
                "WPR",
                "MFI",
                "FORCE INDEX",
            } else lower_indicator.replace(" ", "_")
            if key in self.indicator_items:
                return key

            pane = self._create_indicator_pane(key, pane_label_map[lower_indicator])
            items = []

            if lower_indicator == "ADX":
                items = [
                    self._create_curve(pane, "#ffd54f", 1.4),
                    self._create_curve(pane, "#26a69a", 1.2),
                    self._create_curve(pane, "#ef5350", 1.2),
                ]
                self._add_reference_line(pane, 20.0)
            elif lower_indicator in {"ATR", "STDDEV", "AD", "MFI", "OBV", "MOMENTUM", "BULLS POWER", "BEARS POWER", "FORCE INDEX"}:
                items = [self._create_curve(pane, "#80deea", 1.5)]
                if lower_indicator in {"BULLS POWER", "BEARS POWER", "FORCE INDEX"}:
                    self._add_reference_line(pane, 0.0)
            elif lower_indicator in {"AC", "AO", "OSMA", "GATOR", "BW_MFI"}:
                items = [self._create_histogram(pane)]
                if lower_indicator == "GATOR":
                    items.append(self._create_histogram(pane))
                self._add_reference_line(pane, 0.0)
            elif lower_indicator == "CCI":
                items = [self._create_curve(pane, "#ffb74d", 1.5)]
                self._add_reference_line(pane, 100.0)
                self._add_reference_line(pane, -100.0)
            elif lower_indicator == "DEMARKER":
                items = [self._create_curve(pane, "#64b5f6", 1.5)]
                self._add_reference_line(pane, 0.3)
                self._add_reference_line(pane, 0.7)
            elif lower_indicator == "MACD":
                items = [
                    self._create_histogram(pane),
                    self._create_curve(pane, "#42a5f5", 1.3),
                    self._create_curve(pane, "#ffca28", 1.1),
                ]
                self._add_reference_line(pane, 0.0)
            elif lower_indicator == "RSI":
                items = [self._create_curve(pane, "#ab47bc", 1.5)]
                self._add_reference_line(pane, 30.0)
                self._add_reference_line(pane, 70.0)
            elif lower_indicator == "RVI":
                items = [
                    self._create_curve(pane, "#4fc3f7", 1.4),
                    self._create_curve(pane, "#ffb74d", 1.1),
                ]
                self._add_reference_line(pane, 0.0)
            elif lower_indicator == "STOCHASTIC":
                items = [
                    self._create_curve(pane, "#66bb6a", 1.4),
                    self._create_curve(pane, "#ef5350", 1.1),
                ]
                self._add_reference_line(pane, 20.0)
                self._add_reference_line(pane, 80.0)
            elif lower_indicator == "WPR":
                items = [self._create_curve(pane, "#90caf9", 1.4)]
                self._add_reference_line(pane, -20.0)
                self._add_reference_line(pane, -80.0)

            self.indicator_items[key] = items
            self.indicators.append({"type": lower_indicator, "period": period, "key": key})
            return key

        return None

    def _update_indicators(self, df, x, width):
        if not self.indicators:
            return

        open_ = df["open"].astype(float)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)

        for spec in self.indicators:
            ind_type = spec["type"]
            period = spec["period"]
            key = spec["key"]
            items = self.indicator_items.get(key, [])

            if ind_type == "SMA" and items:
                series = sma(close, period).to_numpy()
                items[0].setData(x, series)

            elif ind_type == "EMA" and items:
                series = ema(close, period).to_numpy()
                items[0].setData(x, series)

            elif ind_type == "SMMA" and items:
                series = smma(close, period).to_numpy()
                items[0].setData(x, series)

            elif ind_type == "LWMA" and items:
                series = lwma(close, period).to_numpy()
                items[0].setData(x, series)

            elif ind_type == "VWAP" and items:
                typical_price = (high + low + close) / 3.0
                pv = typical_price * volume
                vwap = pv.rolling(window=period, min_periods=1).sum() / volume.rolling(window=period, min_periods=1).sum().replace(0, np.nan)
                items[0].setData(x, vwap.bfill().fillna(close).to_numpy())

            elif ind_type == "BB" and len(items) == 3:
                mid = close.rolling(window=period, min_periods=1).mean()
                std = close.rolling(window=period, min_periods=1).std().fillna(0.0)
                upper = (mid + 2.0 * std).to_numpy()
                lower = (mid - 2.0 * std).to_numpy()
                items[0].setData(x, mid.to_numpy())
                items[1].setData(x, upper)
                items[2].setData(x, lower)

            elif ind_type == "ENVELOPES" and len(items) == 3:
                mid, upper, lower = envelopes(close, period)
                items[0].setData(x, mid.to_numpy())
                items[1].setData(x, upper.to_numpy())
                items[2].setData(x, lower.to_numpy())

            elif ind_type == "DONCHIAN" and len(items) == 3:
                upper = high.rolling(window=period, min_periods=1).max()
                lower = low.rolling(window=period, min_periods=1).min()
                mid = (upper + lower) / 2.0
                items[0].setData(x, upper.to_numpy())
                items[1].setData(x, mid.to_numpy())
                items[2].setData(x, lower.to_numpy())

            elif ind_type == "KELTNER" and len(items) == 3:
                atr_series = atr(high, low, close, period)
                mid = close.ewm(span=period, adjust=False).mean()
                upper = mid + (2.0 * atr_series)
                lower = mid - (2.0 * atr_series)
                items[0].setData(x, mid.to_numpy())
                items[1].setData(x, upper.to_numpy())
                items[2].setData(x, lower.to_numpy())

            elif ind_type == "ICHIMOKU" and len(items) == 5:
                tenkan, kijun, span_a, span_b, chikou = ichimoku(high, low, close)
                items[0].setData(x, tenkan.to_numpy())
                items[1].setData(x, kijun.to_numpy())
                items[2].setData(x, span_a.to_numpy())
                items[3].setData(x, span_b.to_numpy())
                items[4].setData(x, chikou.to_numpy())

            elif ind_type == "ALLIGATOR" and len(items) == 3:
                jaw, teeth, lips = alligator(high, low)
                items[0].setData(x, jaw.to_numpy())
                items[1].setData(x, teeth.to_numpy())
                items[2].setData(x, lips.to_numpy())

            elif ind_type == "SAR" and items:
                sar = parabolic_sar(high, low)
                items[0].setData(
                    x=np.asarray(x, dtype=float),
                    y=sar.to_numpy(),
                    symbol="o",
                    size=5,
                    brush=pg.mkBrush("#90caf9"),
                    pen=mkPen("#90caf9"),
                )

            elif ind_type == "FRACTAL" and len(items) == 2:
                (upper_x, upper_y), (lower_x, lower_y) = self._build_fractal_points(high, low, x, period)
                items[0].setData(
                    x=upper_x,
                    y=upper_y,
                    symbol="t",
                    size=10,
                    brush="#ef5350",
                    pen=mkPen("#ef5350"),
                )
                items[1].setData(
                    x=lower_x,
                    y=lower_y,
                    symbol="t1",
                    size=10,
                    brush="#26a69a",
                    pen=mkPen("#26a69a"),
                )

            elif ind_type == "ZIGZAG" and items:
                zz_x, zz_y = self._build_zigzag_points(high, low, x, period)
                items[0].setData(zz_x, zz_y)

            elif ind_type == "FIBO" and isinstance(items, dict):
                curves = items.get("curves", [])
                labels = items.get("labels", [])
                levels = items.get("levels", [])
                lookback = min(len(df), max(2, int(period)))
                window_high = high.iloc[-lookback:]
                window_low = low.iloc[-lookback:]
                if len(window_high) == 0 or len(window_low) == 0 or len(x) == 0:
                    continue

                high_value = float(window_high.max())
                low_value = float(window_low.min())
                span = high_value - low_value
                if not np.isfinite(span) or span <= 0:
                    span = max(abs(high_value) * 0.001, 1e-9)

                x_start = float(x[max(0, len(x) - lookback)])
                x_end = float(x[-1])
                label_x = x_end + max(width * 2.0, 1.0)

                for index, (ratio, _color) in enumerate(levels):
                    level_price = high_value - (span * float(ratio))
                    curves[index].setData(
                        np.array([x_start, x_end], dtype=float),
                        np.array([level_price, level_price], dtype=float),
                    )
                    labels[index].setHtml(
                        f"<span style='color:#d7dfeb;font-size:11px;'>"
                        f"{ratio * 100:.1f}%  {level_price:.6f}</span>"
                    )
                    labels[index].setPos(label_x, level_price)

            elif ind_type == "ADX" and len(items) == 3:
                adx_line, plus_di, minus_di = adx(high, low, close, period)
                items[0].setData(x, adx_line.to_numpy())
                items[1].setData(x, plus_di.to_numpy())
                items[2].setData(x, minus_di.to_numpy())

            elif ind_type == "ATR" and items:
                items[0].setData(x, atr(high, low, close, period).to_numpy())

            elif ind_type == "STDDEV" and items:
                items[0].setData(x, standard_deviation(close, period).to_numpy())

            elif ind_type == "AC" and items:
                values = accelerator(high, low).to_numpy()
                brushes = [pg.mkBrush("#26a69a" if index == 0 or values[index] >= values[index - 1] else "#ef5350") for index in range(len(values))]
                self._set_histogram_data(items[0], x, values, width, brushes)

            elif ind_type == "AO" and items:
                values = awesome(high, low).to_numpy()
                brushes = [pg.mkBrush("#26a69a" if index == 0 or values[index] >= values[index - 1] else "#ef5350") for index in range(len(values))]
                self._set_histogram_data(items[0], x, values, width, brushes)

            elif ind_type == "CCI" and items:
                items[0].setData(x, cci(high, low, close, period).to_numpy())

            elif ind_type == "DEMARKER" and items:
                items[0].setData(x, demarker(high, low, period).to_numpy())

            elif ind_type == "MACD" and len(items) == 3:
                macd_line, signal_line, histogram = macd(close)
                brushes = [pg.mkBrush("#26a69a" if value >= 0 else "#ef5350") for value in histogram.to_numpy()]
                self._set_histogram_data(items[0], x, histogram.to_numpy(), width, brushes)
                items[1].setData(x, macd_line.to_numpy())
                items[2].setData(x, signal_line.to_numpy())

            elif ind_type == "MOMENTUM" and items:
                items[0].setData(x, momentum(close, period).to_numpy())

            elif ind_type == "OSMA" and items:
                _macd_line, _signal_line, histogram = macd(close)
                brushes = [pg.mkBrush("#26a69a" if value >= 0 else "#ef5350") for value in histogram.to_numpy()]
                self._set_histogram_data(items[0], x, histogram.to_numpy(), width, brushes)

            elif ind_type == "RSI" and items:
                items[0].setData(x, rsi(close, period).to_numpy())

            elif ind_type == "RVI" and len(items) == 2:
                rvi_line, signal_line = rvi(open_, high, low, close, period)
                items[0].setData(x, rvi_line.to_numpy())
                items[1].setData(x, signal_line.to_numpy())

            elif ind_type == "STOCHASTIC" and len(items) == 2:
                percent_k, percent_d = stochastic(high, low, close, period)
                items[0].setData(x, percent_k.to_numpy())
                items[1].setData(x, percent_d.to_numpy())

            elif ind_type == "WPR" and items:
                items[0].setData(x, williams_r(high, low, close, period).to_numpy())

            elif ind_type == "AD" and items:
                items[0].setData(x, accumulation_distribution(high, low, close, volume).to_numpy())

            elif ind_type == "MFI" and items:
                items[0].setData(x, money_flow_index(high, low, close, volume, period).to_numpy())

            elif ind_type == "OBV" and items:
                items[0].setData(x, obv(close, volume).to_numpy())

            elif ind_type == "BULLS POWER" and items:
                items[0].setData(x, bulls_power(high, close).to_numpy())

            elif ind_type == "BEARS POWER" and items:
                items[0].setData(x, bears_power(low, close).to_numpy())

            elif ind_type == "FORCE INDEX" and items:
                items[0].setData(x, force_index(close, volume, period).to_numpy())

            elif ind_type == "GATOR" and len(items) == 2:
                upper, lower = gator(high, low)
                upper_brushes = [pg.mkBrush("#26a69a" if value >= 0 else "#ef5350") for value in upper.to_numpy()]
                lower_brushes = [pg.mkBrush("#ef5350" if value < 0 else "#26a69a") for value in lower.to_numpy()]
                self._set_histogram_data(items[0], x, upper.to_numpy(), width, upper_brushes)
                self._set_histogram_data(items[1], x, lower.to_numpy(), width, lower_brushes)

            elif ind_type == "BW_MFI" and items:
                values, colors = market_facilitation_index(high, low, volume)
                self._set_histogram_data(items[0], x, values.to_numpy(), width, [pg.mkBrush(color) for color in colors])

            elif ind_type == "VOLUMES":
                continue

    def update_candles(self, df):
        if df is None or len(df) == 0:
            return

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return

        x = self._extract_time_axis(df)
        width = self._infer_candle_width(x)
        self._sync_view_context()
        self._last_df = df.copy()
        self._last_x = np.array(x, dtype=float)
        self._last_candle_stats = self._build_candle_stats(self._last_df, self._last_x)

        candles = np.column_stack(
            [
                x,
                df["open"].astype(float).to_numpy(),
                df["close"].astype(float).to_numpy(),
                df["low"].astype(float).to_numpy(),
                df["high"].astype(float).to_numpy(),
            ]
        )

        self._last_candles = candles
        self.candle_item.set_body_width(width)
        self.candle_item.setData(candles)
        self.ema_curve.setData([], [])

        volume = df["volume"].astype(float).to_numpy()
        colors = [self.candle_up_color if c >= o else self.candle_down_color for o, c in zip(df["open"], df["close"])]
        brushes = [pg.mkBrush(c) for c in colors]
        self.volume_bars.setOpts(x=x, height=volume, width=width, brushes=brushes)

        self._update_indicators(df, x, width)

        if self._should_fit_chart_view(self._last_x):
            self._fit_chart_view(self._last_candle_stats, width)
        self.refresh_context_display()
        self._update_ohlcv_for_x(self._last_x[-1] if len(self._last_x) else 0.0)
        self._render_news_events()

        try:
            last_close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else last_close
            line_color = self.candle_up_color if last_close >= prev_close else self.candle_down_color
            self.last_line.setPen(mkPen(line_color, width=1.15))
            self.last_line.label.fill = pg.mkBrush(pg.mkColor(line_color))
            self.last_line.label.setColor(pg.mkColor("#ffffff"))
            self.last_line.setPos(last_close)
            self.last_line.setVisible(True)
        except Exception:
            pass

    def update_price_lines(self, bid: float, ask: float, last: float | None = None):
        try:
            bid_f = float(bid)
            ask_f = float(ask)
        except Exception:
            return

        self._last_bid = bid_f
        self._last_ask = ask_f

        if bid_f > 0:
            self.bid_line.setPos(bid_f)
            self.bid_line.setVisible(self.show_bid_ask_lines)

        if ask_f > 0:
            self.ask_line.setPos(ask_f)
            self.ask_line.setVisible(self.show_bid_ask_lines)

        if last is None:
            last_f = (bid_f + ask_f) / 2.0 if (bid_f > 0 and ask_f > 0) else 0.0
        else:
            try:
                last_f = float(last)
            except Exception:
                last_f = 0.0

        if last_f > 0:
            self.last_line.setPos(last_f)
            self.last_line.setVisible(True)
        self._update_chart_header()
        self._refresh_market_panels()

    def set_bid_ask_lines_visible(self, visible: bool):
        self.show_bid_ask_lines = bool(visible)
        self.bid_line.setVisible(self.show_bid_ask_lines and self._last_bid is not None and self._last_bid > 0)
        self.ask_line.setVisible(self.show_bid_ask_lines and self._last_ask is not None and self._last_ask > 0)

    def set_candle_colors(self, up_color: str, down_color: str):
        self.candle_up_color = up_color
        self.candle_down_color = down_color
        self.candle_item.set_colors(up_color, down_color)
        if self._last_candles is not None:
            self.candle_item.setData(self._last_candles)

    def link_all_charts(self, _count):
        return
