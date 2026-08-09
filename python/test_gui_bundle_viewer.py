"""Test the GUI's routes into a ``.meanap`` bundle: View report, and drag-drop.

Run from the repo root::

    uv run python python/test_gui_bundle_viewer.py

Express mode leaves almost no figures on disk, so the old View report — which
built a static page from whatever PNGs it found — showed an express run as a
near-empty page, indistinguishable from a run that failed. The button now picks
its destination from what the run actually produced, and a bundle can be opened
without any run at all, from the toolbar or by dropping the file on the window.

Runs against real bundles from a small synthetic pipeline run (shared with
``test_bundle_render``) and starts the real viewer server, offscreen
(``QT_QPA_PLATFORM=offscreen``) — no display, no example dataset, no MATLAB.

Sections:

  A. View report routing — bundle to the viewer, full run to the HTML report;
  B. opening bundles — dedupe, teardown, and unreadable files;
  C. drag and drop — what the window claims and what it refuses.
"""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

from PyQt6.QtCore import QMimeData, QUrl  # noqa: E402
from PyQt6.QtGui import QAction  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from test_bundle_render import BUNDLE_SUFFIX, _run  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


class _FakeDrag:
    """Enough of a QDragEnterEvent for the window's handlers.

    A real one cannot be constructed without a live drag session, and the
    behaviour under test — which files are claimed — is pure inspection of the
    mime data plus an accept/ignore decision.
    """

    def __init__(self, paths: list[str], *, local: bool = True) -> None:
        self._mime = QMimeData()
        self._mime.setUrls([
            QUrl.fromLocalFile(p) if local else QUrl(p) for p in paths
        ])
        self.accepted = False
        self.ignored = False

    def mimeData(self) -> QMimeData:  # noqa: N802 - Qt naming
        return self._mime

    def acceptProposedAction(self) -> None:  # noqa: N802 - Qt naming
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _EmptyDrag(_FakeDrag):
    """A drag carrying no URLs at all — text, say."""

    def __init__(self) -> None:
        super().__init__([])
        self._mime = QMimeData()
        self._mime.setText("some text")


def _opened_urls(window, monkey: list[str]):
    """Point the window's browser call at a list instead of a real browser."""
    import meanap.gui.main_window as mw

    mw.webbrowser = type("_Stub", (), {"open": staticmethod(monkey.append)})()
    return mw


# ── Section A: View report routing ────────────────────────────────────────────


def _routing_checks(app: QApplication, express_root: Path, full_root: Path) -> list[Check]:
    from meanap.gui.main_window import MainWindow
    from meanap.params import Params

    checks: list[Check] = []
    opened: list[str] = []
    window = MainWindow()
    _opened_urls(window, opened)

    bundle = express_root.with_suffix(BUNDLE_SUFFIX)

    # An express run: the bundle is the only complete record of it, so that is
    # where View report must go.
    window._params = Params(express_mode=True)
    window._on_pipeline_finished(express_root)
    window._on_view_report()
    checks.append(("express run: View report opens a viewer URL",
                   len(opened) == 1 and opened[0].startswith("http://"),
                   str(opened)))
    checks.append(("…and it is the viewer, not a file:// report",
                   not opened[0].startswith("file:"), str(opened[:1])))
    checks.append(("…serving something a browser can load",
                   urllib.request.urlopen(opened[0]).status == 200
                   if opened else False, ""))
    checks.append(("…and no report.html was written into the folder",
                   not (express_root / "report.html").exists(), ""))

    # Clicking again must not start a second server for the same bundle.
    before = len(window._viewers)
    window._on_view_report()
    checks.append(("clicking twice reuses the running viewer",
                   len(window._viewers) == before and opened[1] == opened[0],
                   f"{before} → {len(window._viewers)}"))

    # A full run has the figures on disk; the static report is still right.
    window2 = MainWindow()
    opened2: list[str] = []
    _opened_urls(window2, opened2)
    window2._params = Params(express_mode=False)
    window2._on_pipeline_finished(full_root)
    window2._on_view_report()
    checks.append(("full run: View report still builds the HTML report",
                   len(opened2) == 1 and opened2[0].startswith("file:"), str(opened2)))
    checks.append(("…and that report exists on disk",
                   (full_root / "report.html").is_file(), ""))
    checks.append(("…without starting a viewer",
                   len(window2._viewers) == 0, str(len(window2._viewers))))

    # A bundle sitting beside the folder is found even in a session that never
    # ran anything — the case where someone reopens yesterday's results.
    window3 = MainWindow()
    opened3: list[str] = []
    _opened_urls(window3, opened3)
    window3._data_panel.output_data_folder.set_value(str(express_root.parent))
    window3._data_panel.output_data_folder_name.setText(express_root.name)
    window3._on_view_report()
    checks.append(("a bundle is found from the paths alone, with no run",
                   len(opened3) == 1 and opened3[0].startswith("http://"), str(opened3)))

    for w in (window, window2, window3):
        w._viewers.close_all()
    return checks


