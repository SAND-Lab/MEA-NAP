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
      and first_named == "Reset to defaults", f"{first_named!r} / {texts[:4]}")

# Opening a bundle lives with the other things you do to a finished run.
check("the toolbar is parameters, advanced and help — nothing about results",
      not any("bundle" in t.lower() or "report" in t.lower() for t in texts),
      ", ".join(t for t in texts if t))


# ── Switching it still works ──────────────────────────────────────────────────

print("\nPicking a pipeline")

for key, expected in (("catnap", "CAT-NAP (calcium imaging)"), ("meastim", "Stimulation"),
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

# ── The logo follows the mode ─────────────────────────────────────────────────
#
# All three modes have artwork, so switching must show each one's own. A mode
# whose file has gone missing still has to fall back to MEA-NAP's rather than
# break the window, so that is checked by pointing one mode at a missing file.

print("\nPer-mode branding")

from meanap.gui import branding  # noqa: E402

check("every mode has its own artwork",
      set(branding.available_logos()) == set(branding.LOGO_FILES),
      str(branding.available_logos()))
check("an unknown mode falls back, rather than raising",
      branding.logo_path("nonsense") == branding.LOGO_PATH, "")

# ── The logo is drawn whole ───────────────────────────────────────────────────
#
# Qt gives a QTabWidget corner widget the height of a *tab*, so the logo's size
# is not ours to pick alone: it is capped by the tab padding in theme's QSS,
# and a logo taller than that is silently clipped rather than making room. The
# two were tuned together, and nothing in either file makes the dependency
# visible at the point of edit, so it is pinned here instead.

label_h = corner.height()
pixmap_h = round(corner.pixmap().height() / corner.pixmap().devicePixelRatio())
check("the tabs leave room for the logo, so it is not drawn clipped",
      label_h >= branding.CORNER_LOGO_HEIGHT,
      f"tab strip gives {label_h}px, logo wants {branding.CORNER_LOGO_HEIGHT}px"
      " — raise the QTabBar::tab padding in theme._EXTRA_QSS")
check("and the artwork is rendered at that height, not some other one",
      pixmap_h == branding.CORNER_LOGO_HEIGHT,
      f"pixmap is {pixmap_h}px, expected {branding.CORNER_LOGO_HEIGHT}px")
# A QLabel reports its pixmap as its minimum, and from the tab corner that
# minimum reaches the window — a bigger logo would quietly raise the smallest
# height the window can take, which is what test_gui_window_resize guards.
check("and it does not become a floor under the window's height",
      corner.minimumSizeHint().height() == 0,
      f"logo demands {corner.minimumSizeHint().height()}px of the window")

seen = {}
for mode_key in ("meanap", "catnap", "meastim"):
    window._apply_mode(mode_key)
    seen[mode_key] = corner.pixmap().toImage()
    check(f"switching to {mode_key} leaves its logo at full height",
          round(corner.pixmap().height() / corner.pixmap().devicePixelRatio())
          == branding.CORNER_LOGO_HEIGHT, "")
check("switching to CAT-NAP swaps the logo",
      seen["catnap"] != seen["meanap"], "")
check("switching to MEA-Stim swaps the logo",
      seen["meastim"] != seen["meanap"] and seen["meastim"] != seen["catnap"], "")
window._apply_mode("meastim")
check("a branded mode names itself in the tooltip",
      "MEA-Stim" in corner.toolTip(), corner.toolTip())

real_file = branding.LOGO_FILES["meastim"]
branding.LOGO_FILES["meastim"] = "no-such-logo.png"
branding.available_logos.cache_clear()
try:
    window._apply_mode("meastim")
    check("a mode whose file is missing keeps the fallback",
          corner.pixmap().toImage() == seen["meanap"], "")
    check("and the tooltip says it is MEA-NAP's",
          corner.toolTip().startswith("MEA-NAP"), corner.toolTip())
finally:
    branding.LOGO_FILES["meastim"] = real_file
    branding.available_logos.cache_clear()
    window._apply_mode("meanap")

# The tutorial's opening screen shows the same branding as the mode it opened in.
from PyQt6.QtWidgets import QLabel  # noqa: E402

for mode_key, name in (("meanap", "MEA-NAP"), ("catnap", "CAT-NAP"), ("meastim", "MEA-Stim")):
    window._apply_mode(mode_key)
    window._start_tutorial()
    labels = window._tutorial._bubble.findChildren(QLabel)
    logos = [lab.pixmap().toImage() for lab in labels if not lab.pixmap().isNull()]
    expected = branding.logo_pixmap(96, window._tutorial.devicePixelRatioF(), mode_key)
    check(f"the tutorial opens with {name}'s logo in {name} mode",
          len(logos) == 1 and logos[0] == expected.toImage(), f"{len(logos)} logos")
    check(f"and welcomes the user to {name}",
          any(lab.text() == f"Welcome to {name}" for lab in labels),
          str([lab.text() for lab in labels][:3]))
    window._tutorial.hide()
window._apply_mode("meanap")


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All toolbar checks passed.")
