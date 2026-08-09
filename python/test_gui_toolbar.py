"""The toolbar, and what happens to it when the window is not wide.

A QToolBar that does not fit folds its trailing items into an overflow chevron.
That is fine for Tutorial. It was not fine for the Mode selector, which sat at
the far end behind an expanding spacer and a logo: adding two actions during the
GUI reorganisation pushed it out of reach at the default window size, and picking
a pipeline is the first thing anyone does.

So Mode leads the toolbar, the logo moved to the tab strip's corner where
nothing competes with it, and the default window is wide enough for the whole
row. These checks hold all three in place.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QAction  # noqa: E402
from PyQt6.QtWidgets import QApplication, QToolBar, QToolButton  # noqa: E402

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
# Widths depend on the style, so measure under the one the app actually ships.
theme.apply(app)

from meanap.gui.main_window import MainWindow  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


window = MainWindow()
window.show()
app.processEvents()
app.processEvents()
toolbar = window.findChild(QToolBar)


def hidden_buttons() -> list[str]:
    return [b.text() for b in toolbar.findChildren(QToolButton)
            if b.text() and not b.isVisible()]


# ── Nothing overflows at the size the window opens at ─────────────────────────

print("\nAt the default window size")

check("the whole toolbar fits", not hidden_buttons(), ", ".join(hidden_buttons()))
check("including the Mode selector", window._mode_combo.isVisible(), "")


# ── Mode survives a narrow window ─────────────────────────────────────────────

print("\nWhen the window is narrower than the toolbar")

for width in (1000, 900, 800, 700, 640):
    window.resize(width, 800)
    app.processEvents()
    app.processEvents()
    check(f"Mode is still reachable at {width}px",
          window._mode_combo.isVisible(), ", ".join(hidden_buttons()))

window.resize(1120, 800)
app.processEvents()

# Mode leading the toolbar is *why* the above holds: Qt drops trailing items.
texts = [a.text() for a in toolbar.actions()]
first_named = next((t for t in texts if t), "")
check("and it comes before every action, which is what makes that true",
      toolbar.actions()[0].text() == ""  # the Mode label is a widget action
      and first_named == "New", f"{first_named!r} / {texts[:4]}")


# ── Switching it still works ──────────────────────────────────────────────────

print("\nPicking a pipeline")

for key, expected in (("catnap", "CAT-NAP (2P)"), ("meastim", "Stimulation"),
                      ("meanap", "Spike detection")):
    window._mode_combo.setCurrentIndex(window._mode_combo.findData(key))
    app.processEvents()
    titles = [window._tabs.tabText(i).strip() for i in range(window._tabs.count())]
    check(f"choosing {key} re-tabs the window", expected in titles, str(titles))


# ── One theme, and the logo out of the way ────────────────────────────────────

print("\nTheme and branding")

action_texts = {a.text() for a in window.findChildren(QAction)}
check("there is no light/dark toggle any more",
      not any("Light" in t or "Dark" in t for t in action_texts),
      str(sorted(t for t in action_texts if t)))
check("and nothing else offers to change the theme",
      not hasattr(window, "_act_theme") and not hasattr(window, "_current_theme"), "")
check("theme.toggle and theme.reapply are gone with it",
      not hasattr(theme, "toggle") and not hasattr(theme, "reapply"), "")
check("the default is light",
      theme.apply.__defaults__ == ("light",), str(theme.apply.__defaults__))

corner = window._tabs.cornerWidget(Qt.Corner.TopRightCorner)
check("the logo sits in the tab strip, not the toolbar",
      corner is not None and corner.pixmap() is not None
      and corner.parent() is not toolbar, str(corner))


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All toolbar checks passed.")