# ── Section B: opening bundles ────────────────────────────────────────────────


def _open_checks(app: QApplication, express_root: Path) -> list[Check]:
    from meanap.gui.main_window import MainWindow

    checks: list[Check] = []
    bundle = express_root.with_suffix(BUNDLE_SUFFIX)
    opened: list[str] = []
    window = MainWindow()
    _opened_urls(window, opened)

    ok = window._open_in_viewer(bundle)
    checks.append(("opening a bundle succeeds", ok, ""))
    url = window._viewers.url_for(bundle)
    checks.append(("the session is addressable by path", url == opened[-1], str(url)))
    checks.append(("the log says where the viewer is",
                   url in window._run_panel.log.toPlainText(), ""))

    checks.append(("the same bundle by a different path is one session",
                   window._viewers.open(Path(str(bundle))) == url
                   and len(window._viewers) == 1, str(len(window._viewers))))

    # Closing the window must hand the port and the extraction directory back.
    port = int(url.rsplit(":", 1)[1].rstrip("/"))
    window._viewers.close_all()
    checks.append(("close_all shuts the servers down",
                   len(window._viewers) == 0, ""))
    checks.append(("…and frees the port", not _port_answering(port), str(port)))
    checks.append(("close_all is safe to call twice",
                   window._viewers.close_all() is None, ""))

    # A file that is not a bundle must be refused with a message, not a stack
    # trace — this is the "someone sent me the wrong file" case.
    with tempfile.TemporaryDirectory() as tmp:
        junk = Path(tmp) / "notes.meanap"
        junk.write_text("this is not a zip")
        errors: list[str] = []
        _stub_critical(errors)
        refused = window._open_in_viewer(junk)
        checks.append(("a non-bundle file is refused", refused is False, ""))
        checks.append(("…with an explanation naming the file",
                       bool(errors) and "notes.meanap" in errors[0], str(errors)))
        checks.append(("…and leaves no session behind",
                       len(window._viewers) == 0, str(len(window._viewers))))
    return checks


def _stub_critical(sink: list[str]) -> None:
    """Collect QMessageBox.critical text instead of blocking on a dialog."""
    from PyQt6.QtWidgets import QMessageBox

    QMessageBox.critical = staticmethod(  # type: ignore[method-assign]
        lambda parent, title, text, *a, **k: sink.append(text)
    )


def _port_answering(port: int) -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ── Section C: drag and drop ──────────────────────────────────────────────────


