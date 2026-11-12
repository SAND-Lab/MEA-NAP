"""Test the settings search, in the classic and simple views.

Run from the repo root::

    uv run python python/test_gui_search.py [screenshot-dir]

  A. matching and ranking, on hand-made entries (no window);
  B. the index the classic window builds: what each mode offers and hides;
  C. choosing a setting: tab, folded section, Run-tab page, focus, outline;
  D. the field itself: typing, arrow keys, Return, Escape, Ctrl+F;
  E. the simple view: its own questions and viewers first, and a detour to
     the tabs that does not change which view opens next time.

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

from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtGui import QKeySequence  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.advanced import AdvancedSection  # noqa: E402
from meanap.gui.main_window import (  # noqa: E402
    MainWindow, load_simple_view_preference, save_simple_view_preference,
)
from meanap.gui.panels.run import QUEUE, THIS_RUN  # noqa: E402
from meanap.gui.settings_search import (  # noqa: E402
    FEATURE, SETTING, Flash, SearchEntry, _has, search,
)

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


def titles(entries) -> list[str]:
    return [e.title for e in entries]


def flashes(window) -> list[Flash]:
    return [f for f in window.findChildren(Flash) if f.isVisible()]


def folded_section(widget) -> AdvancedSection | None:
    w = widget.parentWidget()
    while w is not None:
        if isinstance(w, AdvancedSection):
            return w
        w = w.parentWidget()
    return None


# ── A. Matching ───────────────────────────────────────────────────────────────

def matching_section() -> None:
    print("\nA. Matching and ranking")
    entries = [
        SearchEntry("Sampling frequency", "Data › Recording"),
        SearchEntry("Offset", "Data", keywords="shift the start"),
        SearchEntry("Separate plots", "Results"),
        SearchEntry("Spike source", "Spike detection",
                    keywords="where the spikes come from, at the sampling rate"),
        SearchEntry("Make bundle", "Results", FEATURE),
        SearchEntry("Bundle compression", "Results › Advanced settings"),
    ]
    check("a word start matches", _has("sampling frequency", "freq"))
    check("the middle of a word does not", not _has("offset", "fs")
          and not _has("separate plots", "rate"))
    check("synonyms: 'sampling rate' finds Sampling frequency first",
          titles(search(entries, "sampling rate"))[:1] == ["Sampling frequency"],
          str(titles(search(entries, "sampling rate"))))
    check("'fs' finds Sampling frequency (and sampling-rate talk), not Offset",
          titles(search(entries, "fs")) == ["Sampling frequency", "Spike source"],
          str(titles(search(entries, "fs"))))
    check("a tooltip-only match ranks below a title match",
          titles(search(entries, "sampling")) == ["Sampling frequency", "Spike source"],
          str(titles(search(entries, "sampling"))))
    check("a title that starts with the query comes before one that contains it",
          titles(search(entries, "bundle")) == ["Bundle compression", "Make bundle"],
          str(titles(search(entries, "bundle"))))
    check("every word has to match", search(entries, "sampling bundle") == [])
    check("an empty query finds nothing", search(entries, "   ") == [])
    check("case and hyphens do not matter",
          titles(search(entries, "SAMPLING-freq")) == ["Sampling frequency"])
    rank = [SearchEntry("Spreadsheet", "Data"), SearchEntry("Spreadsheet", "Simple view", rank=0)]
    check("the view on screen wins a tie",
          [e.where for e in search(rank, "spreadsheet")][0] == "Simple view")
    dup = [SearchEntry("Folder", "Data"), SearchEntry("Folder", "Data")]
    check("one name in one place is listed once", len(search(dup, "folder")) == 1)


# ── B. The classic index ──────────────────────────────────────────────────────

def index_section(window: MainWindow) -> None:
    print("\nB. What each mode offers")
    window._apply_mode("meanap")
    pump(50)
    entries = window._search_entries()
    places = {(e.title, e.where.split(" › ")[0]) for e in entries}
    check("MEA-NAP: Data tab settings are found",
          ("Sampling frequency", "Data") in places and ("Channel layout", "Data") in places)
    check("folded advanced settings are found too",
          any(e.title == "Wavelet cost" and "Advanced settings" in e.where for e in entries))
    check("buttons are features", any(e.title == "Make bundle…" and e.kind == FEATURE
                                      for e in entries))
    check("the toolbar's actions are there",
          {"Reset to defaults", "Open params…", "Save params…", "Tutorial",
           "This computer", "Advanced"} <= set(titles(entries)),
          str(sorted(e.title for e in entries if e.where == "Toolbar")))
    check("emoji are not part of a title",
          not any(t[:1] in "📦🌐📂🧪▶■?🖥⚙✦" for t in titles(entries)),
          str([t for t in titles(entries) if t[:1] in "📦🌐📂🧪▶■?🖥⚙✦"]))
    check("no tab of another pipeline", not any(
        e.where.startswith(("Stimulation", "CAT-NAP")) for e in entries))
    check("'Simple view' is offered from the classic view",
          "Simple view" in titles(entries) and "Classic view" not in titles(entries))

    window._apply_mode("catnap")
    pump(50)
    entries = window._search_entries()
    check("CAT-NAP: the recording box it hides is not found",
          not any(e.title == "Sampling frequency" and e.where.startswith("Data")
                  for e in entries),
          str([e.where for e in entries if e.title == "Sampling frequency"]))
    check("and its own tab is",
          any(e.where.startswith("CAT-NAP") for e in entries))

    window._apply_mode("meastim")
    pump(50)
    entries = window._search_entries()
    check("MEA-Stim: the Stimulation tab is found",
          any(e.where.startswith("Stimulation") for e in entries))
    window._apply_mode("meanap")
    pump(50)


# ── C. Choosing a setting ─────────────────────────────────────────────────────

def choose_section(window: MainWindow, shots: Path | None) -> None:
    print("\nC. Choosing a setting")
    box = window._search_box
    window._act_advanced.setChecked(False)
    window._tabs.setCurrentIndex(0)
    pump(50)
    target = window._spike_panel.wavelet_cost if hasattr(
        window._spike_panel, "wavelet_cost") else None
    section_before = None
    entry = next(e for e in window._search_entries() if e.title == "Wavelet cost")
    target = entry.target
    section_before = folded_section(target)
    check("Wavelet cost starts folded away",
          section_before is not None and not section_before.is_expanded())
    chosen = box.choose_text("wavelet cost")
    pump(100)
    check("choosing it picks the right entry", chosen is not None and chosen.title == "Wavelet cost",
          str(chosen))
    check("its tab is shown", window._tabs.currentWidget() is entry.page)
    check("its section is unfolded", section_before.is_expanded())
    check("it is on screen", target.isVisible() and not target.visibleRegion().isEmpty())
    check("it has the focus", target.hasFocus())
    check("it is outlined", len(flashes(window)) == 1)
    check("the field is cleared and the list closed",
          box.text() == "" and not box.results_visible())
    if shots:
        window.grab().save(str(shots / "search_flash.png"))
    pump(Flash.DURATION_MS + 200)
    check("the outline goes away", flashes(window) == [])

    window._run_panel.set_mode(QUEUE)
    pump(30)
    chosen = box.choose_text("verbose level")
    pump(100)
    check("a Run-tab setting switches the Run tab back to 'This run'",
          window._run_panel.mode() == THIS_RUN and chosen.target.isVisible(),
          f"{window._run_panel.mode()} / {chosen.target.isVisible()}")

    before = window._act_advanced.isChecked()
    chosen = box.choose_text("advanced")
    pump(30)
    check("a toolbar feature runs", chosen.where == "Toolbar"
          and window._act_advanced.isChecked() != before, str(chosen))
    window._act_advanced.setChecked(False)
    pump(30)


# ── D. The field ──────────────────────────────────────────────────────────────

def field_section(window: MainWindow, shots: Path | None) -> None:
    print("\nD. The field")
    box = window._search_box
    window._tabs.setCurrentIndex(0)
    pump(30)
    QTest.keySequence(window._tabs, QKeySequence(QKeySequence.StandardKey.Find))
    pump(30)
    check("Ctrl+F puts the cursor in the search", box.hasFocus())
    QTest.keyClicks(box, "layout")
    pump(30)
    check("typing shows matches", box.results_visible() and len(box.matches()) >= 2,
          str(titles(box.matches())))
    check("the list sits below the field and above everything else",
          box._list.parentWidget() is window
          and box._list.geometry().top() >= box.mapTo(window, box.rect().bottomLeft()).y())
    if shots:
        window.grab().save(str(shots / "search_list.png"))
    second = box.matches()[1]
    QTest.keyClick(box, Qt.Key.Key_Down)
    QTest.keyClick(box, Qt.Key.Key_Return)
    pump(100)
    check("Down then Return chooses the second match",
          window._tabs.currentWidget() is second.page and second.target.isVisible(),
          f"{second.title} / {second.where}")
    box.setFocus()
    QTest.keyClicks(box, "zzzz")
    pump(30)
    check("no match says so rather than showing nothing",
          box.results_visible() and box._list.count() == 1 and box.matches() == [])
    QTest.keyClick(box, Qt.Key.Key_Escape)
    check("Escape closes the list", not box.results_visible() and box.text() == "zzzz")
    QTest.keyClick(box, Qt.Key.Key_Escape)
    check("a second Escape clears the field", box.text() == "")


# ── E. The simple view ────────────────────────────────────────────────────────

def simple_section(window: MainWindow, shots: Path | None) -> None:
    print("\nE. The simple view")
    save_simple_view_preference(True)
    window._set_simple_view(True, remember=False)
    view = window._simple_view
    pump(50)
    box = view.search_box
    check("the simple view has its own search field", box.isVisible())
    entries = window._search_entries()
    first = view._steps[0].card.title.text()
    found = search(entries, first)
    check("its open question is found, ahead of the tabs",
          found and found[0].where.startswith("Simple view") and found[0].kind == SETTING,
          str([(e.title, e.where) for e in found[:3]]))
    check("questions not asked yet are left out",
          not any(e.where.endswith("Analyse recordings") and e.target is step.card
                  for e in entries for step in view._steps if step.card.state == "hidden"))
    check("'Classic view' is offered, 'Simple view' is not",
          "Classic view" in titles(entries) and "Simple view" not in titles(entries))

    box.choose_text(first)
    pump(400)
    check("choosing a question stays in the simple view", window.is_simple_view())
    check("and outlines its card", any(f._target is view._steps[0].card for f in flashes(window)))
    if shots:
        window.grab().save(str(shots / "search_simple.png"))

    chosen = box.choose_text("network viewer")
    pump(100)
    check("a viewer goes to View results", chosen is not None
          and chosen.where.startswith("Simple view") and view.page() == "results"
          and window.is_simple_view(), str(chosen))

    chosen = box.choose_text("switch to mea-stim")
    pump(100)
    check("a pipeline can be switched to", window._mode == "meastim", str(chosen))
    window._apply_mode("meanap")
    pump(50)

    chosen = box.choose_text("wavelet cost")
    pump(400)
    check("a setting in an 'Other settings' section opens in the panel, on the page",
          window.is_simple_view() and view.drawer.is_open()
          and view.drawer.section().isAncestorOf(chosen.target)
          and chosen.target.isVisible(), str(chosen))
    view.close_section()

    # The Results tab's viewer is not a settings area, so only the tabs have it.
    chosen = box.choose_text("node layout")
    pump(150)
    check("a setting only the tabs have opens the classic view on it",
          chosen is not None and not window.is_simple_view() and chosen.target.isVisible(),
          str(chosen))
    check("without changing which view opens next time", load_simple_view_preference())
    save_simple_view_preference(False)


def main() -> int:
    sys.excepthook = _excepthook
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    matching_section()
    save_simple_view_preference(False)
    window = MainWindow()
    sys.excepthook = _excepthook
    window._set_simple_view(False, remember=False)
    window.resize(1200, 800)
    window.show()
    pump(100)
    index_section(window)
    choose_section(window, shots)
    field_section(window, shots)
    simple_section(window, shots)
    window.close()
    pump(50)
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
