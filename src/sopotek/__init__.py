"""Sopotek v2 runtime package.

Keep package-level imports lazy so lightweight submodules such as
``sopotek.core.event_bus.event`` do not eagerly pull in the full runtime and
optional ML dependencies during unrelated imports.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sopotek.core.orchestrator import SopotekRuntime
    from sopotek.engines.backtest import EventDrivenBacktestEngine

__all__ = ["SopotekRuntime", "EventDrivenBacktestEngine"]

_LAZY_EXPORTS = {
    "SopotekRuntime": ("sopotek.core.orchestrator", "SopotekRuntime"),
    "EventDrivenBacktestEngine": ("sopotek.engines.backtest", "EventDrivenBacktestEngine"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
