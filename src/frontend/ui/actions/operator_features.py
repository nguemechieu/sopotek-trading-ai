import json
import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QMessageBox,
)


WORKSPACE_DOCKS = (
    "market_watch_dock",
    "positions_dock",
    "trade_log_dock",
    "orderbook_dock",
    "strategy_scorecard_dock",
    "strategy_debug_dock",
    "risk_heatmap_dock",
    "ai_signal_dock",
    "system_console_dock",
    "system_status_dock",
)
TOOL_WINDOWS = {
    "performance_analytics",
    "closed_trade_journal",
    "trade_journal_review",
    "portfolio_exposure",
    "position_analysis",
    "trade_recommendations",
    "quant_pm",
    "system_health",
    "trade_checklist",
    "market_chat",
    "ml_monitor",
    "logs",
    "notification_center",
}
WORKSPACE_PRESETS = {
    "trading": {
        "docks": {"market_watch_dock", "positions_dock", "trade_log_dock", "orderbook_dock", "system_status_dock", "system_console_dock"},
        "tools": [],
    },
    "research": {
        "docks": {"market_watch_dock", "orderbook_dock", "strategy_scorecard_dock", "strategy_debug_dock", "ai_signal_dock", "system_console_dock"},
        "tools": ["trade_recommendations", "quant_pm"],
    },
    "risk": {
        "docks": {"positions_dock", "orderbook_dock", "risk_heatmap_dock", "system_status_dock", "system_console_dock"},
        "tools": ["portfolio_exposure", "position_analysis"],
    },
    "review": {
        "docks": {"positions_dock", "trade_log_dock", "ai_signal_dock", "system_console_dock", "system_status_dock"},
        "tools": ["performance_analytics", "closed_trade_journal", "notification_center"],
    },
}


