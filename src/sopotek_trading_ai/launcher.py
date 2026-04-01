"""Package launcher helpers for the desktop application."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _entrypoint_path() -> Path:
    """Return the real desktop entrypoint path inside ``src``."""
    return Path(__file__).resolve().parents[1] / "main.py"


def _load_desktop_entrypoint() -> ModuleType:
    """Load ``src/main.py`` as an importable module."""
    entrypoint = _entrypoint_path()
    spec = importlib.util.spec_from_file_location("sopotek_desktop_entrypoint", entrypoint)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Unable to load desktop entrypoint from {entrypoint}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    """Run the desktop application through the packaged module path."""
    module = _load_desktop_entrypoint()
    runner = getattr(module, "main", None)
    if not callable(runner):
        raise RuntimeError("The desktop entrypoint module does not expose a callable main(argv=None).")
    return int(runner(argv))
