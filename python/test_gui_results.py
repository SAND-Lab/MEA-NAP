"""The Results tab: what it opens, and whether it says so.

**View report** never named the thing it would open. It falls back to the folder
the current settings describe, so in a fresh session pointed at yesterday's
paths it acts on a run nobody mentioned; and for an express run it opens a
bundle in the viewer rather than a report at all. Most of these checks are about
the label that now says which of those is about to happen.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.modes import MODES, TAB_RESULTS  # noqa: E402
from meanap.gui.panels.network_viewer import NetworkViewerPanel  # noqa: E402

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


window = MainWindow()
window.show()
app.processEvents()
panel = window._results_panel


# ── Where it sits ─────────────────────────────────────────────────────────────

print("\nThe tab")

titles = [window._tabs.tabText(i).strip() for i in range(window._tabs.count())]
check("Results is a tab", "Results" in titles, str(titles))
check("and it is the last one — the workflow ends there",
      titles[-1] == "Results", str(titles))
check("there is no separate Network Viewer tab any more",
      "Network Viewer" not in titles, str(titles))
check("the viewer is inside Results instead",
      isinstance(panel.viewer, NetworkViewerPanel)
      and panel.viewer.window() is window, "")
check("every mode has it", all(TAB_RESULTS in m.tabs for m in MODES.values()),
      str([k for k, m in MODES.items() if TAB_RESULTS not in m.tabs]))
check("the Run tab no longer carries a report button",
      not hasattr(window._run_panel, "view_report_btn"), "")


# ── What it says it will open ─────────────────────────────────────────────────

print("\nWhat View report would open")

window._last_output_root = None
window._last_bundle = None
window._data_panel.output_data_folder.set_value("")
window._refresh_results_target()
text = panel.target_label.text()
check("with nothing to open, it says so rather than offering a dead button",
      not panel.view_report_btn.isEnabled() and "Nothing to open" in text, text)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # A folder that has not been written yet — the commonest fresh-session case,
    # and the one that used to give a warning box only after you pressed it.
    window._data_panel.output_data_folder.set_value(str(tmp))
    window._data_panel.output_data_folder_name.setText("NotRunYet")
    window._refresh_results_target()
    text = panel.target_label.text()
    check("a named-but-missing folder is named, and the button is off",
          not panel.view_report_btn.isEnabled()
          and "NotRunYet" in text and "does not exist" in text, text)

    # A real output folder → the HTML report.
    run = tmp / "OutputData09Aug2026"
    (run / "4A_IndividualNetworkAnalysis").mkdir(parents=True)
    window._last_output_root = run
    window._refresh_results_target()
    text = panel.target_label.text()
    check("an existing run offers its report, by name",
          panel.view_report_btn.isEnabled()
          and "OutputData09Aug2026" in text and "report" in text.lower(), text)

    # An express run leaves a bundle beside the folder, and that wins — the
    # folder holds almost no figures, so a report built from it looks like a
    # failed run.
    bundle = run.with_suffix(".meanap")
    bundle.write_bytes(b"not really a zip, but it exists")
    window._refresh_results_target()
    text = panel.target_label.text()
    check("a bundle beside it wins, and the label says it opens the viewer",
          panel.view_report_btn.isEnabled()
          and bundle.name in text and "viewer" in text.lower(), text)

    # The label is recomputed on the way in, because the paths it depends on
    # are edited on another tab.
    bundle.unlink()
    window._last_output_root = None
    window._last_bundle = None
    window._data_panel.output_data_folder_name.setText(run.name)
    window._tabs.setCurrentIndex(
        [window._tabs.tabText(i).strip()
         for i in range(window._tabs.count())].index("Results"))
    app.processEvents()
    check("switching to the tab re-reads the output paths",
          run.name in panel.target_label.text(), panel.target_label.text())


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All Results-tab checks passed.")
