"""Desktop entrypoint for the Sopotek Trading AI application."""

# cspell:words qasync sopotek timerid getpid gaierror clientconnectordnserror

from __future__ import annotations

import asyncio
import contextlib
import faulthandler
import importlib
import os
import socket
import sys
from pathlib import Path
from typing import Any, TextIO

from PySide6 import QtCore, QtGui, QtWidgets


_FAULTHANDLER_STATE: dict[str, TextIO | None] = {"stream": None}
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def _src_root() -> Path:
    """Get the absolute path to the src directory.

    Returns
    -------
    Path
        The directory containing this script.
    """
    return Path(__file__).resolve().parent


def _ensure_src_on_path() -> None:
    """Add the src directory to Python's module search path.

    This enables importing of local modules from the src directory.
    """
    src_root = _src_root()
    src_value = str(src_root)
    if src_value not in sys.path:
        sys.path.insert(0, src_value)


def _load_qeventloop() -> type[Any]:
    """Load and return the qasync QEventLoop class.

    Returns
    -------
    type[Any]
        The QEventLoop class from the qasync module.
    """
    qasync_module = importlib.import_module("qasync")
    return qasync_module.QEventLoop


def _load_app_controller() -> type[Any]:
    """Load and return the AppController class from the frontend module.

    Returns
    -------
    type[Any]
        The AppController class.
    """
    _ensure_src_on_path()
    module = importlib.import_module("frontend.ui.app_controller")
    return module.AppController


def _configure_qt_platform() -> str | None:
    """Choose a safe Qt platform plugin for the current environment."""
    configured = str(os.getenv("QT_QPA_PLATFORM") or "").strip()
    if configured:
        return configured

    has_display = bool(str(os.getenv("DISPLAY") or "").strip() or str(os.getenv("WAYLAND_DISPLAY") or "").strip())
    if sys.platform.startswith("linux") and not has_display:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        return "offscreen"

    return None


def _env_truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in _TRUE_ENV_VALUES


def _append_chromium_flag(existing_flags: str, flag: str) -> str:
    text = str(existing_flags or "").strip()
    normalized_flag = str(flag or "").strip()
    if not normalized_flag:
        return text
    parts = text.split()
    if normalized_flag in parts:
        return text
    return f"{text} {normalized_flag}".strip()


def _configure_browser_qt_runtime() -> bool:
    """Force safer software-only Qt settings for browser/Xvfb container runs."""
    if not sys.platform.startswith("linux"):
        return False
    if not (_env_truthy("SOPOTEK_HTTP_UI") or _env_truthy("SOPOTEK_DISABLE_WEBENGINE")):
        return False

    defaults = {
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "QT_OPENGL": "software",
        "QT_QUICK_BACKEND": "software",
        "QSG_RHI_BACKEND": "software",
        "QT_XCB_GL_INTEGRATION": "none",
        "QTWEBENGINE_DISABLE_SANDBOX": "1",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)

    chromium_flags = str(os.getenv("QTWEBENGINE_CHROMIUM_FLAGS") or "").strip()
    for flag in (
        "--no-sandbox",
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-rasterization",
        "--disable-dev-shm-usage",
        "--disable-features=Vulkan,VulkanFromANGLE,UseSkiaRenderer",
    ):
        chromium_flags = _append_chromium_flag(chromium_flags, flag)
    if chromium_flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = chromium_flags
    return True


def _install_faulthandler() -> None:
    """Install Python's faulthandler to capture native crashes and core dumps.

    Attempts to write crash traces to a log file. Falls back to stderr if file
    logging fails.
    """
    if faulthandler.is_enabled():
        return

    try:
        _setup_faulthandler_file_logging()
    except (OSError, RuntimeError, ValueError):
        try:
            faulthandler.enable(all_threads=True)
        except (OSError, RuntimeError, ValueError):
            return


def _setup_faulthandler_file_logging():
    log_dir = _src_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream: os.TextIOWrapper[_WrappedBuffer] = (log_dir / "native_crash.log").open(  
        mode="a",
        buffering=-1,
        encoding="utf-8",
        errors=None,
        newline=None
)
    stream.write(f"\n=== Native crash trace session pid={os.getpid()} ===\n")
    faulthandler.enable(file=stream, all_threads=True)
    _FAULTHANDLER_STATE["stream"] = stream


def _is_dns_resolution_noise(context: dict[str, Any] | None) -> bool:
    """Check if an asyncio exception is transient DNS resolution noise.

    Parameters
    ----------
    context : dict[str, Any] | None
        The asyncio exception handler context.

    Returns
    -------
    bool
        True if the exception is DNS-related transient noise, False otherwise.
    """
    payload = context or {}
    message = str(payload.get("message") or "").lower()
    exception = payload.get("exception")
    future = payload.get("future")
    future_repr = str(future or "").lower()

    details: list[str] = []
    details.extend(
        str(item).lower()
        for item in (
            exception,
            getattr(exception, "__cause__", None),
            getattr(exception, "__context__", None),
        )
        if item is not None
    )
    if isinstance(exception, socket.gaierror):
        return True

    haystack = " ".join([message, future_repr, *details])
    return any(
        token in haystack
        for token in (
            "getaddrinfo failed",
            "could not contact dns servers",
            "dns lookup failed",
            "clientconnectordnserror",
        )
    )


