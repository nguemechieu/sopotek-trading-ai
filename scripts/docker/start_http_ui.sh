#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:99}"
export SOPOTEK_HTTP_UI="${SOPOTEK_HTTP_UI:-1}"
export SOPOTEK_DISABLE_WEBENGINE="${SOPOTEK_DISABLE_WEBENGINE:-1}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export QTWEBENGINE_DISABLE_SANDBOX="${QTWEBENGINE_DISABLE_SANDBOX:-1}"
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---no-sandbox --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-dev-shm-usage --disable-features=Vulkan,VulkanFromANGLE,UseSkiaRenderer}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export QT_OPENGL="${QT_OPENGL:-software}"
export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
export QSG_RHI_BACKEND="${QSG_RHI_BACKEND:-software}"
export QT_XCB_GL_INTEGRATION="${QT_XCB_GL_INTEGRATION:-none}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-sopotek}"
export SCREEN_WIDTH="${SCREEN_WIDTH:-1600}"
export SCREEN_HEIGHT="${SCREEN_HEIGHT:-900}"
export SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
export VNC_PORT="${VNC_PORT:-5900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"
export X11VNC_EXTRA_ARGS="${X11VNC_EXTRA_ARGS:-}"

mkdir -p "$XDG_RUNTIME_DIR" /app/logs
chmod 700 "$XDG_RUNTIME_DIR"

Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +render -noreset >/app/logs/xvfb.log 2>&1 &
XVFB_PID=$!

DISPLAY_SOCKET="/tmp/.X11-unix/X${DISPLAY#:}"
READY=0
for _ in $(seq 1 40); do
    if [ -e "$DISPLAY_SOCKET" ]; then
        READY=1
        break
    fi
    sleep 0.25
done

if [ "$READY" -ne 1 ]; then
    echo "Timed out waiting for Xvfb display $DISPLAY" >&2
    exit 1
fi

fluxbox >/app/logs/fluxbox.log 2>&1 &
FLUXBOX_PID=$!

autocutsel -display "$DISPLAY" >/app/logs/autocutsel-clipboard.log 2>&1 &
AUTOCUTSEL_CLIPBOARD_PID=$!

autocutsel -display "$DISPLAY" -selection PRIMARY >/app/logs/autocutsel-primary.log 2>&1 &
AUTOCUTSEL_PRIMARY_PID=$!

x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -nopw -quiet $X11VNC_EXTRA_ARGS >/app/logs/x11vnc.log 2>&1 &
X11VNC_PID=$!

/usr/share/novnc/utils/novnc_proxy --listen "$NOVNC_PORT" --vnc "localhost:${VNC_PORT}" >/app/logs/novnc.log 2>&1 &
NOVNC_PID=$!

cleanup() {
    kill "$NOVNC_PID" "$X11VNC_PID" "$AUTOCUTSEL_PRIMARY_PID" "$AUTOCUTSEL_CLIPBOARD_PID" "$FLUXBOX_PID" "$XVFB_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

printf '%s\n' "Browser UI available at http://localhost:${NOVNC_PORT}/vnc.html?autoconnect=1&resize=scale"
printf '%s\n' "Clipboard bridge enabled. If your browser blocks Ctrl+V, use the noVNC clipboard panel to paste text into the app."

python -m sopotek_trading "$@"
