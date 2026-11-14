"""Test opening finished runs: the simple view's View results page, double-click
registration, and handing a file to the window already open.

Run from the repo root::

    uv run python python/test_gui_simple_results.py [screenshot-dir]

  E. the View results page: which viewers each pipeline offers, when each is
     enabled, what opening a run asks the window to do, and the recent list;
  F. registering ``.meanap`` with the Linux desktop, into a temporary
     ``XDG_DATA_HOME`` (the desktop-database tools are not run);
  G. a second start handing its file to the first over the local socket, and
     macOS file-open events queued until the window is ready.

Nothing here opens a browser, starts a viewer server, or touches the person's
own settings or desktop.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QEvent, QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="meanap-xdg-")

from meanap.gui import file_association, theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.main_window import MainWindow, save_simple_view_preference  # noqa: E402
from meanap.gui.simple_results import has_tracking  # noqa: E402
from meanap.gui.single_instance import (  # noqa: E402
    FileOpenFilter, InstanceServer, send_to_running,
)

FAILURES: list[str] = []
ERRORS: list[str] = []
def _excepthook(kind, value, tb) -> None:
    ERRORS.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)


sys.excepthook = _excepthook


class _FileOpen:
    """Stands in for QFileOpenEvent, which PyQt cannot construct."""

    def __init__(self, path: str) -> None:
        self._path = path

    def type(self):
        return QEvent.Type.FileOpen

    def file(self) -> str:
        return self._path


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


def make_runs(root: Path) -> dict[str, Path]:
    plain = root / "OutputData01Jan2026"
    plain.mkdir()
    tracked = root / "Tracked"
    (tracked / "CellTracking" / "payload").mkdir(parents=True)
    bundle = root / "run.meanap"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("manifest.json", "{}")
    tracked_bundle = root / "tracked.meanap"
    with zipfile.ZipFile(tracked_bundle, "w") as zf:
        zf.writestr("CellTracking/payload/chain1.json", "{}")
    other = root / "notes.txt"
    other.write_text("not a run")
    networks = make_network_run(root / "Networks")
    from meanap.pipeline.bundle import write_bundle
    networks_bundle = write_bundle(
        networks, {"mode": "ephys", "recordings": [
            {"filename": r, "group": "WT", "div": 14} for r in NETWORK_RECORDINGS]})
    return {"plain": plain, "tracked": tracked, "bundle": bundle,
            "tracked_bundle": tracked_bundle, "other": other,
            "networks": networks, "networks_bundle": networks_bundle}


NETWORK_RECORDINGS = ("rec_DIV14_A", "rec_DIV14_B")


def make_network_run(root: Path) -> Path:
    """The smallest Python run the network viewer can draw: step 4's metrics
    and step 3's adjacency matrices, for two recordings on the default layout."""
    import json

    import numpy as np

    from meanap.params import Params
    from meanap.pipeline.channel_layout import get_coords_from_layout

    channels = np.asarray(get_coords_from_layout(Params().channel_layout)[0])[:20]
    rng = np.random.default_rng(0)
    (root / "ExperimentMatFiles").mkdir(parents=True)
    (root / "4_NetworkActivity").mkdir()
    results = {}
    for rec in NETWORK_RECORDINGS:
        adj = rng.random((20, 20))
        adj = (adj + adj.T) / 2 * (rng.random((20, 20)) > 0.6)
        np.fill_diagonal(adj, 0)
        np.savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz",
                 channels=channels, adjM10mslag=adj)
        active = list(range(2, 18))
        results[rec] = {"10mslag": {
            "aN": len(active), "activeChannelIndex": active,
            "ND": [float(v) for v in (adj[np.ix_(active, active)] > 0).sum(0)],
            "NS": [float(v) for v in adj[np.ix_(active, active)].sum(0)],
            "Dens": 0.3,
        }}
    (root / "4_NetworkActivity" / "netmet_results.json").write_text(json.dumps(results))
    return root


def window_with_fake_viewer() -> tuple[MainWindow, list]:
    """A window whose viewer records what it was asked to open."""
    w = MainWindow()
    w.resize(1100, 860)
    opened: list = []

    def fake_open(source, *, query=""):
        opened.append((Path(source), query))
        return True

    w._open_in_viewer = fake_open
    w._viewers.url_for = lambda source: "http://127.0.0.1:8765/"
    return w, opened


# ── E. The View results page ─────────────────────────────────────────────────

