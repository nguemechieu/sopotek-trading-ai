"""Allow ``python -m sopotek_trading`` to launch the desktop app."""

from .main import main


if __name__ == "__main__":
    raise SystemExit(main())
