"""Bootstrap wrapper for the Sopotek Trading AI desktop workspace.

This entrypoint lives inside ``desktop_app/`` so the desktop product has its
own dedicated folder, while still delegating execution to the canonical source
tree at ``../src/main.py``.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[1]
    runpy.run_path(str(repo_root / "src" / "main.py"), run_name="__main__")
