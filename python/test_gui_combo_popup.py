"""A dropdown has to be wide enough for the options it is listing.

Run from the repo root::

    uv run python python/test_gui_combo_popup.py

Qt opens a combo box's popup at the width of the *box*. The box is sized by the
form around it, and the popup does not draw its rows the way the box does — it
adds a check-mark column (18px under this theme, plus 6px of spacing) to the
left of every row, out of the same width. On "Verbose level" that left 48px of
a 50px word, and the options came out clipped.

The condition for a row to be drawn in full is therefore

    popup viewport ≥ check column + spacing + the widest option

and that is what these checks assert — on the popup Qt actually opens, not on
the width we asked for. The rest hold the two properties that make the fix safe
to leave installed everywhere: combo boxes built or filled *later* are covered
too, and no box is resized (widening those would reflow every settings form to
suit the longest word in a dropdown).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtGui import QFontMetrics  # noqa: E402
from PyQt6.QtWidgets import QApplication, QComboBox, QStyle  # noqa: E402

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
# Widths depend on the style, so measure under the one the app actually ships.
theme.apply(app)

from meanap.gui.advanced import AdvancedSection  # noqa: E402
from meanap.gui.combo import popup_width  # noqa: E402
from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.panels.pipeline import PipelinePanel  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def needed(combo: QComboBox) -> int:
    """What one row has to draw: the check column, its gap, and the text.

    Deliberately computed here from the style rather than imported from
    ``gui.combo`` — a test that asks the code under test what the answer is
    only proves it is consistent with itself.
    """
    view = combo.view()
    style = view.style()
    metrics = QFontMetrics(view.font())
    return (
        max(metrics.horizontalAdvance(combo.itemText(i))
            for i in range(combo.count()))
        + style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, view)
        + style.pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing, None, view)
    )


window = MainWindow()
window.resize(1200, 900)
window.show()
# The settings this is really about live in folded sections; open them so the
# boxes are laid out at the width the form gives them, not at a placeholder.
for section in window.findChildren(AdvancedSection):
    section.header.setChecked(True)
app.processEvents()

combos = [c for c in window.findChildren(QComboBox) if c.count()]
verbose = window.findChildren(PipelinePanel)[0].verbose_level


print("The dropdown this started with")

# The bug, stated as the measurement that showed it: at the width Qt would have
# used, the row had less room than it needed. If this ever stops holding the
# fix is no longer being tested by the case that motivated it.
frame = 2 * verbose.view().frameWidth()
check("'Verbose level' is a box too narrow for its own options",
      verbose.width() - frame < needed(verbose),
      f"box {verbose.width()} - frame {frame} vs needed {needed(verbose)}")

verbose.showPopup()
app.processEvents()
opened = verbose.view().parentWidget().width()
viewport = verbose.view().viewport().width()
check("but the popup it opens is wide enough for them",
      viewport >= needed(verbose),
      f"viewport {viewport} vs needed {needed(verbose)}")
check("and it is wider than the box, not the same as it",
      opened > verbose.width(), f"{opened} vs {verbose.width()}")
verbose.hidePopup()


print("\nEvery other dropdown in the window")

too_narrow = [
    (c.currentText(), c.view().minimumWidth(), needed(c))
    for c in combos if c.view().minimumWidth() < needed(c)
]
check("no dropdown lists options it cannot draw",
      not too_narrow, str(too_narrow[:3]))

# A popup that is wider than the screen is a different bug in the same place.
screen_width = window.screen().availableGeometry().width()
overflowing = [(c.currentText(), popup_width(c))
               for c in combos if popup_width(c) > screen_width]
check("and none of them runs off the screen", not overflowing, str(overflowing[:3]))

check("the boxes themselves were left alone",
      all(c.minimumWidth() == 0 for c in combos),
      str([c.currentText() for c in combos if c.minimumWidth()][:3]))


print("\nDropdowns built or filled later")

# The reason this is an application-wide filter rather than a sweep: the panels
# that add rows as you use them are the ones with the long labels.
late = QComboBox(window)
late.addItems(["Short", "Excitatory (NeuN+ & ~GAD+) — a deliberately long label"])
late.show()
app.processEvents()          # Polish fires here, and with it the fitter
check("a box built after the window is covered too",
      late.view().minimumWidth() >= needed(late),
      f"{late.view().minimumWidth()} vs {needed(late)}")

before = late.view().minimumWidth()
late.addItem("An option longer than any of the ones it was created with, by far")
check("and refits when an option is added",
      late.view().minimumWidth() > before
      and late.view().minimumWidth() >= needed(late),
      f"{before} → {late.view().minimumWidth()}, needs {needed(late)}")

late.clear()
late.addItems(["a", "b"])
check("and again when its options are replaced wholesale",
      late.view().minimumWidth() >= needed(late),
      f"{late.view().minimumWidth()} vs {needed(late)}")

empty = QComboBox(window)
empty.show()
app.processEvents()
check("an empty box asks for nothing rather than raising",
      popup_width(empty) == 0, str(popup_width(empty)))


print("\nLong lists")

# A list longer than the popup shows scrolls, and the scroll bar comes out of
# the width — so the option text would be clipped again on exactly the lists
# that need the room most.
long_list = QComboBox(window)
long_list.addItems([f"Recording {i:02d} — a name of realistic length" for i in range(40)])
long_list.show()
app.processEvents()
bar = long_list.style().pixelMetric(
    QStyle.PixelMetric.PM_ScrollBarExtent, None, long_list.view())
check("a scrolling list leaves room for its scroll bar",
      long_list.view().minimumWidth() >= needed(long_list) + bar,
      f"{long_list.view().minimumWidth()} vs {needed(long_list) + bar}")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All combo-popup checks passed.")
