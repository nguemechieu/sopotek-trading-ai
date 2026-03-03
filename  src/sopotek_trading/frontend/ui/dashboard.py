from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QMovie
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit,
    QPushButton, QComboBox, QMessageBox,
    QFormLayout, QCheckBox, QLabel,
    QFrame, QSpinBox
)

from sopotek_trading.backend.services.credential_manager import CredentialManager


class Dashboard(QWidget):

    login_success = Signal(dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sopotek AI Trading Platform")
        self.resize(650, 720)
        self.setStyleSheet(self._get_styles())

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        # Spinner
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)
        self.spinner.setVisible(False)

        self.spinner_movie = QMovie("../assets/spinner.gif")  # optional gif
        self.spinner.setMovie(self.spinner_movie)

        main_layout.addWidget(self.spinner)

        # ======================================================
        # LOGO
        # ======================================================
        logo = QLabel("🚀")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(QFont("Arial", 50))
        main_layout.addWidget(logo)

        title = QLabel("SOPOTEK AI TRADING PLATFORM")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 20, QFont.Bold))
        main_layout.addWidget(title)

        subtitle = QLabel("Institutional-Grade Algorithmic Infrastructure")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: gray;")
        main_layout.addWidget(subtitle)

        # ======================================================
        # LOGIN CARD
        # ======================================================
        card = QFrame()
        card.setFixedWidth(500)
        card.setObjectName("loginCard")

        layout = QVBoxLayout(card)
        form = QFormLayout()

        # Exchange
        self.exchange_box = QComboBox()
        self.exchange_box.addItems([
            "binance", "binanceus", "coinbase",
            "kraken", "kucoin", "bybit",
            "okx", "gateio", "bitget", "oanda"
        ])
        form.addRow("Exchange:", self.exchange_box)

        # API
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Enter API Key")
        form.addRow("API Key:", self.api_input)

        # Secret
        self.secret_input = QLineEdit()
        self.secret_input.setEchoMode(QLineEdit.Password)
        self.secret_input.setPlaceholderText("Enter Secret Key")
        form.addRow("Secret:", self.secret_input)

        # Mode
        self.mode_box = QComboBox()
        self.mode_box.addItems(["paper", "live"])
        form.addRow("Mode:", self.mode_box)






        # Strategy
        self.strategy_box = QComboBox()
        self.strategy_box.addItems([
            "LSTM",
            "EMA_CROSS",
            "RSI_MEAN_REVERSION",
            "MACD_TREND"
        ])
        form.addRow("Strategy:", self.strategy_box)

        # Risk %
        self.risk_input = QSpinBox()
        self.risk_input.setRange(1, 10)
        self.risk_input.setValue(2)
        form.addRow("Risk % per Trade:", self.risk_input)

        # Remember
        self.remember_checkbox = QCheckBox("Remember Credentials")
        form.addRow("", self.remember_checkbox)

        layout.addLayout(form)

        # Connect Button
        self.connect_button = QPushButton("CONNECT")
        self.connect_button.setFixedHeight(45)
        layout.addWidget(self.connect_button)

        main_layout.addSpacing(20)
        main_layout.addWidget(card, alignment=Qt.AlignCenter)

        # SIGNALS
        self.connect_button.clicked.connect(self._on_connect)
        self.exchange_box.currentTextChanged.connect(
            self._load_saved_credentials
        )

        self._load_saved_credentials(
            self.exchange_box.currentText()
        )

    # ======================================================
    # STYLE
    # ======================================================

    def _get_styles(self):
        return """
        QWidget {
            background-color: #0f1115;
            color: white;
            font-size: 14px;
        }

        QFrame#loginCard {
            background-color: #1c1f26;
            border-radius: 12px;
            padding: 25px;
        }

        QLineEdit, QComboBox, QSpinBox {
            background-color: #2a2e38;
            border: 1px solid #3a3f4b;
            border-radius: 6px;
            padding: 6px;
        }

        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #0078d7;
        }

        QPushButton {
            background-color: #0078d7;
            border-radius: 6px;
            font-weight: bold;
        }

        QPushButton:hover {
            background-color: #0095ff;
        }
        """

    # ======================================================
    # LOAD CREDENTIALS
    # ======================================================

    def _load_saved_credentials(self, exchange):

        api_key, secret = CredentialManager.load_credentials(exchange)

        self.api_input.setText(api_key or "")
        self.secret_input.setText(secret or "")
        self.remember_checkbox.setChecked(
            bool(api_key and secret)
        )

    # ======================================================
    # CONNECT
    # ======================================================

    def _on_connect(self):

        exchange = self.exchange_box.currentText()
        api_key = self.api_input.text().strip()
        secret = self.secret_input.text().strip()
        mode = self.mode_box.currentText()

        strategy = self.strategy_box.currentText()
        risk_percent = self.risk_input.value()




        if not api_key or not secret:
            QMessageBox.warning(
                self,
                "Missing Credentials",
                "API Key and Secret are required."
            )
            return

        if mode == "live":
            confirm = QMessageBox.question(
                self,
                "Live Trading Warning",
                "You are about to enable LIVE trading.\nContinue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

        if self.remember_checkbox.isChecked():
            CredentialManager.save_credentials(
                exchange,
                api_key,
                secret
            )
        else:
            CredentialManager.delete_credentials(exchange)

        config = {
            "type": "crypto",
            "mode": mode,
            "strategy": strategy,
            "limit":1000,
            "equity_refresh":60,
            "risk_percent": risk_percent,
            "credentials": {
                "api_key": api_key,
                "secret": secret,
                "account_id": 1234,
            },
            "options": {
                "exchange": exchange,
                "rate_limit": 6
            }
        }

        self.connect_button.setText("CONNECTING...")
        self.connect_button.setEnabled(False)

        self.login_success.emit(config)

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