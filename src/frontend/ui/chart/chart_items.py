import pyqtgraph as pg
from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QPen


class CandlestickItem(pg.GraphicsObject):
    """Fast candlestick renderer for OHLC arrays.

    Expected rows: [x, open, close, low, high]
    """

    def __init__(self, body_width: float = 0.7, up_color: str = "#26a69a", down_color: str = "#ef5350"):
        super().__init__()
        self.body_width = float(body_width)
        self.up_color = up_color
        self.down_color = down_color
        self.picture = pg.QtGui.QPicture()
        self._bounding_rect = QRectF(0, 0, 1, 1)

    def set_colors(self, up_color: str, down_color: str):
        self.up_color = up_color
        self.down_color = down_color

    def set_body_width(self, body_width: float):
        self.body_width = max(1e-9, float(body_width))

    def setData(self, data):
        self.generatePicture(data)
        self.update()

    def generatePicture(self, data):
        self.picture = pg.QtGui.QPicture()
        painter = pg.QtGui.QPainter(self.picture)

        up_pen = QPen(pg.mkColor(self.up_color))
        up_brush = QBrush(pg.mkColor(self.up_color))
        down_pen = QPen(pg.mkColor(self.down_color))
        down_brush = QBrush(pg.mkColor(self.down_color))

        min_x = float("inf")
        max_x = float("-inf")
        min_y = float("inf")
        max_y = float("-inf")

        rows = data if data is not None else []
        for row in rows:
            if len(row) < 5:
                continue
            t, open_, close, low, high = map(float, row[:5])

            is_up = close >= open_
            painter.setPen(up_pen if is_up else down_pen)
            painter.setBrush(up_brush if is_up else down_brush)

            painter.drawLine(pg.QtCore.QPointF(t, low), pg.QtCore.QPointF(t, high))

            top = min(open_, close)
            height = abs(close - open_)
            if height < 1e-9:
                height = 1e-9

            rect = QRectF(t - self.body_width / 2.0, top, self.body_width, height)
            painter.drawRect(rect)

            min_x = min(min_x, t - self.body_width)
            max_x = max(max_x, t + self.body_width)
            min_y = min(min_y, low)
            max_y = max(max_y, high)

        painter.end()

        if min_x == float("inf"):
            self._bounding_rect = QRectF(0, 0, 1, 1)
        else:
            self._bounding_rect = QRectF(min_x, min_y, max_x - min_x, max(max_y - min_y, 1e-9))

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return self._bounding_rect