def _drop_checks(app: QApplication, express_root: Path) -> list[Check]:
    from meanap.gui.main_window import MainWindow

    checks: list[Check] = []
    bundle = express_root.with_suffix(BUNDLE_SUFFIX)
    window = MainWindow()
    opened: list[str] = []
    _opened_urls(window, opened)

    checks.append(("the window accepts drops at all", window.acceptDrops(), ""))
    checks.append(("the status log does not swallow them",
                   not window._run_panel.log.acceptDrops(), ""))

    ev = _FakeDrag([str(bundle)])
    window.dragEnterEvent(ev)
    checks.append(("a dragged bundle is claimed", ev.accepted and not ev.ignored, ""))

    # Not the run's folder: an express run keeps only the bundle now, so make a
    # plain one — what is being tested is "a directory is not a bundle".
    some_dir = bundle.parent / "not-a-bundle"
    some_dir.mkdir(exist_ok=True)
    (some_dir / "params.json").write_text("{}")

    ev = _FakeDrag([str(some_dir / "params.json")])
    window.dragEnterEvent(ev)
    checks.append(("a dragged .json is not claimed", ev.ignored and not ev.accepted, ""))

    ev = _FakeDrag([str(some_dir)])
    window.dragEnterEvent(ev)
    checks.append(("a dragged folder is not claimed", ev.ignored and not ev.accepted, ""))

    ev = _FakeDrag(["http://example.com/run.meanap"], local=False)
    window.dragEnterEvent(ev)
    checks.append(("a remote URL is not claimed", ev.ignored and not ev.accepted, ""))

    ev = _EmptyDrag()
    window.dragEnterEvent(ev)
    checks.append(("dragged text is not claimed", ev.ignored and not ev.accepted, ""))

    missing = express_root.parent / "gone.meanap"
    ev = _FakeDrag([str(missing)])
    window.dragEnterEvent(ev)
    checks.append(("a .meanap that isn't there is not claimed",
                   ev.ignored and not ev.accepted, ""))

    drop = _FakeDrag([str(bundle)])
    window.dropEvent(drop)
    checks.append(("dropping it opens the viewer",
                   drop.accepted and len(opened) == 1
                   and opened[0].startswith("http://"), str(opened)))

    # Two bundles dropped together get a viewer each — the ports differ, so the
    # fallback off the preferred port has to work.
    with tempfile.TemporaryDirectory() as tmp:
        second = Path(tmp) / "Second.meanap"
        second.write_bytes(bundle.read_bytes())
        window.dropEvent(_FakeDrag([str(second)]))
        urls = set(opened)
        checks.append(("a second bundle gets its own viewer",
                       len(window._viewers) == 2 and len(urls) == 2, str(sorted(urls))))
        window._viewers.close_all()

    # The toolbar route exists and is discoverable.
    actions = {a.text(): a for a in window.findChildren(QAction)}
    bundle_action = next(
        (a for text, a in actions.items() if "Open bundle" in text), None)
    checks.append(("the toolbar offers 'Open bundle…'", bundle_action is not None,
                   str(sorted(actions))))
    checks.append(("…and says drag-and-drop works too",
                   bundle_action is not None and "drag" in bundle_action.toolTip().lower(),
                   bundle_action.toolTip() if bundle_action else ""))

    # The Results tab offers it too — as the *same* action, so the two cannot
    # drift apart in wording, tooltip or behaviour.
    checks.append(("the Results tab offers the same action, not a copy of it",
                   window._results_panel.bundle_btn.defaultAction() is bundle_action,
                   str(window._results_panel.bundle_btn.defaultAction())))
    return checks


def main() -> int:
    app = QApplication.instance() or QApplication([])
    print("=" * 70)
    print("GUI: opening a .meanap bundle")
    print("=" * 70)

    total_pass = total = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express_root = _run(tmp, "Express", express=True)
        full_root = _run(tmp, "Full", express=False)

        for title, build in [
            ("A — View report routing:", lambda a: _routing_checks(a, express_root, full_root)),
            ("B — opening bundles:", lambda a: _open_checks(a, express_root)),
            ("C — drag and drop:", lambda a: _drop_checks(a, express_root)),
        ]:
            p, n = _report(title, build(app))
            total_pass += p
            total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
