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

# ── Nothing is lost by folding, anywhere in the window ────────────────────────

print("\nEvery section, every mode")

import dataclasses  # noqa: E402

# Values that all live inside advanced sections, spread across every tab that
# has one. Picked to be visibly different from the defaults so a widget that
# silently reset itself would show up.
FOLDED = dict(
    # Data
    spreadsheet_range="A5:A99", custom_grp_order=["KO", "WT"],
    spike_detected_data="/tmp/spikes", d_samp_f=500.0,
    potential_difference_unit="mV",
    # Connectivity
    trunc_rec=True, trunc_length=45.0, prob_thresh_tail=0.02,
    prob_thresh_plot_checks=True, prob_thresh_plot_checks_n=9,
    # Spike detection
    run_spike_check_on_prev_spike_data=True, abs_thresholds=[12.0, 18.0],
    cost_list=-0.3, filter_low_pass=300.0, filter_high_pass=6000.0,
    ref_period=1.5, n_spikes=250, multiple_templates=True,
    multi_template_method="PCA",
    # Run
    optional_steps_to_run=["generateCSV"], verbose_level="Debug",
    time_processes=True, random_seed=99,
    # Stimulation
    min_blanking_duration=0.009, stim_n_shuffles=750, stim_shuffle_alpha=0.01,
    # CAT-NAP
    twop_denoising_time_before_peak=0.9, twop_denoising_time_after_peak=2.5,
    twop_redo_denoising=True,
)

for mode_key in ("meanap", "meastim", "catnap"):
    window._apply_mode(mode_key, sync_params=False)
    set_all_expanded(window, False)
    app.processEvents()

    window._load_params(Params(**FOLDED))
    collapsed = window._collect_params()

    set_all_expanded(window, True)
    app.processEvents()
    expanded = window._collect_params()

    # The strong form: not "these fields survived" but "folding changes nothing
    # about what a run would do", over every field Params has.
    differing = [f.name for f in dataclasses.fields(Params)
                 if getattr(collapsed, f.name) != getattr(expanded, f.name)]
    check(f"{mode_key}: an open window and a folded one save the same run",
          not differing, ", ".join(differing))

    wrong = [name for name, value in FOLDED.items()
             if name in {f.name for f in dataclasses.fields(Params)}
             and getattr(collapsed, name) != value]
    check(f"{mode_key}: every folded setting round-trips through the window",
          not wrong, ", ".join(f"{n}={getattr(collapsed, n)!r}" for n in wrong))

    set_all_expanded(window, False)

# Sixteen sections is the point of the exercise: the count is asserted loosely
# so adding one is not a test failure, but losing them all would be.
sections = window.findChildren(AdvancedSection)
check("every tab that has settings has folded some of them",
      len(sections) >= 14, str(len(sections)))
check("and every header says how many it holds",
      all("(" in s.header.text() for s in sections),
      str([s.header.text() for s in sections if "(" not in s.header.text()]))


# A tutorial step may well point at a folded setting — the tutorial is where
# someone finds out these exist — so what matters is that showing the step opens
# what it is pointing at. Walk every step of every mode and check the target is
# on screen by the time the coach-mark is drawn.
window._act_advanced.setChecked(False)
app.processEvents()

invisible = []
for mode_key in ("meanap", "meastim", "catnap"):
    window._start_tutorial()
    window._on_pipeline_chosen(mode_key)
    app.processEvents()
    tutorial = window._tutorial
    for i, step in enumerate(tutorial._steps):
        target = step.target() if callable(step.target) else step.target
        # Some targets resolve to a QRect (the tab bar) rather than a widget.
        if isinstance(target, QWidget) and not target.isVisible():
            invisible.append(f"{mode_key}: {step.title}")
        tutorial._next()
        app.processEvents()

check("every tutorial target is on screen when its step is shown",
      not invisible, "; ".join(invisible))

# And specifically: the ones inside advanced sections got there by being opened.
# Collapsed directly rather than through the toolbar action, which emits nothing
# when it is already unchecked — as it is, after the walk above opened sections.
set_all_expanded(window, False)
window._apply_mode("meanap", sync_params=False)
app.processEvents()
section = None
for candidate in window._data_panel.findChildren(AdvancedSection):
    if window._data_panel.spreadsheet_range in candidate.findChildren(QWidget):
        section = candidate
check("the spreadsheet-range setting is folded away to begin with",
      section is not None and not section.is_expanded(), str(section))

window._start_tutorial()
window._on_pipeline_chosen("meanap")
app.processEvents()
for _ in window._tutorial._steps:
    if window._tutorial._steps[window._tutorial._index].title == "Spreadsheet range":
        break
    window._tutorial._next()
    app.processEvents()
check("reaching that step opens the section rather than pointing at nothing",
      section is not None and section.is_expanded()
      and window._data_panel.spreadsheet_range.isVisible(), "")

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
