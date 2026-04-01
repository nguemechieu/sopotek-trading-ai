"""Compatibility module for historic Docker and runner commands."""

from sopotek_trading_ai.launcher import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
