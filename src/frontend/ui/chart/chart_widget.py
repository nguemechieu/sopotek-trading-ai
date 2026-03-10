import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget
from pyqtgraph import DateAxisItem, InfiniteLine, PlotWidget, ScatterPlotItem, SignalProxy, TextItem, mkPen

from frontend.ui.chart.chart_items import CandlestickItem


class ChartWidget(QWidget):
    sigMouseMoved = QtCore.Signal(object)

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
        self.heatmap_buffer = []
        self.max_heatmap_rows = 220
        self.max_heatmap_levels = 120

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(QtCore.Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)
        self.splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: #132033;
                border-top: 1px solid #24354f;
                border-bottom: 1px solid #24354f;
            }
            QSplitter::handle:hover {
                background-color: #1c3150;
            }
            """
        )
        layout.addWidget(self.splitter)

        date_axis_top = DateAxisItem(orientation="bottom")
        self.price_plot = PlotWidget(axisItems={"bottom": date_axis_top})
        self.price_plot.setBackground("#0b1220")
        self.price_plot.showGrid(x=True, y=True, alpha=0.2)
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

        self.signal_markers = ScatterPlotItem()
        self.trade_scatter = ScatterPlotItem()
        self.price_plot.addItem(self.signal_markers)
        self.price_plot.addItem(self.trade_scatter)

        date_axis_mid = DateAxisItem(orientation="bottom")
        self.volume_plot = PlotWidget(axisItems={"bottom": date_axis_mid})
        self.volume_plot.setBackground("#0b1220")
        self.volume_plot.setXLink(self.price_plot)
        self.volume_plot.showGrid(x=True, y=True, alpha=0.2)
        self.volume_plot.setLabel("left", "Volume")
        self.volume_plot.hideAxis("right")
        self.volume_plot.hideAxis("bottom")
        self.volume_plot.setMinimumHeight(120)
        self.splitter.addWidget(self.volume_plot)

        self.volume_bars = pg.BarGraphItem(x=[], height=[], width=60.0, brush="#5c6bc0")
        self.volume_plot.addItem(self.volume_bars)

        date_axis_bottom = DateAxisItem(orientation="bottom")
        self.heatmap_plot = PlotWidget(axisItems={"bottom": date_axis_bottom})
        self.heatmap_plot.setBackground("#0b1220")
        self.heatmap_plot.setXLink(self.price_plot)
        self.heatmap_plot.showGrid(x=True, y=True, alpha=0.2)
        self.heatmap_plot.setLabel("left", "Orderbook")
        self.heatmap_plot.setLabel("bottom", "Gregorian Time")
        self.heatmap_plot.setMinimumHeight(120)
        self.splitter.addWidget(self.heatmap_plot)

        self.heatmap_image = pg.ImageItem()
        colormap = pg.colormap.get("inferno")
        self.heatmap_image.setLookupTable(colormap.getLookupTable())
        self.heatmap_plot.addItem(self.heatmap_image)

        self.v_line = InfiniteLine(angle=90, movable=False, pen=mkPen("#90caf9", width=1))
        self.h_line = InfiniteLine(angle=0, movable=False, pen=mkPen("#90caf9", width=1))
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
            pen=mkPen("#90caf9", width=1),
            label="Last {value:.6f}",
            labelOpts={"position": 0.98, "color": "#90caf9", "fill": (11, 18, 32, 160)},
        )

        for line in (self.bid_line, self.ask_line, self.last_line):
            line.setVisible(False)
            self.price_plot.addItem(line, ignoreBounds=True)

        self.text_item = TextItem(color="#e3f2fd")
        self.price_plot.addItem(self.text_item)

        self.proxy = SignalProxy(self.price_plot.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved)

        self.splitter.setStretchFactor(0, 8)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setSizes([720, 170, 170])

    def _mouse_moved(self, evt):
        pos = evt[0]
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return

        mouse_point = self.price_plot.getPlotItem().vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()

        self.v_line.setPos(x)
        self.h_line.setPos(y)
        self.text_item.setHtml(f"<span style='color:#e3f2fd'>Price: {y:.6f}</span>")
        self.text_item.setPos(x, y)

    def _extract_time_axis(self, df):
        if "timestamp" not in df.columns:
            return np.arange(len(df), dtype=float)

        ts = df["timestamp"]

        # Numeric epoch input
        if np.issubdtype(ts.dtype, np.number):
            x = ts.astype(float).to_numpy()
            if len(x) > 0:
                median = np.nanmedian(np.abs(x))
                if median > 1e11:  # likely milliseconds
                    x = x / 1000.0
            return x

        # String/datetime input
        try:
            import pandas as pd

            dt = pd.to_datetime(ts, errors="coerce", utc=True)
            x = (dt.view("int64") / 1e9).to_numpy(dtype=float)
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
        return max(step * 0.7, 1e-6)

    def update_orderbook_heatmap(self, bids, asks):
        if not bids and not asks:
            return

        levels = (bids or []) + (asks or [])
        volumes = []
        for level in levels[: self.max_heatmap_levels]:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                try:
                    volumes.append(float(level[1]))
                except Exception:
                    continue

        if not volumes:
            return

        max_vol = max(volumes)
        if max_vol <= 0:
            return

        normalized = np.zeros(self.max_heatmap_levels, dtype=float)
        scaled = [v / max_vol for v in volumes[: self.max_heatmap_levels]]
        normalized[: len(scaled)] = scaled

        self.heatmap_buffer.append(normalized.tolist())
        if len(self.heatmap_buffer) > self.max_heatmap_rows:
            self.heatmap_buffer.pop(0)

        matrix = np.array(self.heatmap_buffer, dtype=float)
        self.heatmap_image.setImage(matrix.T, autoLevels=False, levels=(0.0, 1.0))

    def add_strategy_signal(self, index, price, signal):
        if signal == "BUY":
            self.signal_markers.addPoints(x=[index], y=[price], symbol="t1", brush="#26a69a", size=12)
        elif signal == "SELL":
            self.signal_markers.addPoints(x=[index], y=[price], symbol="t", brush="#ef5350", size=12)

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

    def add_indicator(self, name: str, period: int = 20):
        indicator = (name or "").strip().upper()
        period = max(2, int(period))

        if indicator in {"SMA", "EMA", "WMA", "VWAP"}:
            key = f"{indicator}_{period}"
            if key in self.indicator_items:
                return key

            color_map = {
                "SMA": "#ffd54f",
                "EMA": "#80deea",
                "WMA": "#ff8a65",
                "VWAP": "#81c784",
            }
            color = color_map.get(indicator, "#ffd54f")
            curve = self.price_plot.plot(pen=mkPen(color, width=1.6))
            self.indicator_items[key] = [curve]
            self.indicators.append({"type": indicator, "period": period, "key": key})

        elif indicator in {"BB", "BOLLINGER", "BOLLINGER BANDS"}:
            key = f"BB_{period}"
            if key in self.indicator_items:
                return key

            mid = self.price_plot.plot(pen=mkPen("#ffb74d", width=1.4))
            upper = self.price_plot.plot(pen=mkPen("#ab47bc", width=1.1))
            lower = self.price_plot.plot(pen=mkPen("#ab47bc", width=1.1))
            self.indicator_items[key] = [mid, upper, lower]
            self.indicators.append({"type": "BB", "period": period, "key": key})

        elif indicator in {"DONCHIAN", "DONCHIAN CHANNEL", "DONCHIAN CHANNELS"}:
            key = f"DONCHIAN_{period}"
            if key in self.indicator_items:
                return key

            upper = self.price_plot.plot(pen=mkPen("#64b5f6", width=1.1))
            mid = self.price_plot.plot(pen=mkPen("#90caf9", width=1.0, style=QtCore.Qt.PenStyle.DashLine))
            lower = self.price_plot.plot(pen=mkPen("#64b5f6", width=1.1))
            self.indicator_items[key] = [upper, mid, lower]
            self.indicators.append({"type": "DONCHIAN", "period": period, "key": key})

        elif indicator in {"KELTNER", "KELTNER CHANNEL", "KELTNER CHANNELS"}:
            key = f"KELTNER_{period}"
            if key in self.indicator_items:
                return key

            mid = self.price_plot.plot(pen=mkPen("#ffcc80", width=1.2))
            upper = self.price_plot.plot(pen=mkPen("#ce93d8", width=1.0))
            lower = self.price_plot.plot(pen=mkPen("#ce93d8", width=1.0))
            self.indicator_items[key] = [mid, upper, lower]
            self.indicators.append({"type": "KELTNER", "period": period, "key": key})

        elif indicator in {"FRACTAL", "FRACTALS"}:
            key = f"FRACTAL_{period}"
            if key in self.indicator_items:
                return key

            upper = ScatterPlotItem()
            lower = ScatterPlotItem()
            self.price_plot.addItem(upper)
            self.price_plot.addItem(lower)
            self.indicator_items[key] = [upper, lower]
            self.indicators.append({"type": "FRACTAL", "period": period, "key": key})

        elif indicator in {"ZIGZAG", "ZIG ZAG"}:
            key = f"ZIGZAG_{period}"
            if key in self.indicator_items:
                return key

            curve = self.price_plot.plot(pen=mkPen("#f06292", width=1.8))
            self.indicator_items[key] = [curve]
            self.indicators.append({"type": "ZIGZAG", "period": period, "key": key})

        else:
            return None

        return key

    def _update_indicators(self, df, x):
        if not self.indicators:
            return

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
                series = close.rolling(window=period, min_periods=1).mean().to_numpy()
                items[0].setData(x, series)

            elif ind_type == "EMA" and items:
                series = close.ewm(span=period, adjust=False).mean().to_numpy()
                items[0].setData(x, series)

            elif ind_type == "WMA" and items:
                weights = np.arange(1, period + 1, dtype=float)
                series = close.rolling(window=period, min_periods=1).apply(
                    lambda values: np.dot(values, weights[-len(values):]) / weights[-len(values):].sum(),
                    raw=True,
                ).to_numpy()
                items[0].setData(x, series)

            elif ind_type == "VWAP" and items:
                typical_price = (high + low + close) / 3.0
                pv = typical_price * volume
                vwap = pv.rolling(window=period, min_periods=1).sum() / volume.rolling(window=period, min_periods=1).sum().replace(0, np.nan)
                items[0].setData(x, vwap.fillna(method="bfill").fillna(close).to_numpy())

            elif ind_type == "BB" and len(items) == 3:
                mid = close.rolling(window=period, min_periods=1).mean()
                std = close.rolling(window=period, min_periods=1).std().fillna(0.0)
                upper = (mid + 2.0 * std).to_numpy()
                lower = (mid - 2.0 * std).to_numpy()
                items[0].setData(x, mid.to_numpy())
                items[1].setData(x, upper)
                items[2].setData(x, lower)

            elif ind_type == "DONCHIAN" and len(items) == 3:
                upper = high.rolling(window=period, min_periods=1).max()
                lower = low.rolling(window=period, min_periods=1).min()
                mid = (upper + lower) / 2.0
                items[0].setData(x, upper.to_numpy())
                items[1].setData(x, mid.to_numpy())
                items[2].setData(x, lower.to_numpy())

            elif ind_type == "KELTNER" and len(items) == 3:
                prev_close = close.shift(1).fillna(close.iloc[0])
                true_range = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
                atr = true_range.rolling(window=period, min_periods=1).mean()
                mid = close.ewm(span=period, adjust=False).mean()
                upper = mid + (2.0 * atr)
                lower = mid - (2.0 * atr)
                items[0].setData(x, mid.to_numpy())
                items[1].setData(x, upper.to_numpy())
                items[2].setData(x, lower.to_numpy())

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

    def update_candles(self, df):
        if df is None or len(df) == 0:
            return

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return

        x = self._extract_time_axis(df)
        width = self._infer_candle_width(x)

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

        ema = df["close"].astype(float).ewm(span=21, adjust=False).mean().to_numpy()
        self.ema_curve.setData(x, ema)

        volume = df["volume"].astype(float).to_numpy()
        colors = [self.candle_up_color if c >= o else self.candle_down_color for o, c in zip(df["open"], df["close"])]
        brushes = [pg.mkBrush(c) for c in colors]
        self.volume_bars.setOpts(x=x, height=volume, width=width, brushes=brushes)

        self._update_indicators(df, x)

        self.price_plot.enableAutoRange()

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
