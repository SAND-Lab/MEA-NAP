"""Test the simple view's "Other settings" card and the panel it opens.

Run from the repo root::

    uv run python python/test_gui_simple_settings.py [screenshot-dir]

  A. which areas and sections each pipeline lists, and in what order;
  B. counting settings changed from the defaults — and not the ones the
     questions ask for;
  C. opening a section: the tab's own box, borrowed and given back, edits
     kept, every way of closing;
  D. the panel is closed (and the box returned) whenever the tabs could need it.

Nothing here touches the person's own settings.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QPoint, QSettings, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QScrollArea, QSplitter  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.main_window import (  # noqa: E402
    MainWindow, load_simple_view_preference, save_simple_view_preference,
)
from meanap.gui.modes import TAB_CATNAP, TAB_CONNECTIVITY, TAB_RUN, TAB_SPIKE  # noqa: E402
from meanap.gui.simple_settings import summarise  # noqa: E402

FAILURES: list[str] = []
ERRORS: list[str] = []


def _excepthook(kind, value, tb) -> None:
    ERRORS.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def pump(ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def area(view, key):
    return next((a for a in view.settings_card.areas() if a.key == key), None)


def section_index(view, key, title):
    return [s.title for s in area(view, key).sections].index(title)


def page_of(window, key):
    return next(page for k, page, _ in window._tab_specs if k == key)


# ── A. Areas and sections ─────────────────────────────────────────────────────

def areas_section(window) -> None:
    print("\nA. Areas and sections")
    view = window._simple_view
    titles = {}
    for mode in ("meanap", "meastim", "catnap"):
        window._apply_mode(mode)
        pump(30)
        titles[mode] = [a.title for a in view.settings_card.areas()]
    check("MEA-NAP: data, spike detection, connectivity, steps",
          titles["meanap"] == ["Recordings and output", "Spike detection",
                               "Connectivity and networks", "Pipeline steps and figures"],
          str(titles["meanap"]))
    check("MEA-Stim adds Stimulation", "Stimulation" in titles["meastim"]
          and "Stimulation" not in titles["meanap"], str(titles["meastim"]))
    check("CAT-NAP has calcium imaging instead of spike detection",
          "Calcium imaging" in titles["catnap"] and "Spike detection" not in titles["catnap"],
          str(titles["catnap"]))
    check("no viewer or stats tab is an area",
          not any("Results" in t or "Stats" in t or "Preview" in t
                  for ts in titles.values() for t in ts))

    window._apply_mode("catnap")
    pump(30)
    data = [s.title for s in view.settings_card.areas()[0].sections]
    check("CAT-NAP: the Recording box it hides is not a section", "Recording" not in data,
          str(data))
    catnap = [s.title for s in area(view, TAB_CATNAP).sections]
    check("CAT-NAP: logs, previews and the scan list are not sections",
          not {"Log", "Trace preview", "Suite2p recordings"} & set(catnap), str(catnap))
    check("sections in the tab's order: left column, then right",
          catnap[-1].startswith("Cell types"), str(catnap))
    window._apply_mode("meanap")
    pump(30)
    run = [s.title for s in area(view, TAB_RUN).sections]
    check("Run tab: settings only, not the run controls",
          run == ["Pipeline steps", "Output"], str(run))
    spike = [s.title for s in area(view, TAB_SPIKE).sections]
    check("Spike detection's sections in order",
          spike == ["Detection control", "Thresholds", "Active electrodes", "Wavelet"],
          str(spike))
    check("the card is numbered after the questions",
          view.settings_card.badge.text() == str(len(view._steps) + 1))


# ── B. Changed from the defaults ──────────────────────────────────────────────

def changes_section(window) -> None:
    print("\nB. Changed from the defaults")
    view = window._simple_view
    card = view.settings_card
    view.refresh_settings()
    check("a fresh window has nothing changed",
          card.total_changed() == 0 and card.summary.text() == "All at defaults",
          card.summary.text())

    window._data_panel.raw_data.line_edit.setText("/tmp/some/recordings")
    window._data_panel.output_data_folder.line_edit.setText("/tmp/some/output")
    window._data_panel.channel_layout.setCurrentText("Axion64")
    view.refresh_settings()
    check("answering the questions is not changing a default", card.total_changed() == 0,
          str([c.name for a in card.areas() for c in a.changed]))

    old = window._spike_panel.thresholds.text()
    window._spike_panel.thresholds.setText("3.5, 5.0")
    view.refresh_settings()
    spike = area(view, TAB_SPIKE)
    check("a changed threshold is counted against Spike detection",
          [c.name for c in spike.changed] == ["thresholds"], str(spike.changed))
    check("the card says how many", card.summary.text() == "1 changed from the defaults",
          card.summary.text())
    row = card.rows[TAB_SPIKE]
    pump(20)  # a newly laid-out child is shown on the next pass of the event loop
    check("the row shows the count", row.changed.isVisibleTo(card) and row.changed.text() == "1",
          f"{row.changed.isVisibleTo(card)} {row.changed.isHidden()} {row.changed.text()!r} {row.isVisibleTo(card)}")
    check("its tooltip says what changed",
          "thresholds: [4, 5] → [3.5, 5]" in row.toolTip(), row.toolTip())
    check("the summary shows the new value", "thresholds 3.5, 5" in spike.summary,
          spike.summary)
    window._spike_panel.thresholds.setText(old)

    from meanap.gui.modes import default_params
    window._load_params(default_params("meanap"))
    pump(30)
    check("loading the defaults counts nothing again", card.total_changed() == 0,
          str([c.name for a in card.areas() for c in a.changed]))

    p = default_params("meanap")
    p.trunc_rec, p.trunc_length = True, 60.0
    p.express_mode = True
    check("summaries read as sentences",
          summarise("data", p) == "First 60 s of each recording"
          and summarise("run", p) == "steps 1–4 · figures png · express mode",
          f"{summarise('data', p)!r} / {summarise('run', p)!r}")


# ── C. The panel ──────────────────────────────────────────────────────────────

def panel_section(window, shots: Path | None) -> None:
    print("\nC. The panel")
    view = window._simple_view
    card = view.settings_card
    drawer = view.drawer
    page = page_of(window, TAB_SPIKE)
    card.expand(TAB_SPIKE)
    pump(30)
    links = card.links[TAB_SPIKE]
    check("an unfolded area lists its sections", [l.isVisibleTo(card) for l in links] == [True] * 4)
    index = section_index(view, TAB_SPIKE, "Thresholds")
    box = area(view, TAB_SPIKE).sections[index].box
    parent_before = box.parentWidget()
    layout_index = parent_before.layout().indexOf(box)

    links[index].click()
    pump(300)
    check("clicking a section opens the panel", drawer.is_open() and drawer.isVisible())
    check("holding the tab's own box",
          drawer.section() is box and drawer.isAncestorOf(box) and not page.isAncestorOf(box))
    check("headed by area and section, without the box repeating its title",
          drawer.area_label.text() == "Spike detection"
          and drawer.title_label.text() == "Thresholds" and box.title() == "")
    check("the panel sits at the right, within the page",
          drawer.panel.geometry().right() <= view.width()
          and drawer.panel.geometry().left() > 0, str(drawer.panel.geometry()))
    if shots:
        window.grab().save(str(shots / "settings_panel.png"))

    edit = window._spike_panel.thresholds
    check("its fields are on screen", edit.isVisible())
    edit.setText("4.5")
    check("an edit made there is what a run uses",
          window._collect_params().thresholds == [4.5],
          str(window._collect_params().thresholds))

    drawer.done_button.click()
    pump(30)
    check("Done closes it", not drawer.is_open() and not drawer.isVisible())
    check("and the box is back where it was, title and all",
          box.parentWidget() is parent_before
          and parent_before.layout().indexOf(box) == layout_index
          and box.title() == "Thresholds" and page.isAncestorOf(box),
          f"{parent_before.layout().indexOf(box)} vs {layout_index}")
    check("no placeholder is left behind",
          not page.findChildren(type(box.parentWidget()), "loanPlaceholder"))
    check("the edit survives, and the card counts it",
          window._collect_params().thresholds == [4.5]
          and [c.name for c in area(view, TAB_SPIKE).changed] == ["thresholds"],
          f"{window._collect_params().thresholds} {area(view, TAB_SPIKE).changed}")
    edit.setText("4.0, 5.0")

    view.open_section(TAB_SPIKE, index)
    pump(250)
    QTest.keyClick(drawer.done_button, Qt.Key.Key_Escape)
    pump(30)
    check("Escape closes it", not drawer.is_open() and page.isAncestorOf(box))

    view.open_section(TAB_SPIKE, index)
    pump(250)
    QTest.mouseClick(drawer, Qt.MouseButton.LeftButton, pos=QPoint(20, 200))
    pump(30)
    check("so does a click beside it", not drawer.is_open() and page.isAncestorOf(box))

    # A folded-away section inside the box opens and closes with it as usual.
    wavelet = section_index(view, TAB_SPIKE, "Wavelet")
    view.open_section(TAB_SPIKE, wavelet)
    pump(250)
    check("a different section replaces the box in the panel",
          drawer.title_label.text() == "Wavelet")
    view.open_section(TAB_SPIKE, index)
    pump(250)
    wavelet_box = area(view, TAB_SPIKE).sections[wavelet].box
    check("and the one it replaced goes home first",
          drawer.section() is box and page.isAncestorOf(wavelet_box)
          and wavelet_box.title() == "Wavelet")
    view.close_section()

    # The Run tab's settings are a page of a stack.
    run_index = section_index(view, TAB_RUN, "Output")
    run_box = area(view, TAB_RUN).sections[run_index].box
    run_parent = run_box.parentWidget()
    view.open_section(TAB_RUN, run_index)
    pump(250)
    check("a Run-tab section opens", drawer.section() is run_box and run_box.isVisible())
    view.close_section()
    check("and goes back to its page", run_box.parentWidget() is run_parent)

    # CAT-NAP's cell-type box is in a splitter, not a layout.
    window._apply_mode("catnap")
    pump(50)
    cells = section_index(view, TAB_CATNAP, "Cell types: subnetworks and comparisons")
    cell_box = area(view, TAB_CATNAP).sections[cells].box
    splitter = cell_box.parentWidget()
    position = splitter.indexOf(cell_box) if isinstance(splitter, QSplitter) else -1
    view.open_section(TAB_CATNAP, cells)
    pump(250)
    check("a box in a splitter can be borrowed",
          drawer.section() is cell_box and isinstance(splitter, QSplitter))
    view.close_section()
    check("and goes back into the same pane",
          cell_box.parentWidget() is splitter and splitter.indexOf(cell_box) == position)
    window._apply_mode("meanap")
    pump(50)


# ── D. Closed whenever the tabs could need it ─────────────────────────────────

def lifecycle_section(window) -> None:
    print("\nD. Giving it back")
    view = window._simple_view
    drawer = view.drawer
    page = page_of(window, TAB_CONNECTIVITY)
    view.open_section(TAB_CONNECTIVITY, 0)
    pump(250)
    box = drawer.section()
    window._set_simple_view(False, remember=False)
    pump(30)
    check("switching to the tabs puts the box back on its tab",
          not drawer.is_open() and page.isAncestorOf(box))
    window._tabs.setCurrentWidget(page)
    pump(30)
    check("where the tab shows it", box.isVisible())
    window._set_simple_view(True, remember=False)
    pump(30)

    view.open_section(TAB_CONNECTIVITY, 0)
    pump(250)
    window._apply_mode("meastim")
    pump(30)
    check("switching pipeline puts it back", not drawer.is_open() and page.isAncestorOf(box))
    window._apply_mode("meanap")
    pump(30)

    view.open_section(TAB_CONNECTIVITY, 0)
    pump(250)
    window._search_box.focus_search()  # the classic box: index without the panel
    entries = window._search_entries()
    check("searching puts it back, so the index finds its settings",
          not drawer.is_open() and any(e.target is not None and box.isAncestorOf(e.target)
                                       for e in entries))

    save_simple_view_preference(True)
    chosen = view.search_box.choose_text("lag values")
    pump(400)
    check("a setting found by the search opens in the panel",
          chosen is not None and window.is_simple_view() and drawer.is_open()
          and drawer.section().isAncestorOf(chosen.target) and chosen.target.isVisible(),
          str(chosen))
    check("with its area unfolded on the card",
          view.settings_card.rows[TAB_CONNECTIVITY].isChecked())
    check("and the simple view still opens next time", load_simple_view_preference())
    view.close_section()
    save_simple_view_preference(False)


def main() -> int:
    sys.excepthook = _excepthook
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    save_simple_view_preference(False)
    window = MainWindow()
    sys.excepthook = _excepthook
    if window._tutorial is not None:
        window._tutorial.hide()
    window._set_simple_view(True, remember=False)
    window.resize(1200, 800)
    window.show()
    pump(100)
    areas_section(window)
    changes_section(window)
    panel_section(window, shots)
    lifecycle_section(window)
    window.close()
    pump(50)
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
