import numpy as np
from PySide6 import QtCore
from PySide6.QtWidgets import QTabWidget

from pyqtgraph import GraphicsLayoutWidget, ScatterPlotItem, mkPen, ImageItem, InfiniteLine, TextItem, SignalProxy



import pyqtgraph as pg

from sopotek_trading.frontend.ui.chart.chart_items import CandlestickItem


class ChartWidget(GraphicsLayoutWidget):
    sigMouseMoved = QtCore.Signal(object)

    def __init__(self, symbol: str, timeframe: str):
        super().__init__()

        self.chart_tabs = QTabWidget()
        self._mouse_moved = None
        self.symbol = symbol
        self.timeframe = timeframe
        self.setBackground("k")

        self.ohlcv_data = []
        self.last_index = -1
        self.heatmap_buffer = []
        self.max_heatmap_rows = 200

        # ===============================
        # 1️⃣ PRICE PLOT (ROW 0)
        # ===============================
        self.price_plot = self.addPlot(row=0, col=0)
        self.price_plot.showGrid(x=True, y=True)
        self.price_plot.setLabel("right", "Price")
        self.price_plot.setLabel("bottom", "Time")

        self.candle_item = CandlestickItem()
        self.price_plot.addItem(self.candle_item)

        self.ema_curve = self.price_plot.plot(
            pen=mkPen("yellow", width=2)
        )

        self.trade_scatter = ScatterPlotItem()
        self.price_plot.addItem(self.trade_scatter)

        # ===============================
        # 2️⃣ VOLUME PLOT (ROW 1)
        # ===============================
        self.volume_plot = self.addPlot(row=1, col=0)

        self.volume_plot.showGrid(x=True, y=True)
        self.volume_plot.setXLink(self.price_plot)
        self.volume_plot.setYLink(self.volume_plot)
        self.volume_plot.setLabel("bottom", "Volume")
        self.volume_plot.setLabel("left", "Time")
        self.volume_bars = self.price_plot.plot()

        self.volume_bars = pg.BarGraphItem(
            x=[], height=[], width=0.6, brush="b"
        )
        self.volume_plot.addItem(self.volume_bars)

        # ===============================
        # 3️⃣ HEATMAP PLOT (ROW 2)
        # # ===============================
        # self.heatmap_plot = self.addPlot(row=2, col=0)
        # self.heatmap_plot.showGrid(x=True, y=True)
        # self.heatmap_plot.setXLink(self.price_plot)
        #
        # colormap = pg.colormap.get("inferno")
        # self.heatmap_image = ImageItem()
        # self.heatmap_image.setLookupTable(
        #     colormap.getLookupTable()
        # )
        # self.heatmap_plot.addItem(self.heatmap_image)

        # ===============================
        # CROSSHAIR
        # ===============================
        self.v_line = InfiniteLine(
            angle=90, movable=False, pen="y"
        )
        self.h_line = InfiniteLine(
            angle=0, movable=False, pen="y"
        )

        self.price_plot.addItem(
            self.v_line, ignoreBounds=True
        )
        self.price_plot.addItem(
            self.h_line, ignoreBounds=True
        )

        self.text_item = TextItem(color="w")
        self.price_plot.addItem(self.text_item)

        self.proxy = SignalProxy(
            self.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._mouse_moved
        )

        # Set layout proportions
        self.ci.layout.setRowStretchFactor(0, 25)  # Price dominant
        self.ci.layout.setRowStretchFactor(1, 2)  # Volume smaller
        self.ci.layout.setRowStretchFactor(2, 2)  # Heatmap smaller
        self.signal_markers = pg.ScatterPlotItem()
        self.price_plot.addItem(self.signal_markers)




    def update_orderbook_heatmap(self, bids, asks):

     if not bids or not asks:
        return

     volumes = []

     for price, volume in bids + asks:
        volumes.append(float(volume))

     if not volumes:
        return

     max_vol = max(volumes)
     normalized = [v / max_vol for v in volumes]

     self.heatmap_buffer.append(normalized)

     if len(self.heatmap_buffer) > self.max_heatmap_rows:
        self.heatmap_buffer.pop(0)

     heatmap_array = np.array(self.heatmap_buffer).T

     self.heatmap_image.setImage(
        heatmap_array,
        autoLevels=False
    )

    def link_all_charts(self,count):

     charts = []

     for i in range(count):
        widget = self.chart_tabs.widget(i)

        if isinstance(widget, ChartWidget):
            charts.append(widget)

     if len(charts) < 2:
        return

     base = charts[0]

     for chart in charts[1:]:
        chart.link_to(base)


    def add_strategy_signal(self, index, price, signal):

     if signal == "BUY":
        symbol = "t1"
        color = "green"
     elif signal == "SELL":
        symbol = "t"
        color = "red"
     else:
        return

     self.signal_markers.addPoints(
        x=[index],
        y=[price],
        symbol=symbol,
        brush=color,
        size=14
    )

    def update_candles(self, df):
        pass

