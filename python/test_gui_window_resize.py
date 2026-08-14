"""Can the window actually be resized vertically?

On a Mac the window could be made wider and narrower but its height would not
budge. Nothing pinned it: the Results tab's network-viewer control column is
five stacked group boxes, and an unscrolled panel hands its full height to the
window as a *minimum*. That minimum came to 1144px — taller than the usable
height of a laptop screen — so macOS clamped the window to the screen and it
could neither grow (screen limit) nor shrink (minimum). Width had a minimum of
~400px, so width stayed free, which is exactly what it looked like from
outside.

The guard here is the same one the bug broke: no mode's window may demand more
vertical space than a modest laptop screen leaves. 800px is the height of the
smallest display anyone runs this on, less the menu bar and the Dock.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.modes import MODES  # noqa: E402

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


# A 1280x800 display with the menu bar and Dock taken off it.
USABLE_HEIGHT = 700
USABLE_WIDTH = 1100

for mode in MODES:
    print(f"\n{MODES[mode].label}")
    window = MainWindow(mode=mode)
    window.show()
    app.processEvents()

    min_h = window.minimumSizeHint().height()
    min_w = window.minimumSizeHint().width()
    check(f"[{mode}] fits the height of a small laptop screen",
          min_h <= USABLE_HEIGHT, f"minimum height {min_h}px > {USABLE_HEIGHT}px")
    check(f"[{mode}] fits the width too", min_w <= USABLE_WIDTH,
          f"minimum width {min_w}px > {USABLE_WIDTH}px")

    # And it really does resize, not just report a small minimum: shrink it and
    # see the height follow. (Offscreen has no window manager to clamp against,
    # so a refused resize here means a layout constraint refused it.)
    window.resize(900, USABLE_HEIGHT)
    app.processEvents()
    check(f"[{mode}] height follows a resize down",
          window.height() <= USABLE_HEIGHT,
          f"asked for {USABLE_HEIGHT}px, got {window.height()}px")

    # Every tab, not just the one showing — switching tabs must not re-lock it.
    for i in range(window._tabs.count()):
        window._tabs.setCurrentIndex(i)
        app.processEvents()
        title = window._tabs.tabText(i).strip()
        h = window.minimumSizeHint().height()
        check(f"[{mode}] the {title} tab does not raise the floor",
              h <= USABLE_HEIGHT, f"minimum height {h}px with {title} showing")

    window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All window-resize checks passed.")
