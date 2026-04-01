import sys
import socket
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as app_main


def test_qt_windows_noise_filter_matches_known_console_noise():
    assert app_main._is_qt_windows_noise("External WM_DESTROY received for QWidgetWindow(...)") is True
    assert app_main._is_qt_windows_noise("QWindowsWindow::setGeometry: Unable to set geometry 2139x1290+0+29") is True
    assert app_main._is_qt_windows_noise("OpenThemeData() failed for theme 15 (WINDOW). (The handle is invalid.)") is True
    assert app_main._is_qt_windows_noise("Using polling market data for Oanda") is False


def test_dns_resolution_noise_filter_matches_known_dns_cases():
    assert app_main._is_dns_resolution_noise({"exception": socket.gaierror(11001, "getaddrinfo failed")}) is True
    assert app_main._is_dns_resolution_noise({"message": "ClientConnectorDNSError: dns lookup failed"}) is True
    assert app_main._is_dns_resolution_noise({"future": "getaddrinfo failed for broker host"}) is True
    assert app_main._is_dns_resolution_noise({"message": "unexpected failure"}) is False


def test_install_asyncio_exception_filter_suppresses_dns_noise_and_logs_debug():
    debug_messages = []

    class _Loop:
        def __init__(self):
            self.installed_handler = None
            self.default_calls = []

        def get_exception_handler(self):
            return None

        def set_exception_handler(self, handler):
            self.installed_handler = handler

        def default_exception_handler(self, context):
            self.default_calls.append(context)

    loop = _Loop()
    logger = SimpleNamespace(debug=lambda message, detail: debug_messages.append((message, detail)))

    app_main._install_asyncio_exception_filter(loop, logger=logger)

    loop.installed_handler(loop, {"message": "ClientConnectorDNSError: dns lookup failed"})

    assert loop.default_calls == []
    assert debug_messages
    assert "Suppressed transient DNS resolver noise" in debug_messages[0][0]


def test_install_asyncio_exception_filter_delegates_non_dns_errors_to_previous_handler():
    forwarded = []

    class _Loop:
        def __init__(self):
            self.installed_handler = None

        def get_exception_handler(self):
            return lambda active_loop, context: forwarded.append((active_loop, context))

        def set_exception_handler(self, handler):
            self.installed_handler = handler

        def default_exception_handler(self, context):
            raise AssertionError("default handler should not be used when previous handler exists")

    loop = _Loop()

    app_main._install_asyncio_exception_filter(loop, logger=None)

    payload = {"message": "non dns runtime error"}
    loop.installed_handler(loop, payload)

    assert forwarded == [(loop, payload)]