def page_section(runs: dict[str, Path], shots: Path | None) -> None:
    print("E. View results page")
    check("tracking found in a folder", has_tracking(runs["tracked"]))
    check("tracking found in a bundle", has_tracking(runs["tracked_bundle"]))
    check("no tracking in a plain run", not has_tracking(runs["plain"])
          and not has_tracking(runs["bundle"]))

    w, opened = window_with_fake_viewer()
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    page = sv.results_page
    check("opens on Analyse recordings", sv.page() == "analyse")
    if shots:
        sv.show_page("results")
        pump(50)
        w.grab().save(str(shots / "results_empty.png"))
    sv.show_page("results")
    check("View results hides the questions", not sv.analyse_page.isVisible()
          and page.isVisible())
    check("MEA-NAP offers the results, network and spike viewers",
          page.viewer_keys() == ["results", "results_native", "network", "spikes"], str(page.viewer_keys()))
    check("before a run is open, only the spike viewer can open",
          not page.viewer_enabled("results") and not page.viewer_enabled("network")
          and page.viewer_enabled("spikes"))

    page.set_source(runs["bundle"])
    check("choosing a bundle opens it in the results viewer",
          opened[-1:] == [(runs["bundle"].resolve(), "")], str(opened))
    check("and says where, with a reminder to keep MEA-NAP open",
          "127.0.0.1:8765" in page.serving.text() and "Keep MEA-NAP open" in page.serving.text())
    check("the results viewer is now enabled", page.viewer_enabled("results"))
    check("the network viewer is not, for a run with no networks",
          not page.viewer_enabled("network"))
    if shots:
        pump(50)
        w.grab().save(str(shots / "results_bundle.png"))

    page.set_source(runs["other"])
    check("a file that is not a run is refused, and the run in hand kept",
          page.source == runs["bundle"].resolve()
          and "not a .meanap" in page.serving.text() and len(opened) == 1)

    w._apply_mode("meastim")
    check("MEA-Stim adds the ΔFR viewer and stimulation preview",
          page.viewer_keys() == ["results", "results_native", "fr_diff", "network", "stim_preview", "spikes"],
          str(page.viewer_keys()))
    check("stimulation preview needs no run", page.viewer_enabled("stim_preview"))
    w._data_panel.raw_data.line_edit.setText(str(runs["plain"]))
    page.open_viewer("stim_preview")
    stim = w._panel_windows.get("stim_preview")
    check("and opens in a window of its own, browsing from the recordings folder",
          stim is not None and stim.isVisible()
          and stim.panel.start_dir == str(runs["plain"]), str(stim and stim.panel.start_dir))
    fr_sources = []
    w._on_results_page_fr_diff = lambda path: fr_sources.append(path)
    page.fr_diff_requested.disconnect()
    page.fr_diff_requested.connect(w._on_results_page_fr_diff)
    page.open_viewer("fr_diff")
    check("the ΔFR viewer is asked for the run in hand",
          fr_sources == [str(runs["bundle"].resolve())], str(fr_sources))

    w._apply_mode("catnap")
    check("CAT-NAP offers results, networks and cell tracking",
          page.viewer_keys() == ["results", "results_native", "network", "tracking"], str(page.viewer_keys()))
    check("cell tracking disabled for a run without it", not page.viewer_enabled("tracking"))
    page.set_source(runs["tracked"])
    check("enabled for a run with it", page.viewer_enabled("tracking"))
    page.open_viewer("tracking")
    check("and opens the browser on the tracking tab",
          opened[-1] == (runs["tracked"].resolve(), "tab=tracking"), str(opened[-1]))
    if shots:
        pump(50)
        w.grab().save(str(shots / "results_catnap.png"))

    page.refresh_recent()
    recent = [b.toolTip() for b in page.findChildren(type(page.open_bundle_button),
                                                       "recentButton")]
    check("recent runs listed, newest first",
          recent[:2] == [str(runs["tracked"].resolve()), str(runs["bundle"].resolve())],
          str(recent))

    w.close()

    # A run double-clicked, or sent by a second start, while the classic view shows.
    save_simple_view_preference(False)
    w, opened = window_with_fake_viewer()
    w.show()
    w.open_results([str(runs["plain"])])
    check("a run handed to the window shows on View results",
          w.is_simple_view() and w._simple_view.page() == "results"
          and opened == [(runs["plain"].resolve(), "")], str(opened))
    check("without changing which view opens next time", not MainWindow().is_simple_view())
    w.open_results([str(runs["other"])])
    check("something that is not a run is ignored", len(opened) == 1)
    w.close()

    # After a run in the simple view.
    w, opened = window_with_fake_viewer()
    w.show()
    w._set_simple_view(True)
    w._last_output_root = runs["plain"]
    w._last_bundle = None
    w._simple_view.results_button.click()
    check("View results after a run opens that run on the page",
          w._simple_view.page() == "results"
          and opened == [(runs["plain"].resolve(), "")], str(opened))
    w.close()


# ── E2. The network viewer on a Python run ───────────────────────────────────

