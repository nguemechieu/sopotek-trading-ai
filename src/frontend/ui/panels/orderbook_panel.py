from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class OrderBookPanel(QWidget):
    ROWS = 15

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()

        self.table = QTableWidget(self.ROWS, 6)
        self.table.setHorizontalHeaderLabels(
            ["Bid Depth", "Bid Size", "Bid Price", "Ask Price", "Ask Size", "Ask Depth"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table)

        self.setLayout(layout)

    # ------------------------------------

    def update_orderbook(self, bids, asks):
        self.table.clearContents()

        bid_depth = 0.0
        ask_depth = 0.0

        for i, level in enumerate((bids or [])[: self.ROWS]):
            if not isinstance(level, (list, tuple)) or len(level) < 2:
                continue

            price, size = level[0], level[1]
            bid_depth += float(size)

            self._set_item(i, 0, f"{bid_depth:.6f}", QColor("#d8ffea"))
            self._set_item(i, 1, f"{float(size):.6f}", QColor("#b6f5d5"))
            self._set_item(i, 2, f"{float(price):.8f}", QColor("#7ee2a8"))

        for i, level in enumerate((asks or [])[: self.ROWS]):
            if not isinstance(level, (list, tuple)) or len(level) < 2:
                continue

            price, size = level[0], level[1]
            ask_depth += float(size)

            self._set_item(i, 3, f"{float(price):.8f}", QColor("#ff9ea8"))
            self._set_item(i, 4, f"{float(size):.6f}", QColor("#ffd0d5"))
            self._set_item(i, 5, f"{ask_depth:.6f}", QColor("#ffe6e9"))

    def _set_item(self, row, column, value, color):
        item = QTableWidgetItem(value)
        item.setForeground(color)
        self.table.setItem(row, column, item)