def _install_asyncio_exception_filter(loop: Any, logger: Any = None) -> None:
    """Install a custom asyncio exception handler to filter DNS resolution noise.

    Suppresses transient DNS resolution errors while preserving meaningful
    exceptions for proper logging and debugging.

    Parameters
    ----------
    loop : Any
        The asyncio event loop.
    logger : Any, optional
        Logger instance for debug messages, by default None.
    """
    previous_handler = loop.get_exception_handler()

    def handler(active_loop: Any, context: dict[str, Any]) -> None:
        if _is_dns_resolution_noise(context):
            if logger is not None:
                logger.debug(
                    "Suppressed transient DNS resolver noise: %s",
                    context.get("message") or context.get("exception"),
                )
            return

        if previous_handler is not None:
            previous_handler(active_loop, context)
        else:
            active_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def _is_qt_windows_noise(message: str | None) -> bool:
    """Check if a Qt message is harmless Windows platform integration noise.

    Parameters
    ----------
    message : str | None
        The Qt message text.

    Returns
    -------
    bool
        True if the message is known harmless noise, False otherwise.
    """
    if text := str(message or "").strip():
        return any(
            token in text
            for token in (
                "External WM_DESTROY received for",
                "QWindowsWindow::setGeometry: Unable to set geometry",
                "OpenThemeData() failed for theme 15 (WINDOW).",
            )
        )
    else:
        return False


def _install_qt_message_filter() -> None:
    """Install a custom Qt message handler to filter Windows platform noise.

    Suppresses known harmless Qt warnings on Windows while preserving meaningful
    messages.
    """
    previous_handler = QtCore.qInstallMessageHandler(None)

    def handler(mode: Any, context: Any, message: str) -> None:
        if _is_qt_windows_noise(message):
            return
        if callable(previous_handler):
            previous_handler(mode, context, message)
        else:
            sys.stderr.write(f"{message}\n")

    QtCore.qInstallMessageHandler(handler)


def main(argv: list[str] | None = None) -> int:
    _install_faulthandler()
    _install_qt_message_filter()
    browser_runtime = _configure_browser_qt_runtime()
    platform_plugin = _configure_qt_platform()
    if platform_plugin == "offscreen":
        sys.stderr.write(
            "No Linux display detected; using Qt offscreen mode. "
            "Set DISPLAY or WAYLAND_DISPLAY and override QT_QPA_PLATFORM if you need an interactive GUI.\n"
        )
    elif browser_runtime:
        sys.stderr.write(
            "Browser container mode detected; forcing software Qt rendering and disabling embedded WebEngine panels.\n"
        )

    app = QtWidgets.QApplication(sys.argv if argv is None else list(argv))
    app.setStyle("Fusion")
    qeventloop_cls = _load_qeventloop()
    loop = qeventloop_cls(app)
    asyncio.set_event_loop(loop)

    def _stop_loop() -> None:
        if loop.is_running():
            loop.stop()

    app_controller_cls = _load_app_controller()
    window = app_controller_cls()
    _install_asyncio_exception_filter(loop, logger=getattr(window, "logger", None))
    window.setIconSize(QtCore.QSize(48, 48))

    icon_path = _src_root() / "assets" / "logo.ico"
    if icon_path.exists():
        window.setWindowIcon(QtGui.QIcon(str(icon_path)))

    window.setWindowIconText("Sopotek Trading AI Platform")
    window.setWindowTitle("Sopotek Trading AI")
    quit_signal = getattr(app, "aboutToQuit", None)
    connect = getattr(quit_signal, "connect", None)
    if connect is not None:
        connect(_stop_loop)  # pylint: disable=not-callable
    window.show()

    with loop:
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            shutdown_coro = getattr(window, "shutdown_for_exit", None)
            if callable(shutdown_coro):
                with contextlib.suppress(KeyboardInterrupt, RuntimeError):
                    loop.run_until_complete(shutdown_coro())
            shutdown_asyncgens = getattr(loop, "shutdown_asyncgens", None)
            if callable(shutdown_asyncgens):
                with contextlib.suppress(KeyboardInterrupt, RuntimeError):
                    loop.run_until_complete(shutdown_asyncgens())
            shutdown_default_executor = getattr(loop, "shutdown_default_executor", None)
            if callable(shutdown_default_executor):
                with contextlib.suppress(KeyboardInterrupt, RuntimeError):
                    loop.run_until_complete(shutdown_default_executor())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
