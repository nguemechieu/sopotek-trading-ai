"""Sopotek v2 runtime package."""

from __future__ import annotations

from typing import Any

__all__ = ["SopotekRuntime", "EventDrivenBacktestEngine"]


def __getattr__(name: str) -> Any:
    if name == "SopotekRuntime":
        from sopotek.core.orchestrator import SopotekRuntime

        return SopotekRuntime
    if name == "EventDrivenBacktestEngine":
        from sopotek.engines.backtest import EventDrivenBacktestEngine

        return EventDrivenBacktestEngine
    raise AttributeError(f"module 'sopotek' has no attribute {name!r}")