def network_section(runs: dict[str, Path], shots: Path | None) -> None:
    print("E2. Network viewer on a Python run")
    from meanap.gui.simple_results import has_networks

    check("networks found in a folder and a bundle",
          has_networks(runs["networks"]) and has_networks(runs["networks_bundle"]))
    check("none in a run that stopped early",
          not has_networks(runs["plain"]) and not has_networks(runs["bundle"]))

    w, _opened = window_with_fake_viewer()
    w.show()
    w._set_simple_view(True)
    page = w._simple_view.results_page
    w._simple_view.show_page("results")
    page.set_source(runs["networks"])
    check("enabled for a run with networks", page.viewer_enabled("network"))
    page.open_viewer("network")
    window = w._panel_windows.get("network")
    panel = window.panel if window is not None else None
    check("opens in a window of its own", window is not None and window.isVisible())
    recs = [panel._run_combo.itemText(i) for i in range(panel._run_combo.count())]
    check("listing the run's recordings", recs == list(NETWORK_RECORDINGS), str(recs))
    check("drawing the first, with its lags, metrics and active nodes",
          panel._info_fn.text() == NETWORK_RECORDINGS[0]
          and panel._lag_combo.count() == 1 and panel._lag_combo.isEnabled()
          and panel._node_size_metric.currentText() == "ND"
          and panel._info_nodes.text().startswith("16"),
          f"{panel._info_fn.text()} {panel._lag_combo.count()} "
          f"{panel._node_size_metric.currentText()} {panel._info_nodes.text()}")
    panel._run_combo.setCurrentIndex(1)
    check("another recording is a pick away", panel._info_fn.text() == NETWORK_RECORDINGS[1])
    if shots:
        pump(100)
        window.grab().save(str(shots / "network_viewer_run.png"))

    page.set_source(runs["networks_bundle"])
    page.open_viewer("network")
    extracted = panel._run_bundle.root if panel._run_bundle is not None else None
    check("a bundle is opened too, from its extracted copy",
          extracted is not None and extracted.is_dir()
          and panel._info_fn.text() == NETWORK_RECORDINGS[0])
    panel._load_example_network()
    check("and the extracted copy is removed once let go",
          extracted is not None and not extracted.exists() and not panel._run_row.isVisible())
    page.open_viewer("network")
    extracted = panel._run_bundle.root
    w.close()
    check("closing MEA-NAP removes it too", not extracted.exists())


# ── F. Double-click registration (Linux) ─────────────────────────────────────

def association_section() -> None:
    print("F. Registering .meanap with the desktop")
    if not sys.platform.startswith("linux"):
        print("  (skipped: Linux only)")
        return
    ran: list = []
    file_association._run_quietly = lambda *cmd: ran.append(cmd) or True
    check("not registered to start with", not file_association.status().registered)
    result = file_association.register()
    paths = file_association._linux_paths()
    check("register writes the MIME type, launcher and icons",
          result.registered and all(p.is_file() for p in paths.values()))
    desktop = paths["desktop"].read_text()
    check("the launcher runs this Python and takes the file",
          f"{sys.executable} -m meanap.gui.app %f" in desktop
          and "MimeType=application/x-meanap-bundle;" in desktop, desktop)
    check("the MIME type matches *.meanap",
          'pattern="*.meanap"' in paths["mime"].read_text())
    check("MEA-NAP is made the default for it",
          ("xdg-mime", "default", "meanap.desktop", "application/x-meanap-bundle") in ran)
    check("status reports registered", file_association.status().registered)
    paths["desktop"].write_text(desktop.replace(sys.executable, "/elsewhere/python"))
    check("a launcher for another copy is reported as not this one",
          not file_association.status().registered
          and "different copy" in file_association.status().message)
    file_association.unregister()
    check("unregister removes everything",
          not any(p.exists() for p in paths.values())
          and not file_association.status().registered)


# ── G. One window ────────────────────────────────────────────────────────────

def instance_section() -> None:
    print("G. Handing a run to the window already open")
    name = f"meanap-test-{os.getpid()}"
    check("nothing to send to when no window is open", not send_to_running(["x"], name=name))
    server = InstanceServer(name=name)
    got: list = []
    server.paths_received.connect(got.append)
    check("the first copy listens", server.listening)
    second = InstanceServer(name=name)
    check("a second copy leaves the first copy's socket alone",
          not second.listening and server.listening)
    sent = send_to_running(["some/run.meanap"], name=name)
    pump(300)
    check("a second start's file reaches the first, as an absolute path",
          sent and got == [[str(Path("some/run.meanap").resolve())]], str(got))

    opens = FileOpenFilter()
    received: list = []
    opens.path_opened.connect(received.append)
    opens.eventFilter(app, _FileOpen("/tmp/a.meanap"))
    check("a macOS file-open before the window is ready is kept",
          opens.pending == ["/tmp/a.meanap"] and not received)
    check("and handed over when it is", opens.set_ready() == ["/tmp/a.meanap"])
    opens.eventFilter(app, _FileOpen("/tmp/b.meanap"))
    check("later ones are sent straight on", received == ["/tmp/b.meanap"])
    check("other events pass through", not opens.eventFilter(app, QEvent(QEvent.Type.Show)))


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as tmp:
        runs = make_runs(Path(tmp))
        page_section(runs, shots)
        network_section(runs, shots)
    association_section()
    instance_section()
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
