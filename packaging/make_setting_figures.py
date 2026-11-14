"""Draw the illustrations for the run settings' explanation cards.

    uv run --project python python packaging/make_setting_figures.py

Each module in ``setting_figures/`` (other than ``style``) has a ``main()``
that writes its PNGs to ``src/meanap/gui/assets/settings``. The pictures are
deterministic (fixed seeds), drawn from the pipeline's own functions where it
has them, so rerunning gives the same files.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    sys.path.insert(0, str(HERE))
    import setting_figures

    for info in pkgutil.iter_modules(setting_figures.__path__):
        if info.name == "style":
            continue
        module = importlib.import_module(f"setting_figures.{info.name}")
        print(f"{info.name}: {', '.join(p.name for p in module.main() or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
