from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem


class OrderBookPanel(QWidget):

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()

        self.table = QTableWidget(20, 2)
        self.table.setHorizontalHeaderLabels(["Bid", "Ask"])

        layout.addWidget(self.table)

        self.setLayout(layout)

    # ------------------------------------

    def update_orderbook(self, bids, asks):

        for i, (price, size) in enumerate(bids[:10]):
            self.table.setItem(i, 0, QTableWidgetItem(str(price)))

        for i, (price, size) in enumerate(asks[:10]):
            self.table.setItem(i, 1, QTableWidgetItem(str(price)))
