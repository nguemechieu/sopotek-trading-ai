import asyncio
import os

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QMovie, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit,
    QPushButton, QComboBox, QMessageBox,
    QFormLayout, QCheckBox, QLabel,
    QFrame, QSpinBox, QScrollArea
)

from config.credential_manager import CredentialManager
from config.config import AppConfig, BrokerConfig, RiskConfig, SystemConfig


# ------------------------------------------------
# PATHS
# ------------------------------------------------

BASE_DIR = "src"
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

LOGO_PATH = "assets/logo.png"
SPINNER_PATH = "assets/spinner.gif"


# ------------------------------------------------
# EXCHANGE MAP
# ------------------------------------------------

EXCHANGE_MAP = {
    "crypto": [
        "binanceus", "coinbase", "binance",
        "kraken", "kucoin", "bybit",
        "okx", "gateio", "bitget"
    ],
    "forex": ["oanda"],
    "stocks": ["alpaca"],
    "paper": ["paper"]
}


# ======================================================
# DASHBOARD
# ======================================================

class Dashboard(QWidget):

    login_requested = Signal(object)

    def __init__(self, controller):

        super().__init__()

        self.controller = controller

        self.setWindowTitle("Sopotek AI Trading Platform")
        self.resize(600, 720)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ------------------------------------------------
        # HEADER
        # ------------------------------------------------

        logo = QLabel()

        pixmap = QPixmap(LOGO_PATH)

        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    140, 140,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

        logo.setAlignment(Qt.AlignCenter)

        title = QLabel("SOPOTEK TRADING AI PLATFORM")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 18, QFont.Bold))

        subtitle = QLabel("Institutional Algorithmic Trading Infrastructure")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: gray")

        main_layout.addWidget(logo)
        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        # ------------------------------------------------
        # LOGIN CARD
        # ------------------------------------------------

        card = QFrame()
        card.setMaximumWidth(420)

        layout = QVBoxLayout(card)

        form = QFormLayout()

        self.exchange_type_box = QComboBox()
        self.exchange_type_box.addItems(["crypto", "forex", "stocks", "paper"])

        self.exchange_box = QComboBox()

        self.api_input = QLineEdit()

        self.secret_input = QLineEdit()
        self.secret_input.setEchoMode(QLineEdit.Password)

        self.mode_box = QComboBox()
        self.mode_box.addItems(["live", "paper"])

        self.strategy_box = QComboBox()
        self.strategy_box.addItems([
            "LSTM",
            "EMA_CROSS",
            "RSI_MEAN_REVERSION",
            "MACD_TREND"
        ])

        self.risk_input = QSpinBox()
        self.risk_input.setRange(1, 100)
        self.risk_input.setValue(2)

        self.remember_checkbox = QCheckBox("Save Credentials")
        self.remember_checkbox.setChecked(True)

        form.addRow("Broker Type", self.exchange_type_box)
        form.addRow("Exchange", self.exchange_box)
        form.addRow("API Key", self.api_input)
        form.addRow("Secret", self.secret_input)
        form.addRow("Mode", self.mode_box)
        form.addRow("Strategy", self.strategy_box)
        form.addRow("Risk %", self.risk_input)
        form.addRow("", self.remember_checkbox)

        layout.addLayout(form)

        self.connect_button = QPushButton("CONNECT")
        self.connect_button.setFixedHeight(40)

        layout.addWidget(self.connect_button)

        main_layout.addWidget(card, alignment=Qt.AlignCenter)

        # ------------------------------------------------
        # LOADING SPINNER
        # ------------------------------------------------

        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)
        self.spinner.setVisible(False)

        self.spinner_movie = QMovie(SPINNER_PATH)
        self.spinner.setMovie(self.spinner_movie)

        main_layout.addWidget(self.spinner)

        # ------------------------------------------------
        # SIGNALS
        # ------------------------------------------------

        self.exchange_type_box.currentTextChanged.connect(
            self._update_exchange_list
        )

        self.connect_button.clicked.connect(self._on_connect)

        # ------------------------------------------------
        # INIT
        # ------------------------------------------------

        self._update_exchange_list(self.exchange_type_box.currentText())

        # auto load saved credentials
        self._load_last_account()

    # ======================================================
    # LOAD SAVED ACCOUNT
    # ======================================================

    def _load_last_account(self):

        accounts = CredentialManager.list_accounts()

        if not accounts:
            return

        name = accounts[0]

        creds = CredentialManager.load_account(name)

        if not creds:
            return

        broker = creds["broker"]

        self.exchange_type_box.setCurrentText(broker["type"])

        self._update_exchange_list(broker["type"])

        self.exchange_box.setCurrentText(broker["exchange"])

        self.api_input.setText(broker.get("api_key", ""))
        self.secret_input.setText(broker.get("secret", ""))

        self.mode_box.setCurrentText(broker.get("mode", "paper"))

        self.risk_input.setValue(
            creds.get("risk", {}).get("risk_percent", 2)
        )

        self.strategy_box.setCurrentText(
            creds.get("strategy", "EMA_CROSS")
        )

    # ======================================================
    # EXCHANGE LIST
    # ======================================================

    def _update_exchange_list(self, exchange_type):

        self.exchange_box.clear()

        exchanges = EXCHANGE_MAP.get(exchange_type, [])

        self.exchange_box.addItems(exchanges)

    # ======================================================
    # CONNECT
    # ======================================================

    def _on_connect(self):

        exchange = self.exchange_box.currentText()
        api_key = self.api_input.text().strip()
        secret = self.secret_input.text().strip()

        if exchange != "paper" and not api_key:

            QMessageBox.warning(
                self,
                "Missing Credentials",
                "API credentials required."
            )

            return

        broker_config = BrokerConfig(
            type=self.exchange_type_box.currentText(),
            exchange=exchange,
            mode=self.mode_box.currentText(),
            api_key=api_key,
            secret=secret
        )

        config = AppConfig(
            broker=broker_config,
            risk=RiskConfig(
                risk_percent=self.risk_input.value()
            ),
            system=SystemConfig(),
            strategy=self.strategy_box.currentText()
        )

        if self.remember_checkbox.isChecked():

            name = f"{exchange}_{api_key[:6] if api_key else 'paper'}"

            CredentialManager.save_account(name, config.dict())

        self.show_loading()

        self.login_requested.emit(config)

    # ======================================================
    # LOADING UI
    # ======================================================

    def show_loading(self):

        self.connect_button.setEnabled(False)
        self.connect_button.setText("CONNECTING...")

        self.spinner.setVisible(True)

        self.spinner_movie.start()

    def hide_loading(self):

        self.spinner.setVisible(False)

        self.spinner_movie.stop()

        self.connect_button.setEnabled(True)
        self.connect_button.setText("CONNECT")