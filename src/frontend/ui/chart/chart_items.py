import pyqtgraph as pg
from PySide6.QtGui import QBrush, QPen
from PySide6.QtCore import QRectF


class CandlestickItem(pg.GraphicsObject):

    def __init__(self):
        super().__init__()
        self.picture = None
        self.generatePicture([])

    def generatePicture(self, data):
        """
        data format:
        [
            (index, open, high, low, close),
            ...
        ]
        """
        self.picture = pg.QtGui.QPicture()
        painter = pg.QtGui.QPainter(self.picture)

        for (t, open_, high, low, close) in data:

            if close >= open_:
                painter.setPen(QPen(pg.mkColor("g")))
                painter.setBrush(QBrush(pg.mkColor("g")))
            else:
                painter.setPen(QPen(pg.mkColor("r")))
                painter.setBrush(QBrush(pg.mkColor("r")))

            # Wick
            painter.drawLine(pg.QtCore.QPointF(t, low),
                             pg.QtCore.QPointF(t, high))

            # Body
            rect = QRectF(
                t - 0.3,
                open_,
                0.6,
                close - open_
            )
            painter.drawRect(rect)

        painter.end()


    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())