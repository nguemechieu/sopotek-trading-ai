import sys
import socket
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as app_main
from sopotek_trading import main as compat_main
from sopotek_trading_ai import launcher as package_launcher


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


def test_configure_qt_platform_defaults_to_offscreen_without_linux_display(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(app_main.sys, "platform", "linux")

    selected = app_main._configure_qt_platform()

    assert selected == "offscreen"
    assert app_main.os.environ["QT_QPA_PLATFORM"] == "offscreen"


def test_configure_qt_platform_preserves_explicit_setting(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(app_main.sys, "platform", "linux")

    selected = app_main._configure_qt_platform()

    assert selected == "xcb"
    assert app_main.os.environ["QT_QPA_PLATFORM"] == "xcb"


def test_configure_qt_platform_leaves_gui_mode_when_display_exists(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(app_main.sys, "platform", "linux")

    selected = app_main._configure_qt_platform()

    assert selected is None
    assert "QT_QPA_PLATFORM" not in app_main.os.environ


def test_configure_browser_qt_runtime_sets_software_container_defaults(monkeypatch):
    monkeypatch.setenv("SOPOTEK_HTTP_UI", "1")
    monkeypatch.delenv("SOPOTEK_DISABLE_WEBENGINE", raising=False)
    monkeypatch.delenv("LIBGL_ALWAYS_SOFTWARE", raising=False)
    monkeypatch.delenv("QT_OPENGL", raising=False)
    monkeypatch.delenv("QT_QUICK_BACKEND", raising=False)
    monkeypatch.delenv("QSG_RHI_BACKEND", raising=False)
    monkeypatch.delenv("QT_XCB_GL_INTEGRATION", raising=False)
    monkeypatch.delenv("QTWEBENGINE_DISABLE_SANDBOX", raising=False)
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.setattr(app_main.sys, "platform", "linux")

    enabled = app_main._configure_browser_qt_runtime()

    assert enabled is True
    assert app_main.os.environ["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert app_main.os.environ["QT_OPENGL"] == "software"
    assert app_main.os.environ["QT_QUICK_BACKEND"] == "software"
    assert app_main.os.environ["QSG_RHI_BACKEND"] == "software"
    assert app_main.os.environ["QT_XCB_GL_INTEGRATION"] == "none"
    assert app_main.os.environ["QTWEBENGINE_DISABLE_SANDBOX"] == "1"
    flags = app_main.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
    assert "--disable-gpu" in flags
    assert "--disable-features=Vulkan,VulkanFromANGLE,UseSkiaRenderer" in flags


def test_configure_browser_qt_runtime_is_noop_without_browser_env(monkeypatch):
    monkeypatch.delenv("SOPOTEK_HTTP_UI", raising=False)
    monkeypatch.delenv("SOPOTEK_DISABLE_WEBENGINE", raising=False)
    monkeypatch.setattr(app_main.sys, "platform", "linux")

    enabled = app_main._configure_browser_qt_runtime()

    assert enabled is False


def test_packaged_launcher_delegates_to_desktop_entrypoint(monkeypatch):
    calls = []
    fake_module = SimpleNamespace(main=lambda argv=None: calls.append(argv) or 7)
    monkeypatch.setattr(package_launcher, "_load_desktop_entrypoint", lambda: fake_module)

    assert package_launcher.main(["--headless"]) == 7
    assert calls == [["--headless"]]


def test_packaged_launcher_requires_callable_main(monkeypatch):
    monkeypatch.setattr(package_launcher, "_load_desktop_entrypoint", lambda: SimpleNamespace())

    try:
        package_launcher.main()
    except RuntimeError as exc:
        assert "callable main" in str(exc)
    else:
        raise AssertionError("launcher should reject entrypoints without a callable main")


def test_compat_module_exports_packaged_launcher():
    assert compat_main is package_launcher.main
