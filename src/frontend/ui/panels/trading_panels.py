from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QPushButton, QTableWidget, QVBoxLayout, QWidget


POSITION_HEADERS = ["Symbol", "Side", "Amount", "Entry", "Mark", "Value", "PnL", "Action"]
OPEN_ORDER_HEADERS = [
    "Symbol",
    "Side",
    "Type",
    "Price",
    "Mark",
    "Amount",
    "Filled",
    "Remaining",
    "Status",
    "PnL",
    "Order ID",
]
TRADE_LOG_HEADERS = [
    "Timestamp",
    "Symbol",
    "Source",
    "Side",
    "Price",
    "Size",
    "Order Type",
    "Status",
    "Order ID",
    "PnL",
]


def create_positions_panel(terminal):
    dock = QDockWidget("Positions", terminal)
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    actions = QHBoxLayout()
    actions.setContentsMargins(0, 0, 0, 0)
    actions.addStretch()
    close_all_btn = QPushButton("Close All Positions")
    close_all_btn.setStyleSheet(terminal._action_button_style())
    close_all_btn.clicked.connect(terminal._close_all_positions)
    actions.addWidget(close_all_btn)
    layout.addLayout(actions)

    terminal.positions_table = QTableWidget()
    terminal.positions_table.setColumnCount(len(POSITION_HEADERS))
    terminal.positions_table.setHorizontalHeaderLabels(POSITION_HEADERS)
    layout.addWidget(terminal.positions_table)
    dock.setWidget(container)
    terminal.positions_close_all_button = close_all_btn
    terminal.addDockWidget(Qt.BottomDockWidgetArea, dock)
    return dock


def create_open_orders_panel(terminal):
    dock = QDockWidget("Open Orders", terminal)
    terminal.open_orders_table = QTableWidget()
    terminal.open_orders_table.setColumnCount(len(OPEN_ORDER_HEADERS))
    terminal.open_orders_table.setHorizontalHeaderLabels(OPEN_ORDER_HEADERS)
    dock.setWidget(terminal.open_orders_table)
    terminal.addDockWidget(Qt.BottomDockWidgetArea, dock)
    return dock


def create_trade_log_panel(terminal):
    dock = QDockWidget("Trade Log", terminal)
    terminal.trade_log = QTableWidget()
    terminal.trade_log.setColumnCount(len(TRADE_LOG_HEADERS))
    terminal.trade_log.setHorizontalHeaderLabels(TRADE_LOG_HEADERS)
    dock.setWidget(terminal.trade_log)
    terminal.addDockWidget(Qt.RightDockWidgetArea, dock)
    return dock
