"""Folding the less-used settings away without losing them.

The risk in hiding settings is not that they are hard to find — it is that a
hidden setting stops being *used*: a value that does not reach ``Params``, a
loaded parameter file that silently drops half of what it carried. So most of
what is checked here is that a collapsed section behaves exactly as an open one
does, and only the last few tests are about what is on screen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from meanap.gui.advanced import AdvancedSection, set_all_expanded  # noqa: E402
from meanap.gui.panels.connectivity import ConnectivityPanel  # noqa: E402
from meanap.params import Params  # noqa: E402

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


# ── The section itself ────────────────────────────────────────────────────────

print("\nAdvancedSection")

section = AdvancedSection()
section.form().addRow("One", QLabel("a"))
section.form().addRow("Two", QLabel("b"))
holder = QWidget()
from PyQt6.QtWidgets import QVBoxLayout  # noqa: E402

QVBoxLayout(holder).addWidget(section)
holder.show()
app.processEvents()

check("collapsed by default", not section.is_expanded())
check("contents hidden while collapsed", not section._body.isVisibleTo(holder))
check("header counts what it holds", "(2)" in section.header.text(),
      section.header.text())

seen: list[bool] = []
section.toggled.connect(seen.append)
section.set_expanded(True)
app.processEvents()
check("expanding shows the contents", section._body.isVisibleTo(holder))
check("expanding emits toggled(True)", seen == [True], str(seen))
check("no count while open", "(2)" not in section.header.text(),
      section.header.text())

section.set_expanded(True)
check("setting the same state emits nothing more", seen == [True], str(seen))

section.set_expanded(False)
check("collapsing emits toggled(False)", seen == [True, False], str(seen))

empty = AdvancedSection()
empty.show()
app.processEvents()
check("an empty section shows no count", "(" not in empty.header.text(),
      empty.header.text())


# ── Values survive folding ────────────────────────────────────────────────────

print("\nCollapsed settings are still real settings")

panel = ConnectivityPanel()
panel.show()
app.processEvents()

sections = panel.findChildren(AdvancedSection)
check("connectivity has advanced sections", len(sections) == 2, str(len(sections)))

# Loaded into a collapsed panel, read straight back out.
loaded = Params(trunc_rec=True, trunc_length=45.0, prob_thresh_tail=0.02,
                prob_thresh_plot_checks=True, prob_thresh_plot_checks_n=7)
panel.load(loaded)
check("loading does not force sections open",
      all(not s.is_expanded() for s in sections))

out = Params()
panel.save(out)
check("collapsed values round-trip",
      (out.trunc_rec, out.trunc_length, out.prob_thresh_tail,
       out.prob_thresh_plot_checks, out.prob_thresh_plot_checks_n)
      == (True, 45.0, 0.02, True, 7),
      f"{out.trunc_rec} {out.trunc_length} {out.prob_thresh_tail} "
      f"{out.prob_thresh_plot_checks} {out.prob_thresh_plot_checks_n}")

# And the same when they were opened, edited, and closed again.
set_all_expanded(panel, True)
panel.prob_thresh_tail.setValue(0.1)
set_all_expanded(panel, False)
after = Params()
panel.save(after)
check("an edit made while open survives closing",
      abs(after.prob_thresh_tail - 0.1) < 1e-9, str(after.prob_thresh_tail))

# The settings that a run is normally configured with stay in the open.
check("lag values stay visible", panel.lag_vals.isVisibleTo(panel))
check("iterations stay visible", panel.prob_thresh_rep_num.isVisibleTo(panel))
check("truncation is folded away", not panel.trunc_rec.isVisibleTo(panel))


# ── The window's toggle ───────────────────────────────────────────────────────

print("\nWindow toggle")

from PyQt6.QtCore import QSettings  # noqa: E402

from meanap.gui.advanced import SETTINGS_KEY  # noqa: E402
from meanap.gui.main_window import MainWindow  # noqa: E402

# The window restores this from the real settings store, so pin it rather than
# letting the result depend on how whoever ran this last left their GUI.
_settings = QSettings("SAND Lab", "MEA-NAP")
_previous = _settings.value(SETTINGS_KEY, None)
_settings.setValue(SETTINGS_KEY, False)

window = MainWindow()
window.show()
app.processEvents()

found = window.findChildren(AdvancedSection)
check("window finds its sections", len(found) >= 2, str(len(found)))
check("starts collapsed", all(not s.is_expanded() for s in found))
check("toolbar action is a checkbox, unchecked",
      window._act_advanced.isCheckable() and not window._act_advanced.isChecked())

window._act_advanced.setChecked(True)
app.processEvents()
check("toggling opens every section", all(s.is_expanded() for s in found))

window._act_advanced.setChecked(False)
app.processEvents()
check("toggling again closes them", all(not s.is_expanded() for s in found))

# Whatever the window is showing, a save writes everything.
window._act_advanced.setChecked(False)
saved = window._collect_params()
check("a save from a collapsed window still carries advanced settings",
      saved.prob_thresh_tail == Params().prob_thresh_tail,
      str(saved.prob_thresh_tail))

# A tutorial that points at a folded widget would highlight nothing, so no step
# may target one while the sections are shut.
window._act_advanced.setChecked(False)
app.processEvents()
hidden_targets = []
builders = {
    "meanap": lambda: window._build_meanap_steps(),
    "meastim": lambda: window._build_meastim_steps(),
    "catnap": lambda: window._build_catnap_steps(),
}
for mode_key, build in builders.items():
    window._apply_mode(mode_key, sync_params=False)
    app.processEvents()
    for step in build():
        target = step.target() if callable(step.target) else step.target
        # Some targets resolve to a QRect (the tab bar) rather than a widget.
        if not isinstance(target, QWidget):
            continue
        parent = target
        while parent is not None:
            if isinstance(parent, AdvancedSection) and not parent.is_expanded():
                hidden_targets.append(f"{mode_key}: {step.title}")
                break
            parent = parent.parentWidget()
check("no tutorial step points into a collapsed section",
      not hidden_targets, "; ".join(hidden_targets))


if _previous is None:
    _settings.remove(SETTINGS_KEY)
else:
    _settings.setValue(SETTINGS_KEY, _previous)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All advanced-settings checks passed.")