def install_terminal_operator_features(Terminal):
    if getattr(Terminal, "_operator_features_installed", False):
        return

    orig_create_menu_bar = Terminal._create_menu_bar
    orig_update_symbols = Terminal._update_symbols
    orig_update_trade_log = Terminal._update_trade_log
    orig_update_connection_status = Terminal.update_connection_status
    orig_refresh_terminal = Terminal._refresh_terminal
    orig_restore_settings = Terminal._restore_settings
    orig_close_event = Terminal.closeEvent
    orig_submit_manual_trade_from_ticket = Terminal._submit_manual_trade_from_ticket
    orig_manual_trade_default_payload = Terminal._manual_trade_default_payload
    orig_show_async_message = Terminal._show_async_message
    orig_handle_chart_trade_context_action = Terminal._handle_chart_trade_context_action
    orig_on_chart_tab_changed = Terminal._on_chart_tab_changed

    def workspace_context_key(self):
        controller = getattr(self, "controller", None)
        exchange = "default"
        account = "default"
        if controller is not None:
            exchange_getter = getattr(controller, "_active_exchange_code", None)
            account_getter = getattr(controller, "current_account_label", None)
            try:
                exchange = str(exchange_getter() if callable(exchange_getter) else getattr(controller, "exchange_name", "default") or "default")
            except Exception:
                exchange = str(getattr(controller, "exchange_name", "default") or "default")
            try:
                account = str(account_getter() if callable(account_getter) else getattr(controller, "account_label", "default") or "default")
            except Exception:
                account = str(getattr(controller, "account_label", "default") or "default")
        value = f"{exchange}__{account}".lower().strip()
        for old, new in (("/", "_"), ("\\", "_"), (":", "_"), (" ", "_"), ("-", "_")):
            value = value.replace(old, new)
        value = "_".join(part for part in value.split("_") if part)
        return value or "default"

    def workspace_settings_prefix(self, slot="last"):
        slot_name = str(slot or "last").strip().lower() or "last"
        return f"workspace_layout/{self._workspace_context_key()}/{slot_name}"

    def favorite_symbols_storage_key(self):
        return f"trader_memory/{self._workspace_context_key()}/favorite_symbols"

    def manual_trade_template_storage_key(self):
        return f"trader_memory/{self._workspace_context_key()}/manual_trade_template"

    def ensure_notification_state(self):
        if not isinstance(getattr(self, "_notification_records", None), list):
            self._notification_records = []
        if not isinstance(getattr(self, "_notification_dedupe_cache", None), dict):
            self._notification_dedupe_cache = {}
        if not isinstance(getattr(self, "_runtime_notification_state", None), dict):
            self._runtime_notification_state = {}
        return self._notification_records

    def refresh_notification_action_text(self):
        action = getattr(self, "action_notifications", None)
        if action is None:
            return
        records = self._ensure_notification_state()
        count = len(list(records or []))
        action.setText("Notification Center" if count <= 0 else f"Notification Center ({count})")

    def push_notification(self, title, message, level="INFO", source="system", dedupe_seconds=20.0):
        self._ensure_notification_state()
        title_text = str(title or "").strip() or "Notification"
        message_text = str(message or "").strip()
        level_text = str(level or "INFO").strip().upper() or "INFO"
        source_text = str(source or "system").strip().lower() or "system"
        now = time.time()
        fingerprint = (title_text, message_text, level_text, source_text)
        cooldown = max(float(dedupe_seconds or 0.0), 0.0)
        last_seen = self._notification_dedupe_cache.get(fingerprint)
        if last_seen is not None and cooldown > 0 and (now - float(last_seen)) < cooldown:
            return None
        self._notification_dedupe_cache[fingerprint] = now
        created_at = datetime.now().astimezone()
        self._notification_records.append(
            {
                "id": int(now * 1000),
                "timestamp": now,
                "time_text": created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": created_at.isoformat(),
                "title": title_text,
                "message": message_text,
                "level": level_text,
                "source": source_text,
            }
        )
        if len(self._notification_records) > 400:
            del self._notification_records[:-400]
        refresh_notification_action_text(self)
        window = (getattr(self, "detached_tool_windows", {}) or {}).get("notification_center")
        if self._is_qt_object_alive(window):
            refresh_notification_center_window(self, window)
        return self._notification_records[-1]

    def refresh_notification_center_window(self, window=None):
        window = window or (getattr(self, "detached_tool_windows", {}) or {}).get("notification_center")
        if not self._is_qt_object_alive(window):
            return
        table = getattr(window, "_notification_table", None)
        filter_input = getattr(window, "_notification_filter", None)
        summary = getattr(window, "_notification_summary", None)
        if table is None or filter_input is None or summary is None:
            return
        query = str(filter_input.text() or "").strip().lower()
        rows = []
        for record in reversed(list(self._ensure_notification_state() or [])):
            haystack = " ".join(str(record.get(key, "") or "") for key in ("title", "message", "level", "source", "time_text")).lower()
            if query and query not in haystack:
                continue
            rows.append(record)
        table.setRowCount(len(rows))
        colors = {
            "INFO": QColor("#74c0fc"),
            "WARN": QColor("#ffd166"),
            "WARNING": QColor("#ffd166"),
            "ERROR": QColor("#ff7b72"),
            "CRITICAL": QColor("#ff5d73"),
        }
        for row_index, record in enumerate(rows):
            values = [record.get("time_text", "-"), record.get("level", "INFO"), record.get("title", "Notification"), record.get("message", "")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(record.get("message", "") or ""))
                if column == 1:
                    item.setForeground(colors.get(str(record.get("level", "INFO")).upper(), QColor("#d8e6ff")))
                table.setItem(row_index, column, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        summary.setText(f"{len(rows)} notifications shown for {self._workspace_context_key().replace('__', ' / ')}.")
        refresh_notification_action_text(self)

    def open_notification_center(self):
        window = self._get_or_create_tool_window("notification_center", "Notification Center", width=860, height=560)
        if getattr(window, "_notification_container", None) is None:
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)
            summary = QLabel("Notifications collect fills, rejects, disconnects, stale market-data warnings, and guard events.")
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #d9e6f7; background-color: #101a2d; border: 1px solid #20324d; border-radius: 12px; padding: 10px;")
            layout.addWidget(summary)
            controls = QHBoxLayout()
            filter_input = QLineEdit()
            filter_input.setPlaceholderText("Filter notifications")
            filter_input.textChanged.connect(lambda *_: self._refresh_notification_center_window(window))
            controls.addWidget(filter_input, 1)
            clear_btn = QPushButton("Clear")
            clear_btn.clicked.connect(lambda: (setattr(self, "_notification_records", []), refresh_notification_action_text(self), self._refresh_notification_center_window(window)))
            controls.addWidget(clear_btn)
            layout.addLayout(controls)
            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["Time", "Level", "Event", "Details"])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            layout.addWidget(table, 1)
            window.setCentralWidget(container)
            window._notification_container = container
            window._notification_summary = summary
            window._notification_filter = filter_input
            window._notification_table = table
        self._refresh_notification_center_window(window)
        window.show()
        window.raise_()
        window.activateWindow()
        if getattr(window, "_notification_filter", None) is not None:
            window._notification_filter.setFocus()
        return window

    def record_trade_notification(self, trade):
        if not isinstance(trade, dict):
            return None
        symbol = str(trade.get("symbol") or "").strip() or "Unknown symbol"
        status = str(trade.get("status") or "").strip().lower()
        side = str(trade.get("side") or "").strip().upper() or "TRADE"
        size = trade.get("size", trade.get("amount", "-"))
        price = trade.get("price", trade.get("mark", "-"))
        reason_text = " ".join(str(trade.get(key) or "") for key in ("reason", "outcome", "status", "source")).lower()
        pnl = self._safe_float(trade.get("pnl"))
        details = f"{symbol} | {side} | size {size} | price {price}"
        if pnl is not None:
            details += f" | PnL {pnl:.2f}"
        if "stop" in reason_text:
            return self._push_notification("Stop hit", details, level="WARN", source="trade", dedupe_seconds=10.0)
        if any(token in status for token in ("reject", "fail", "error")) or trade.get("blocked_by_guard"):
            return self._push_notification("Order rejected", details, level="ERROR", source="trade", dedupe_seconds=10.0)
        if any(token in status for token in ("fill", "executed", "closed")):
            return self._push_notification("Order filled", details, level="INFO", source="trade", dedupe_seconds=10.0)
        return None

    def runtime_notification_transition(self, key, fingerprint, title, message, level="WARN", source="runtime"):
        state = getattr(self, "_runtime_notification_state", None)
        if not isinstance(state, dict):
            state = {}
            self._runtime_notification_state = state
        if fingerprint in (None, "", False):
            state.pop(key, None)
            return
        if state.get(key) != fingerprint:
            state[key] = fingerprint
            self._push_notification(title, message, level=level, source=source, dedupe_seconds=30.0)

    def refresh_runtime_notifications(self):
        controller = getattr(self, "controller", None)
        if controller is None:
            return
        broker_snapshot = dict(getattr(self, "_latest_broker_status_snapshot", {}) or {})
        broker_summary = str(broker_snapshot.get("summary") or "").strip()
        broker_detail = str(broker_snapshot.get("detail") or "").strip()
        broker_text = f"{broker_summary} {broker_detail}".lower()
        fingerprint = None
        if broker_text and any(token in broker_text for token in ("disconnect", "offline", "fail", "error", "unauthorized", "denied")):
            fingerprint = f"{broker_summary}|{broker_detail}"
        self._runtime_notification_transition(
            "broker_api",
            fingerprint,
            "API disconnected",
            broker_detail or broker_summary or "The broker API is unavailable.",
            level="ERROR",
            source="broker",
        )
        notices = getattr(controller, "_market_data_shortfall_notices", {}) or {}
        stale_fingerprint = None
        stale_message = ""
        if isinstance(notices, dict) and notices:
            try:
                (symbol, timeframe), (received, requested) = next(iter(notices.items()))
                stale_fingerprint = f"{symbol}|{timeframe}|{received}|{requested}"
                stale_message = f"{symbol} {timeframe}: received {received} of {requested} requested candles."
            except Exception:
                stale_fingerprint = f"{len(notices)}-shortfalls"
                stale_message = "Recent candle history is incomplete for one or more symbols."
        else:
            market_status = ""
            if hasattr(controller, "get_market_stream_status"):
                try:
                    market_status = str(controller.get_market_stream_status() or "")
                except Exception:
                    market_status = ""
            if market_status.strip().lower() == "stopped":
                stale_fingerprint = "stream-stopped"
                stale_message = "Live market data is currently stopped."
        self._runtime_notification_transition(
            "stale_market_data",
            stale_fingerprint,
            "Stale market data",
            stale_message,
            level="WARN",
            source="market-data",
        )
        behavior = {}
        if hasattr(controller, "get_behavior_guard_status"):
            try:
                behavior = controller.get_behavior_guard_status() or {}
            except Exception:
                behavior = {}
        summary = str(behavior.get("summary") or "").strip()
        reason = str(behavior.get("reason") or "").strip()
        behavior_fingerprint = None
        if summary and summary.lower() not in {"not active", "inactive", "disabled", "off"}:
            behavior_fingerprint = f"{summary}|{reason}"
        self._runtime_notification_transition(
            "behavior_guard",
            behavior_fingerprint,
            "Behavior guard active",
            reason or summary or "The behavior guard is actively constraining trading behavior.",
            level="WARN",
            source="risk",
        )

    def visible_tool_window_keys(self):
        visible = []
        for key, window in (getattr(self, "detached_tool_windows", {}) or {}).items():
            if key not in TOOL_WINDOWS or not self._is_qt_object_alive(window):
                continue
            try:
                if window.isVisible():
                    visible.append(key)
            except Exception:
                continue
        return sorted(set(visible))

    def save_workspace_layout(self, slot="last"):
        settings = getattr(self, "settings", None)
        if settings is None:
            return False
        prefix = self._workspace_settings_prefix(slot)
        settings.setValue(f"{prefix}/geometry", self.saveGeometry())
        settings.setValue(f"{prefix}/windowState", self.saveState())
        visible_docks = []
        for attr_name in WORKSPACE_DOCKS:
            dock = getattr(self, attr_name, None)
            if self._is_qt_object_alive(dock) and dock.isVisible():
                visible_docks.append(attr_name)
        settings.setValue(f"{prefix}/visible_docks", json.dumps(sorted(visible_docks)))
        settings.setValue(f"{prefix}/open_tools", json.dumps(self._visible_tool_window_keys()))
        return True

    def restore_workspace_layout(self, slot="last"):
        settings = getattr(self, "settings", None)
        if settings is None:
            return False
        prefix = self._workspace_settings_prefix(slot)
        geometry = settings.value(f"{prefix}/geometry")
        state = settings.value(f"{prefix}/windowState")
        visible_docks_raw = settings.value(f"{prefix}/visible_docks", "")
        open_tools_raw = settings.value(f"{prefix}/open_tools", "")
        if all(value in (None, "") for value in (geometry, state, visible_docks_raw, open_tools_raw)):
            return False
        if geometry not in (None, ""):
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass
        if state not in (None, ""):
            try:
                self.restoreState(state)
            except Exception:
                pass
        try:
            visible_docks = set(json.loads(visible_docks_raw or "[]"))
        except Exception:
            visible_docks = set()
        if visible_docks:
            for attr_name in WORKSPACE_DOCKS:
                dock = getattr(self, attr_name, None)
                if not self._is_qt_object_alive(dock):
                    continue
                dock.show() if attr_name in visible_docks else dock.hide()
        try:
            open_tools = set(json.loads(open_tools_raw or "[]"))
        except Exception:
            open_tools = set()
        for key in open_tools:
            self._open_tool_window_by_key(key)
        for key, window in list((getattr(self, "detached_tool_windows", {}) or {}).items()):
            if key in TOOL_WINDOWS and key not in open_tools and self._is_qt_object_alive(window):
                try:
                    window.hide()
                except Exception:
                    pass
        self._queue_terminal_layout_fit()
        self._refresh_symbol_picker_favorites()
        self._update_favorite_action_text()
        return True

    def save_current_workspace_layout(self):
        saved = self._save_workspace_layout("saved")
        if hasattr(self, "system_console"):
            self.system_console.log("Workspace layout saved for the current broker/account." if saved else "Workspace layout could not be saved.", "INFO" if saved else "WARN")
        return saved

    def restore_saved_workspace_layout(self):
        restored = self._restore_workspace_layout("saved")
        if hasattr(self, "system_console"):
            self.system_console.log("Saved workspace layout restored." if restored else "No saved workspace layout was found for this broker/account.", "INFO" if restored else "WARN")
        return restored

    def open_tool_window_by_key(self, key):
        actions = {
            "performance_analytics": getattr(self, "_open_performance", None),
            "closed_trade_journal": getattr(self, "_open_closed_journal_window", None),
            "trade_journal_review": getattr(self, "_open_trade_journal_review_window", None),
            "portfolio_exposure": getattr(self, "_show_portfolio_exposure", None),
            "position_analysis": getattr(self, "_open_position_analysis_window", None),
            "trade_recommendations": getattr(self, "_open_recommendations_window", None),
            "quant_pm": getattr(self, "_open_quant_pm_window", None),
            "system_health": getattr(self, "_open_system_health_window", None),
            "trade_checklist": getattr(self, "_open_trade_checklist_window", None),
            "market_chat": getattr(self, "_open_market_chat_window", None),
            "ml_monitor": getattr(self, "_open_ml_monitor", None),
            "logs": getattr(self, "_open_logs", None),
            "notification_center": getattr(self, "_open_notification_center", None),
        }
        handler = actions.get(str(key or "").strip())
        return handler() if callable(handler) else None

    def apply_workspace_preset(self, name):
        preset_name = str(name or "trading").strip().lower() or "trading"
        preset = WORKSPACE_PRESETS.get(preset_name, WORKSPACE_PRESETS["trading"])
        visible_docks = set(preset.get("docks", set()) or set())
        open_tools = list(preset.get("tools", []) or [])
        for attr_name in WORKSPACE_DOCKS:
            dock = getattr(self, attr_name, None)
            if not self._is_qt_object_alive(dock):
                continue
            dock.show() if attr_name in visible_docks else dock.hide()
        for key, window in list((getattr(self, "detached_tool_windows", {}) or {}).items()):
            if key in TOOL_WINDOWS and key not in open_tools and self._is_qt_object_alive(window):
                try:
                    window.hide()
                except Exception:
                    pass
        for key in open_tools:
            self._open_tool_window_by_key(key)
        self._queue_terminal_layout_fit()
        self._save_workspace_layout("last")
        self._push_notification("Workspace preset applied", f"{preset_name.title()} workspace is now active.", level="INFO", source="workspace", dedupe_seconds=2.0)
        if hasattr(self, "system_console"):
            self.system_console.log(f"Applied {preset_name.title()} workspace preset.", "INFO")
        return preset_name

    def restore_trader_memory(self):
        settings = getattr(self, "settings", None)
        if settings is None:
            self.favorite_symbols = set()
            return
        raw = settings.value(self._favorite_symbols_storage_key(), "[]")
        try:
            parsed = json.loads(raw or "[]")
        except Exception:
            parsed = []
        self.favorite_symbols = {self._normalized_symbol(symbol) for symbol in parsed if str(symbol or "").strip()}
        self._refresh_symbol_picker_favorites()
        self._update_favorite_action_text()

    def persist_trader_memory(self):
        settings = getattr(self, "settings", None)
        if settings is None:
            return False
        settings.setValue(self._favorite_symbols_storage_key(), json.dumps(sorted(getattr(self, "favorite_symbols", set()) or set())))
        ticket = (getattr(self, "detached_tool_windows", {}) or {}).get("manual_trade_ticket")
        if self._is_qt_object_alive(ticket):
            self._save_manual_trade_template_from_window(ticket)
        return True

    def refresh_symbol_picker_favorites(self):
        picker = getattr(self, "symbol_picker", None)
        if picker is None:
            return
        items = [picker.itemText(index) for index in range(picker.count())]
        if not items:
            return
        favorites = set(getattr(self, "favorite_symbols", set()) or set())
        current = str(picker.currentText() or "").strip()
        ranked = sorted(items, key=lambda item: (0 if self._normalized_symbol(item) in favorites else 1, self._normalized_symbol(item)))
        if ranked == items:
            return
        blocked = picker.blockSignals(True)
        picker.clear()
        picker.addItems(ranked)
        if current:
            picker.setCurrentText(current)
        picker.blockSignals(blocked)

    def update_favorite_action_text(self):
        action = getattr(self, "action_favorite_symbol", None)
        if action is None:
            return
        symbol = ""
        current_chart = getattr(self, "_current_chart_symbol", None)
        if callable(current_chart):
            try:
                symbol = str(current_chart() or "").strip()
            except Exception:
                symbol = ""
        if not symbol and getattr(self, "symbol_picker", None) is not None:
            symbol = str(self.symbol_picker.currentText() or "").strip()
        if not symbol:
            action.setText("Favorite Current Symbol")
            return
        normalized = self._normalized_symbol(symbol)
        favorites = set(getattr(self, "favorite_symbols", set()) or set())
        action.setText(f"Remove {normalized} From Favorites" if normalized in favorites else f"Favorite {normalized}")

    def toggle_current_symbol_favorite(self):
        symbol = ""
        current_chart = getattr(self, "_current_chart_symbol", None)
        if callable(current_chart):
            try:
                symbol = str(current_chart() or "").strip()
            except Exception:
                symbol = ""
        if not symbol and getattr(self, "symbol_picker", None) is not None:
            symbol = str(self.symbol_picker.currentText() or "").strip()
        if not symbol:
            self._push_notification("Favorite symbol", "Open or select a symbol before saving it as a favorite.", level="WARN", source="favorites", dedupe_seconds=5.0)
            return False
        favorites = set(getattr(self, "favorite_symbols", set()) or set())
        normalized = self._normalized_symbol(symbol)
        added = normalized not in favorites
        favorites.add(normalized) if added else favorites.discard(normalized)
        self.favorite_symbols = favorites
        self._persist_trader_memory()
        self._refresh_symbol_picker_favorites()
        self._update_favorite_action_text()
        self._push_notification("Favorite symbols", f"{normalized} was {'added to' if added else 'removed from'} favorites.", level="INFO", source="favorites", dedupe_seconds=2.0)
        return added

    def load_manual_trade_template(self):
        settings = getattr(self, "settings", None)
        if settings is None:
            return {}
        raw = settings.value(self._manual_trade_template_storage_key(), "")
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {}
        return dict(payload) if isinstance(payload, dict) else {}

    def save_manual_trade_template_from_window(self, window):
        if window is None:
            return {}
        payload = {
            "symbol": str(getattr(getattr(window, "_manual_trade_symbol_picker", None), "currentText", lambda: "")() or "").strip(),
            "side": str(getattr(getattr(window, "_manual_trade_side_picker", None), "currentText", lambda: "")() or "buy").strip().lower() or "buy",
            "order_type": str(getattr(getattr(window, "_manual_trade_type_picker", None), "currentText", lambda: "")() or "market").strip().lower() or "market",
            "quantity_mode": self._normalize_manual_trade_quantity_mode(str(getattr(getattr(window, "_manual_trade_quantity_picker", None), "currentText", lambda: "")() or "units")),
            "amount": float(getattr(getattr(window, "_manual_trade_amount_input", None), "value", lambda: 0.0)() or 0.0),
            "price": self._safe_float(getattr(getattr(window, "_manual_trade_price_input", None), "text", lambda: "")()),
            "stop_price": self._safe_float(getattr(getattr(window, "_manual_trade_stop_price_input", None), "text", lambda: "")()),
            "stop_loss": self._safe_float(getattr(getattr(window, "_manual_trade_stop_loss_input", None), "text", lambda: "")()),
            "take_profit": self._safe_float(getattr(getattr(window, "_manual_trade_take_profit_input", None), "text", lambda: "")()),
        }
        payload = {key: value for key, value in payload.items() if value not in (None, "", [])}
        settings = getattr(self, "settings", None)
        if settings is not None:
            settings.setValue(self._manual_trade_template_storage_key(), json.dumps(payload))
        return payload

    def command_palette_entries(self, query=None):
        query_text = str(query or "").strip().lower()
        entries = [
            {"title": "Manual Trade Ticket", "description": "Open the manual order ticket.", "keywords": "manual trade order ticket", "handler": lambda: self._open_manual_trade()},
            {"title": "Notification Center", "description": "Review fills, rejects, disconnects, and guard alerts.", "keywords": "notifications alerts fills rejects disconnect guard", "handler": self._open_notification_center},
            {"title": "Performance Analytics", "description": "Open the performance analysis workspace.", "keywords": "performance analytics ledger equity pnl", "handler": self._open_performance},
            {"title": "Portfolio Exposure", "description": "Open the portfolio exposure view.", "keywords": "portfolio exposure risk", "handler": self._show_portfolio_exposure},
            {"title": "Position Analysis", "description": "Inspect open positions and account metrics.", "keywords": "position analysis risk", "handler": self._open_position_analysis_window},
            {"title": "Trade Checklist", "description": "Open the pre-trade and post-trade checklist.", "keywords": "checklist journal review", "handler": self._open_trade_checklist_window},
            {"title": "Journal Review", "description": "Open the trade journal review window.", "keywords": "journal review closed trades", "handler": self._open_trade_journal_review_window},
            {"title": "Recommendations", "description": "Open AI trade recommendations.", "keywords": "recommendations signals ai", "handler": self._open_recommendations_window},
            {"title": "Sopotek Pilot", "description": "Open the market chat workspace.", "keywords": "pilot market chat assistant", "handler": self._open_market_chat_window},
            {"title": "Quant PM", "description": "Open portfolio analytics and correlation tools.", "keywords": "quant pm correlation portfolio", "handler": self._open_quant_pm_window},
            {"title": "Strategy Assigner", "description": "Open the strategy assignment workspace.", "keywords": "strategy assigner ranking", "handler": self._open_strategy_assignment_window},
            {"title": "Strategy Optimization", "description": "Open the optimization workspace.", "keywords": "strategy optimization backtest", "handler": self._optimize_strategy},
            {"title": "Backtesting Workspace", "description": "Open the strategy tester.", "keywords": "backtest tester", "handler": self._show_backtest_window},
            {"title": "Trading Workspace", "description": "Focus the terminal on execution and monitoring.", "keywords": "workspace preset trading layout", "handler": lambda: self._apply_workspace_preset("trading")},
            {"title": "Research Workspace", "description": "Focus the terminal on analysis and strategy discovery.", "keywords": "workspace preset research layout", "handler": lambda: self._apply_workspace_preset("research")},
            {"title": "Risk Workspace", "description": "Focus the terminal on exposure and control panels.", "keywords": "workspace preset risk layout", "handler": lambda: self._apply_workspace_preset("risk")},
            {"title": "Review Workspace", "description": "Focus the terminal on journaling and performance review.", "keywords": "workspace preset review layout", "handler": lambda: self._apply_workspace_preset("review")},
            {"title": "Save Layout For Account", "description": "Save the current dock layout for this broker/account.", "keywords": "workspace layout save account", "handler": self._save_current_workspace_layout},
            {"title": "Restore Saved Layout", "description": "Restore the saved dock layout for this broker/account.", "keywords": "workspace layout restore account", "handler": self._restore_saved_workspace_layout},
            {"title": "Favorite Current Symbol", "description": "Pin the active symbol to the top of selectors.", "keywords": "favorite symbol watchlist", "handler": self._toggle_current_symbol_favorite},
            {"title": "Refresh Markets", "description": "Reload available symbols and market state.", "keywords": "refresh markets symbols", "handler": self._refresh_markets},
            {"title": "Refresh Chart", "description": "Reload the active chart candles.", "keywords": "refresh chart candles", "handler": self._refresh_active_chart_data},
            {"title": "Refresh Orderbook", "description": "Reload the active order book and recent trades.", "keywords": "refresh orderbook depth trades", "handler": self._refresh_active_orderbook},
            {"title": "Reload Balance", "description": "Refresh balances and equity.", "keywords": "reload balance equity", "handler": self._reload_balance},
        ]
        available_symbols = list(getattr(getattr(self, "controller", None), "symbols", []) or [])
        if query_text and available_symbols:
            ranked = []
            for symbol in available_symbols:
                normalized = self._normalized_symbol(symbol)
                haystack = normalized.lower()
                if query_text in haystack:
                    ranked.append((0 if haystack.startswith(query_text) else 1, normalized))
            for _priority, symbol in sorted(ranked)[:8]:
                entries.append({"title": f"Open Chart: {symbol}", "description": f"Open {symbol} on the active timeframe.", "keywords": f"chart symbol {symbol.lower()}", "handler": (lambda target=symbol: self._open_symbol_chart(target, getattr(self, "current_timeframe", "1h")))})
                entries.append({"title": f"Manual Trade: {symbol}", "description": f"Open a manual trade ticket for {symbol}.", "keywords": f"manual trade symbol {symbol.lower()}", "handler": (lambda target=symbol: self._open_manual_trade({"symbol": target, "source": "command_palette"}))})
        if not query_text:
            return entries
        tokens = [token for token in query_text.split() if token]
        return [entry for entry in entries if all(token in " ".join(str(entry.get(key, "") or "") for key in ("title", "description", "keywords")).lower() for token in tokens)]

    def refresh_command_palette_window(self, window=None, query=None):
        window = window or (getattr(self, "detached_tool_windows", {}) or {}).get("command_palette")
        if not self._is_qt_object_alive(window):
            return
        table = getattr(window, "_command_palette_table", None)
        search = getattr(window, "_command_palette_search", None)
        summary = getattr(window, "_command_palette_summary", None)
        if table is None or search is None or summary is None:
            return
        query_text = str(search.text() if query is None else query or "").strip()
        entries = self._command_palette_entries(query=query_text)
        window._command_palette_entries = entries
        table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            title_item = QTableWidgetItem(str(entry.get("title") or ""))
            description_item = QTableWidgetItem(str(entry.get("description") or ""))
            title_item.setToolTip(str(entry.get("description") or ""))
            description_item.setToolTip(str(entry.get("keywords") or ""))
            table.setItem(row_index, 0, title_item)
            table.setItem(row_index, 1, description_item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        if entries:
            table.selectRow(0)
            summary.setText(f"{len(entries)} commands ready. Press Enter to run the highlighted command.")
        else:
            summary.setText("No commands match the current search.")

    def execute_command_palette_selection(self, window=None):
        window = window or (getattr(self, "detached_tool_windows", {}) or {}).get("command_palette")
        if not self._is_qt_object_alive(window):
            return None
        table = getattr(window, "_command_palette_table", None)
        entries = list(getattr(window, "_command_palette_entries", []) or [])
        if table is None or not entries:
            return None
        row = table.currentRow()
        row = 0 if row < 0 else row
        if row >= len(entries):
            return None
        entry = entries[row]
        handler = entry.get("handler")
        try:
            if callable(handler):
                window.hide()
                return handler()
        except Exception as exc:
            self._show_async_message("Command Failed", str(exc), QMessageBox.Icon.Critical)
        return None

    def open_command_palette(self):
        window = self._get_or_create_tool_window("command_palette", "Command Palette", width=760, height=520)
        if getattr(window, "_command_palette_container", None) is None:
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)
            summary = QLabel("Type a task, symbol, or workspace name to jump directly to it.")
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #d9e6f7; background-color: #101a2d; border: 1px solid #20324d; border-radius: 12px; padding: 10px;")
            layout.addWidget(summary)
            search = QLineEdit()
            search.setPlaceholderText("Try 'performance', 'risk', 'btc', or 'layout'")
            search.textChanged.connect(lambda *_: self._refresh_command_palette_window(window))
            search.returnPressed.connect(lambda: self._execute_command_palette_selection(window))
            layout.addWidget(search)
            table = QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["Command", "Description"])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.cellDoubleClicked.connect(lambda *_: self._execute_command_palette_selection(window))
            layout.addWidget(table, 1)
            run_btn = QPushButton("Run Selected Command")
            run_btn.clicked.connect(lambda: self._execute_command_palette_selection(window))
            layout.addWidget(run_btn)
            window.setCentralWidget(container)
            window._command_palette_container = container
            window._command_palette_summary = summary
            window._command_palette_search = search
            window._command_palette_table = table
            window._command_palette_entries = []
        self._refresh_command_palette_window(window)
        window.show()
        window.raise_()
        window.activateWindow()
        if getattr(window, "_command_palette_search", None) is not None:
            window._command_palette_search.setFocus()
            window._command_palette_search.selectAll()
        return window

    def create_menu_bar(self):
        result = orig_create_menu_bar(self)
        if not hasattr(self, "workspace_menu"):
            self.workspace_menu = self.menuBar().addMenu("Workspace")
            self.action_workspace_trading = QAction("Trading Workspace", self)
            self.action_workspace_trading.triggered.connect(lambda: self._apply_workspace_preset("trading"))
            self.action_workspace_research = QAction("Research Workspace", self)
            self.action_workspace_research.triggered.connect(lambda: self._apply_workspace_preset("research"))
            self.action_workspace_risk = QAction("Risk Workspace", self)
            self.action_workspace_risk.triggered.connect(lambda: self._apply_workspace_preset("risk"))
            self.action_workspace_review = QAction("Review Workspace", self)
            self.action_workspace_review.triggered.connect(lambda: self._apply_workspace_preset("review"))
            self.action_save_workspace_layout = QAction("Save Layout For Account", self)
            self.action_save_workspace_layout.triggered.connect(self._save_current_workspace_layout)
            self.action_restore_workspace_layout = QAction("Restore Saved Layout", self)
            self.action_restore_workspace_layout.triggered.connect(self._restore_saved_workspace_layout)
            for action in (
                self.action_workspace_trading,
                self.action_workspace_research,
                self.action_workspace_risk,
                self.action_workspace_review,
            ):
                self.workspace_menu.addAction(action)
            self.workspace_menu.addSeparator()
            self.workspace_menu.addAction(self.action_save_workspace_layout)
            self.workspace_menu.addAction(self.action_restore_workspace_layout)
            self.action_notifications = QAction("Notification Center", self)
            self.action_notifications.setShortcut("Ctrl+Shift+N")
            self.action_notifications.triggered.connect(self._open_notification_center)
            self.review_menu.addAction(self.action_notifications)
            self.tools_menu.addAction(self.action_notifications)
            self.action_command_palette = QAction("Command Palette", self)
            self.action_command_palette.setShortcut("Ctrl+K")
            self.action_command_palette.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            self.action_command_palette.triggered.connect(self._open_command_palette)
            self.tools_menu.addAction(self.action_command_palette)
            self.action_favorite_symbol = QAction("Favorite Current Symbol", self)
            self.action_favorite_symbol.triggered.connect(self._toggle_current_symbol_favorite)
            self.charts_menu.addSeparator()
            self.charts_menu.addAction(self.action_favorite_symbol)
        refresh_notification_action_text(self)
        update_favorite_action_text(self)
        return result

    def update_symbols(self, exchange, symbols):
        result = orig_update_symbols(self, exchange, symbols)
        self._refresh_symbol_picker_favorites()
        self._update_favorite_action_text()
        return result

    def update_trade_log(self, trade):
        result = orig_update_trade_log(self, trade)
        try:
            self._record_trade_notification(trade)
        except Exception:
            pass
        return result

    def update_connection_status(self, status):
        previous = str(getattr(self, "current_connection_status", "") or "").strip().lower()
        result = orig_update_connection_status(self, status)
        current = str(status or "").strip().lower()
        if current == "disconnected" and previous != "disconnected":
            self._push_notification("API disconnected", "The trading connection dropped and the terminal is no longer connected.", level="ERROR", source="broker", dedupe_seconds=5.0)
        elif current == "connected" and previous == "disconnected":
            self._push_notification("API reconnected", "The trading connection is back online.", level="INFO", source="broker", dedupe_seconds=5.0)
        return result

    def refresh_terminal(self):
        result = orig_refresh_terminal(self)
        try:
            self._refresh_runtime_notifications()
        except Exception:
            pass
        return result

    def restore_settings(self):
        result = orig_restore_settings(self)
        self._restore_trader_memory()
        self._restore_workspace_layout("last")
        self._update_favorite_action_text()
        return result

    def close_event(self, event):
        try:
            self._save_workspace_layout("last")
            self._persist_trader_memory()
        except Exception:
            pass
        return orig_close_event(self, event)

    def submit_manual_trade_from_ticket(self, window):
        try:
            self._save_manual_trade_template_from_window(window)
        except Exception:
            pass
        return orig_submit_manual_trade_from_ticket(self, window)

    def manual_trade_default_payload(self, prefill=None):
        merged = dict(self._load_manual_trade_template())
        merged.update(dict(prefill or {}))
        return orig_manual_trade_default_payload(self, merged)

    def show_async_message(self, title, text, icon=QMessageBox.Icon.Information):
        result = orig_show_async_message(self, title, text, icon=icon)
        level = "INFO"
        if icon == QMessageBox.Icon.Critical:
            level = "ERROR"
        elif icon == QMessageBox.Icon.Warning:
            level = "WARN"
        self._push_notification(title, text, level=level, source="dialog", dedupe_seconds=10.0)
        return result

    def handle_chart_trade_context_action(self, payload):
        if isinstance(payload, dict):
            action = str(payload.get("action") or "").strip().lower()
            symbol = str(payload.get("symbol") or self._current_chart_symbol() or "").strip()
            if action in {"buy_market_ticket", "sell_market_ticket"} and symbol:
                return self._open_manual_trade(
                    {
                        "symbol": symbol,
                        "side": "buy" if action == "buy_market_ticket" else "sell",
                        "order_type": "market",
                        "source": "chart_context_menu",
                        "timeframe": payload.get("timeframe"),
                    }
                )
        return orig_handle_chart_trade_context_action(self, payload)

    def on_chart_tab_changed(self, index):
        result = orig_on_chart_tab_changed(self, index)
        self._update_favorite_action_text()
        return result

    Terminal._workspace_context_key = workspace_context_key
    Terminal._workspace_settings_prefix = workspace_settings_prefix
    Terminal._favorite_symbols_storage_key = favorite_symbols_storage_key
    Terminal._manual_trade_template_storage_key = manual_trade_template_storage_key
    Terminal._ensure_notification_state = ensure_notification_state
    Terminal._refresh_notification_action_text = refresh_notification_action_text
    Terminal._push_notification = push_notification
    Terminal._refresh_notification_center_window = refresh_notification_center_window
    Terminal._open_notification_center = open_notification_center
    Terminal._record_trade_notification = record_trade_notification
    Terminal._runtime_notification_transition = runtime_notification_transition
    Terminal._refresh_runtime_notifications = refresh_runtime_notifications
    Terminal._visible_tool_window_keys = visible_tool_window_keys
    Terminal._save_workspace_layout = save_workspace_layout
    Terminal._restore_workspace_layout = restore_workspace_layout
    Terminal._save_current_workspace_layout = save_current_workspace_layout
    Terminal._restore_saved_workspace_layout = restore_saved_workspace_layout
    Terminal._open_tool_window_by_key = open_tool_window_by_key
    Terminal._apply_workspace_preset = apply_workspace_preset
    Terminal._restore_trader_memory = restore_trader_memory
    Terminal._persist_trader_memory = persist_trader_memory
    Terminal._refresh_symbol_picker_favorites = refresh_symbol_picker_favorites
    Terminal._update_favorite_action_text = update_favorite_action_text
    Terminal._toggle_current_symbol_favorite = toggle_current_symbol_favorite
    Terminal._load_manual_trade_template = load_manual_trade_template
    Terminal._save_manual_trade_template_from_window = save_manual_trade_template_from_window
    Terminal._command_palette_entries = command_palette_entries
    Terminal._refresh_command_palette_window = refresh_command_palette_window
    Terminal._execute_command_palette_selection = execute_command_palette_selection
    Terminal._open_command_palette = open_command_palette
    Terminal._create_menu_bar = create_menu_bar
    Terminal._update_symbols = update_symbols
    Terminal._update_trade_log = update_trade_log
    Terminal.update_connection_status = update_connection_status
    Terminal._refresh_terminal = refresh_terminal
    Terminal._restore_settings = restore_settings
    Terminal.closeEvent = close_event
    Terminal._submit_manual_trade_from_ticket = submit_manual_trade_from_ticket
    Terminal._manual_trade_default_payload = manual_trade_default_payload
    Terminal._show_async_message = show_async_message
    Terminal._handle_chart_trade_context_action = handle_chart_trade_context_action
    Terminal._on_chart_tab_changed = on_chart_tab_changed
    Terminal._operator_features_installed = True
