import asyncio
import faulthandler
import os
import socket
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from frontend.ui.app_controller import AppController


def _patch_qasync_timer_cleanup():
    simple_timer = getattr(qasync, "_SimpleTimer", None)
    if simple_timer is None or getattr(simple_timer, "_sopotek_safe_timer_patch", False):
        return

    def timer_event(self, event):  # noqa: N802
        timerid = event.timerId()
        self._SimpleTimer__log_debug("Timer event on id %s", timerid)
        callbacks = self._SimpleTimer__callbacks

        if self._stopped:
            self._SimpleTimer__log_debug("Timer stopped, killing %s", timerid)
            self.killTimer(timerid)
            callbacks.pop(timerid, None)
            return

        handle = callbacks.get(timerid)
        if handle is None:
            self._SimpleTimer__log_debug("Timer %s already cleared", timerid)
            self.killTimer(timerid)
            return

        try:
            if handle._cancelled:
                self._SimpleTimer__log_debug("Handle %s cancelled", handle)
            else:
                if self._SimpleTimer__debug_enabled:
                    import time
                    from asyncio.events import _format_handle

                    loop = asyncio.get_event_loop()
                    try:
                        loop._current_handle = handle
                        self._logger.debug("Calling handle %s", handle)
                        t0 = time.time()
                        handle._run()
                        dt = time.time() - t0
                        if dt >= loop.slow_callback_duration:
                            self._logger.warning(
                                "Executing %s took %.3f seconds",
                                _format_handle(handle),
                                dt,
                            )
                    finally:
                        loop._current_handle = None
                else:
                    handle._run()
        finally:
            callbacks.pop(timerid, None)
            self.killTimer(timerid)

    simple_timer.timerEvent = timer_event
    simple_timer._sopotek_safe_timer_patch = True


_patch_qasync_timer_cleanup()

_FAULTHANDLER_STREAM = None


def _install_faulthandler():
    global _FAULTHANDLER_STREAM

    if faulthandler.is_enabled():
        return

    try:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        _FAULTHANDLER_STREAM = open(log_dir / "native_crash.log", "a", encoding="utf-8", buffering=1)
        _FAULTHANDLER_STREAM.write(
            f"\n=== Native crash trace session pid={os.getpid()} ===\n"
        )
        faulthandler.enable(file=_FAULTHANDLER_STREAM, all_threads=True)
    except Exception:
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass


_install_faulthandler()


def _is_dns_resolution_noise(context):
    message = str((context or {}).get("message") or "").lower()
    exception = (context or {}).get("exception")
    future = (context or {}).get("future")
    future_repr = str(future or "").lower()

    details = []
    for item in (exception, getattr(exception, "__cause__", None), getattr(exception, "__context__", None)):
        if item is not None:
            details.append(str(item).lower())

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


def _install_asyncio_exception_filter(loop, logger=None):
    previous_handler = loop.get_exception_handler()

    def handler(active_loop, context):
        if _is_dns_resolution_noise(context):
            if logger is not None:
                logger.debug("Suppressed transient DNS resolver noise: %s", context.get("message") or context.get("exception"))
            return

        if previous_handler is not None:
            previous_handler(active_loop, context)
        else:
            active_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def main(argv=None):
    app = QApplication(sys.argv if argv is None else list(argv))

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    def _stop_loop():
        if loop.is_running():
            loop.stop()

    window = AppController()
    _install_asyncio_exception_filter(loop, logger=getattr(window, "logger", None))
    window.setIconSize(QSize(48, 48))
    app.aboutToQuit.connect(_stop_loop)
    window.setWindowIcon(QIcon("./assets/logo.ico"))
    window.setWindowIconText("Sopotek Trading AI Platform")
    window.setWindowTitle("Sopotek Trading AI")
    window.show()

    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

