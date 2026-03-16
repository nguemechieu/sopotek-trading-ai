import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.panels.trading_panels import (
    OPEN_ORDER_HEADERS,
    POSITION_HEADERS,
    TRADE_LOG_HEADERS,
    create_open_orders_panel,
    create_positions_panel,
    create_trade_log_panel,
)


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class DummyTerminal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.close_all_requests = 0

    def _action_button_style(self):
        return ""

    def _close_all_positions(self):
        self.close_all_requests += 1


def test_create_positions_panel_builds_table_and_action_button():
    _app()
    terminal = DummyTerminal()

    create_positions_panel(terminal)
    terminal.positions_close_all_button.click()

    assert terminal.close_all_requests == 1
    assert terminal.positions_table.columnCount() == len(POSITION_HEADERS)
    assert [
        terminal.positions_table.horizontalHeaderItem(index).text()
        for index in range(terminal.positions_table.columnCount())
    ] == POSITION_HEADERS


def test_create_open_orders_panel_builds_expected_columns():
    _app()
    terminal = DummyTerminal()

    create_open_orders_panel(terminal)

    assert terminal.open_orders_table.columnCount() == len(OPEN_ORDER_HEADERS)
    assert [
        terminal.open_orders_table.horizontalHeaderItem(index).text()
        for index in range(terminal.open_orders_table.columnCount())
    ] == OPEN_ORDER_HEADERS


def test_create_trade_log_panel_builds_expected_columns():
    _app()
    terminal = DummyTerminal()

    create_trade_log_panel(terminal)

    assert terminal.trade_log.columnCount() == len(TRADE_LOG_HEADERS)
    assert [
        terminal.trade_log.horizontalHeaderItem(index).text()
        for index in range(terminal.trade_log.columnCount())
    ] == TRADE_LOG_HEADERS
