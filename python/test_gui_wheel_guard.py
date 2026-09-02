"""Scrolling past a settings field must not retune it.

Run from the repo root::

    uv run python python/test_gui_wheel_guard.py

A spin box or combo box takes the wheel whenever the pointer is over it, so
rolling down a tab of settings used to change whichever fields the pointer
crossed. The page scrolled either way, so there was nothing to notice — the run
simply used a different threshold than the one that had been typed.

What is checked, on the real window rather than a mock-up:

  - a wheel turn over an unfocused field leaves its value alone;
  - the page scrolls anyway, so the wheel does not feel broken;
  - a wheel turn *does* work once the field has been clicked into;
  - the wheel never focuses a field, so the first turn cannot arm the second;
  - the event arrives at a spin box's internal line edit rather than the box
    itself, which is the case a naive guard misses;
  - scroll bars, lists and logs still scroll — the guard must not have been
    written so broadly that it stops the scrolling it exists to protect;
  - an *open* combo box's list scrolls, which is the one case where the wheel
    really does belong to the combo box.

The focus-policy checks are the ones that matter most, and are not decoration
around the behavioural ones. A synthesised wheel event is not spontaneous, so
Qt never runs the focus-granting path a real mouse takes — the first version of
this test passed against a guard that let the first turn on every field through,
because the field was handed focus in ``QApplication::notify`` before the
filter ever saw the event. What can be checked here is the precondition that
path depends on: no field is reachable by the wheel in the first place.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QWheelEvent  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QAbstractScrollArea, QApplication, QComboBox, QDoubleSpinBox, QLineEdit,
    QSpinBox, QTabWidget, QWidget,
)

from meanap.gui.advanced import AdvancedSection  # noqa: E402
from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.modes import MODES  # noqa: E402
from meanap.gui.wheel import GUARDED, _guarded_widget  # noqa: E402

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def wheel(widget: QWidget, steps: int = -1) -> None:
    """Roll the wheel over *widget*, as a mouse does: 120 units per notch."""
    pos = QPointF(widget.rect().center())
    event = QWheelEvent(
        pos, widget.mapToGlobal(pos), QPoint(0, 0), QPoint(0, 120 * steps),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(widget, event)
    app.processEvents()


def scroll_area_of(widget: QWidget) -> QAbstractScrollArea | None:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


print("\nSection A — no field can be focused by the wheel at all")

# The precondition the whole guard rests on, and the one a synthesised wheel
# event cannot exercise: a real turn would have Qt hand the field focus before
# this filter is consulted, and a focused field is one the wheel may change.
for mode in MODES:
    probe_window = MainWindow(mode=mode)
    probe_window.show()
    app.processEvents()
    fields = probe_window.findChildren(GUARDED)
    wheelable = [f for f in fields
                 if f.focusPolicy() == Qt.FocusPolicy.WheelFocus]
    check(f"[{mode}] every field is out of the wheel's reach",
          not wheelable and bool(fields),
          f"{len(wheelable)} of {len(fields)} still on WheelFocus")
    focused = QApplication.focusWidget()
    check(f"[{mode}] the window does not open with a field focused",
          not isinstance(focused, GUARDED),
          f"{type(focused).__name__} has focus and nobody clicked it")
    probe_window.close()

# A field built after the guard was installed — a dialog, or a row a panel adds
# as you use it — is caught when it is polished, not when it is first scrolled.
late = QSpinBox()
check("a newly built spin box starts out wheel-focusable",
      late.focusPolicy() == Qt.FocusPolicy.WheelFocus, str(late.focusPolicy()))
late.ensurePolished()
check("...and is defused by the time it could be shown",
      late.focusPolicy() == Qt.FocusPolicy.StrongFocus, str(late.focusPolicy()))
late.deleteLater()


# The probe windows above are built and closed first on purpose: each one
# becomes the active window while it lives, and the checks below need the
# window they act on to be the active one for focus to mean anything.

window = MainWindow()
# Deliberately short: the guard only matters on a tab that has to scroll, and
# a window tall enough to show everything would test nothing.
window.resize(1000, 520)
window.show()

tabs = window.findChild(QTabWidget)
for index in range(tabs.count()):
    if "Spike" in tabs.tabText(index):
        tabs.setCurrentIndex(index)
        break
# The fields worth guarding are mostly the less-used ones, which live folded
# away — and a folded field is not one the pointer can cross.
for section in window._spike_panel.findChildren(AdvancedSection):
    section.set_expanded(True)
for _ in range(3):
    app.processEvents()

tab = window._spike_panel
spins = [w for w in tab.findChildren((QSpinBox, QDoubleSpinBox)) if w.isVisibleTo(tab)]
combos = [w for w in tab.findChildren(QComboBox) if w.isVisibleTo(tab)]
check("the tab offers fields to scroll past", bool(spins), "no visible spin boxes")


print("\nSection B — a wheel turn over an unfocused field")

spin = spins[0]
area = scroll_area_of(spin)
check("the field really is inside a scrolling tab", area is not None)

bar = area.verticalScrollBar()
bar.setValue(0)
app.processEvents()

before_value = spin.value()
before_scroll = bar.value()
spin.clearFocus()
wheel(spin, steps=-1)

check("the value is left alone", spin.value() == before_value,
      f"{before_value} → {spin.value()}")
check("and the page scrolls instead", bar.value() > before_scroll,
      f"scroll {before_scroll} → {bar.value()} (max {bar.maximum()})")
check("the wheel does not focus the field", not spin.hasFocus())
check("...and cannot, on the next turn either",
      spin.focusPolicy() != Qt.FocusPolicy.WheelFocus,
      str(spin.focusPolicy()))

# The turn that would have done the damage: a second one, now that the old
# WheelFocus would have handed focus over.
before_value = spin.value()
wheel(spin, steps=-1)
check("a second turn still leaves it alone", spin.value() == before_value,
      f"{before_value} → {spin.value()}")


print("\nSection C — the event delivered to the spin box's own line edit")

inner = spin.findChild(QLineEdit)
check("a spin box does have an internal line edit", inner is not None)
if inner is not None:
    spin.clearFocus()
    before_value = spin.value()
    before_scroll = bar.value()
    wheel(inner, steps=-1)
    check("a turn on the line edit does not change the value",
          spin.value() == before_value, f"{before_value} → {spin.value()}")
    check("and still scrolls the page", bar.value() > before_scroll,
          f"scroll {before_scroll} → {bar.value()}")


print("\nSection D — once clicked into, the field is the user's")

spin.setFocus(Qt.FocusReason.MouseFocusReason)
app.processEvents()
check("the field can still be focused", spin.hasFocus())

before_value = spin.value()
before_scroll = bar.value()
wheel(spin, steps=1)
check("a wheel turn now changes the value", spin.value() != before_value,
      f"{before_value} → {spin.value()}")
check("and the page stays put", bar.value() == before_scroll,
      f"scroll {before_scroll} → {bar.value()}")

spin.clearFocus()


print("\nSection E — combo boxes behave the same way")

if not combos:
    check("a combo box was found on this tab", False, "none visible")
else:
    combo = combos[0]
    if combo.count() < 2:
        combo.addItems(["a", "b"])
    combo.setCurrentIndex(0)
    combo.clearFocus()
    app.processEvents()
    wheel(combo, steps=-1)
    check("scrolling past a combo box does not change the selection",
          combo.currentIndex() == 0, f"index {combo.currentIndex()}")
    check("the wheel does not focus it either", not combo.hasFocus())

    combo.setFocus(Qt.FocusReason.MouseFocusReason)
    app.processEvents()
    wheel(combo, steps=-1)
    check("but it does once clicked into", combo.currentIndex() != 0,
          f"index {combo.currentIndex()}")
    combo.clearFocus()


print("\nSection F — the guard does not break ordinary scrolling")

# The tab's own scroll area, scrolled directly rather than through a field.
bar.setValue(0)
app.processEvents()
wheel(area.viewport(), steps=-1)
check("a scroll area still scrolls when the wheel is over open space",
      bar.value() > 0, f"scroll {bar.value()}")

# A scroll bar is a QAbstractSlider, and guarding every one of those would
# have frozen the scrolling this exists to protect.
check("scroll bars were not caught by the guard", not isinstance(bar, GUARDED),
      "a QScrollBar is treated as a guarded field")

# The Run tab's log is a scrolling widget in its own right; scrolling it should
# move its own contents rather than being handed to anything else. It has to be
# the tab on screen first — an unlaid-out log has nothing to scroll, and would
# pass this by doing nothing.
for index in range(tabs.count()):
    if tabs.tabText(index).strip() == "Run":
        tabs.setCurrentIndex(index)
        break
log = window._run_panel.log
log.setPlainText("\n".join(f"line {i}" for i in range(500)))
for _ in range(3):
    app.processEvents()
log.verticalScrollBar().setValue(0)
app.processEvents()
check("the log has something to scroll", log.verticalScrollBar().maximum() > 0,
      f"max {log.verticalScrollBar().maximum()}")
wheel(log.viewport(), steps=-1)
check("a log still scrolls its own contents",
      log.verticalScrollBar().value() > 0,
      f"scroll {log.verticalScrollBar().value()}")

print("\nSection G — an open combo box's own list still scrolls")

# The one place the wheel does belong to a combo box. Its popup is a separate
# window, which is what stops the walk up from the list reaching the combo.
probe = QComboBox(window)
probe.addItems([f"item {i}" for i in range(60)])
probe.showPopup()
app.processEvents()
view = probe.view()
check("the popup is open", view.isVisible())
check("the list inside it is not treated as the combo box",
      _guarded_widget(view) is None, str(_guarded_widget(view)))

popup_bar = view.verticalScrollBar()
check("the list is long enough to scroll", popup_bar.maximum() > 0,
      f"max {popup_bar.maximum()}")
popup_bar.setValue(0)
app.processEvents()
wheel(view.viewport(), steps=-1)
check("and it scrolls", popup_bar.value() > 0, f"scroll {popup_bar.value()}")
probe.hidePopup()

window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All wheel-guard checks passed.")
