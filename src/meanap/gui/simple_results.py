"""The simple view's **View results** page.

Opening MEA-NAP only to look at a run someone sent is common, so the simple
view has a second page for it beside **Analyse recordings**: drop a ``.meanap``
bundle or a results folder on it (or double-click a bundle in the file
manager), and the results viewer opens in a window of this app. Below that are
the other viewers the current pipeline has, each enabled only when the run in
hand can feed it, and the runs opened recently.

The web viewer is still a link away, for the few things only it has (the run's
settings, exporting every figure of a bundle, cell-type decisions on tracked
cells).

The page opens nothing itself. It asks the window through signals, because the
window owns the viewer windows and the web viewer's server; the window reports
back with :meth:`ResultsPage.note_opened`.
"""

from __future__ import annotations

import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from meanap.gui import file_association
from meanap.pipeline.bundle import BUNDLE_SUFFIX

__all__ = [
    "ResultsPage", "Viewer", "has_networks", "has_tracking", "is_results_source",
    "viewers_for",
]

RECENT_KEY = "viewer/recent"
MAX_RECENT = 6


@dataclass(frozen=True)
class Viewer:
    key: str
    title: str
    description: str
    #: Whether it reads the run that was opened (rather than raw recordings).
    needs_run: bool = True


_RESULTS = Viewer("results", "Results viewer",
                  "Every figure from the run: zoom and move them, point at a node "
                  "or a point to read it, and compare recordings and DIVs.")
_SPIKES = Viewer("spikes", "Spike and burst viewer",
                 "The detected spikes and bursts on one recording, from the "
                 "recordings folder set under Analyse recordings.", needs_run=False)
_FR_DIFF = Viewer("fr_diff", "Stimulation response (ΔFR)",
                  "How each electrode's firing rate changes with stimulation.")
_TRACKING = Viewer("tracking", "Cell tracking",
                   "The same cells followed across recordings, in the results viewer.")
_NETWORK = Viewer("network", "Network viewer",
                  "One recording's network, drawn with the node sizes, colours "
                  "and layout you choose, and saved as a figure.")
_STIM_PREVIEW = Viewer("stim_preview", "Stimulation preview",
                       "Stimulation detection on one raw recording, to try "
                       "detection settings before a run.", needs_run=False)


def viewers_for(mode: str) -> list[Viewer]:
    """The viewers that apply to *mode*'s pipeline, most used first."""
    if mode == "meastim":
        return [_RESULTS, _FR_DIFF, _NETWORK, _STIM_PREVIEW, _SPIKES]
    if mode == "catnap":
        return [_RESULTS, _NETWORK, _TRACKING]
    return [_RESULTS, _NETWORK, _SPIKES]


def is_results_source(path: Path) -> bool:
    """Whether *path* is something the results viewer can open."""
    return (path.is_file() and path.suffix == BUNDLE_SUFFIX) or path.is_dir()


#: Where step 4 leaves the node metrics the network viewer draws from.
_NETMET = "4_NetworkActivity/netmet_results.json"


def has_networks(source: Path) -> bool:
    """Whether a run reached step 4, so it has networks to draw."""
    if source.is_dir():
        return (source / _NETMET).is_file()
    try:
        with zipfile.ZipFile(source) as zf:
            return any(name.endswith(_NETMET) for name in zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def has_tracking(source: Path) -> bool:
    """Whether a run carries cell-tracking results, without unpacking it."""
    if source.is_dir():
        return any((root / "payload").is_dir() for root in (source / "CellTracking", source))
    try:
        with zipfile.ZipFile(source) as zf:
            return any("CellTracking/payload/" in name or name.startswith("payload/")
                       for name in zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _load_recent() -> list[str]:
    value = QSettings("SAND Lab", "MEA-NAP").value(RECENT_KEY, [])
    if isinstance(value, str):  # QSettings returns a lone string for a one-item list
        value = [value]
    return [str(v) for v in value or []]


def _save_recent(paths: list[str]) -> None:
    QSettings("SAND Lab", "MEA-NAP").setValue(RECENT_KEY, paths[:MAX_RECENT])


def _clear(layout: QVBoxLayout) -> None:
    """Empty *layout* now; its widgets are detached at once and deleted later."""
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class _DropZone(QFrame):
    """The dashed box a bundle or a results folder is dropped on."""

    dropped = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)

    @staticmethod
    def _source(event) -> str | None:
        data = event.mimeData()
        if not data.hasUrls():
            return None
        for url in data.urls():
            if url.isLocalFile() and is_results_source(Path(url.toLocalFile())):
                return url.toLocalFile()
        return None

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._source(event):
            event.acceptProposedAction()
            self.setProperty("hover", True)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setProperty("hover", False)
        self.style().polish(self)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setProperty("hover", False)
        self.style().polish(self)
        source = self._source(event)
        if source:
            event.acceptProposedAction()
            self.dropped.emit(source)


class ResultsPage(QWidget):
    """Open a finished run and choose how to look at it."""

    #: (path, query): serve *path* in the web viewer, on the page *query* names.
    open_requested = pyqtSignal(str, str)
    spike_viewer_requested = pyqtSignal()
    #: path: open the firing-rate change viewer on that run.
    fr_diff_requested = pyqtSignal(str)
    #: path: open the network viewer on that run.
    network_viewer_requested = pyqtSignal(str)
    #: (path, query): open the results viewer on that run; ``tab=tracking``
    #: lands on its cell-tracking page.
    native_viewer_requested = pyqtSignal(str, str)
    stim_preview_requested = pyqtSignal()

    def __init__(self, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stepRow")
        self._mode = mode
        self.source: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Drop zone
        self.drop_zone = _DropZone()
        self.drop_zone.dropped.connect(self.set_source)
        drop = QVBoxLayout(self.drop_zone)
        drop.setContentsMargins(24, 26, 24, 22)
        drop.setSpacing(10)
        prompt = QLabel("Drop a .meanap bundle or a results folder here")
        prompt.setObjectName("dropPrompt")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_bundle_button = QPushButton("Open bundle…")
        self.open_bundle_button.setObjectName("primary")
        self.open_bundle_button.clicked.connect(self._browse_bundle)
        self.open_folder_button = QPushButton("Open results folder…")
        self.open_folder_button.clicked.connect(self._browse_folder)
        for button in (self.open_bundle_button, self.open_folder_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch(1)
        drop.addWidget(prompt)
        drop.addLayout(buttons)
        layout.addWidget(self.drop_zone)

        # What is open
        self.source_card = QFrame()
        self.source_card.setObjectName("stepCard")
        card = QVBoxLayout(self.source_card)
        card.setContentsMargins(18, 16, 18, 16)
        card.setSpacing(4)
        self.source_title = QLabel()
        self.source_title.setObjectName("stepTitle")
        self.source_path = QLabel()
        self.source_path.setObjectName("stepHint")
        self.source_path.setWordWrap(True)
        self.serving = QLabel()
        self.serving.setObjectName("stepStatus")
        self.serving.setProperty("state", "ok")
        self.serving.setWordWrap(True)
        self.serving.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.serving.setOpenExternalLinks(True)
        # The web viewer, for what only it has.
        self.browser_button = QPushButton("Open in browser instead")
        self.browser_button.setObjectName("linkButton")
        self.browser_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browser_button.setToolTip(
            "The older web viewer. It also shows the settings the run used, exports "
            "every figure of a bundle to a folder, and records cell-type decisions "
            "on tracked cells.")
        self.browser_button.clicked.connect(
            lambda: self.source is not None and self.open_requested.emit(str(self.source), ""))
        title_row = QHBoxLayout()
        title_row.addWidget(self.source_title, 1)
        title_row.addWidget(self.browser_button, 0, Qt.AlignmentFlag.AlignTop)
        card.addLayout(title_row)
        card.addWidget(self.source_path)
        card.addSpacing(4)
        card.addWidget(self.serving)
        layout.addWidget(self.source_card)

        # Viewers
        self._viewer_label = QLabel("Viewers")
        self._viewer_label.setObjectName("sectionLabel")
        layout.addWidget(self._viewer_label)
        self._viewer_box = QVBoxLayout()
        self._viewer_box.setSpacing(8)
        layout.addLayout(self._viewer_box)
        self._viewer_rows: dict[str, tuple[QFrame, QPushButton, QLabel]] = {}

        # Recent
        self._recent_label = QLabel("Recent")
        self._recent_label.setObjectName("sectionLabel")
        layout.addWidget(self._recent_label)
        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(2)
        layout.addLayout(self._recent_box)

        # Double-click to open
        self.association = QWidget()
        self.association.setObjectName("stepRow")
        assoc = QHBoxLayout(self.association)
        assoc.setContentsMargins(0, 10, 0, 0)
        self.association_status = QLabel()
        self.association_status.setObjectName("stepHint")
        self.association_status.setWordWrap(True)
        self.association_button = QPushButton()
        self.association_button.setObjectName("linkButton")
        self.association_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.association_button.clicked.connect(self._toggle_association)
        assoc.addWidget(self.association_status, 1)
        assoc.addWidget(self.association_button)
        layout.addWidget(self.association)

        self.set_mode(mode)
        self._refresh_source()
        self.refresh_recent()
        self._refresh_association()

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        """Show the viewers *mode*'s pipeline has."""
        self._mode = mode
        _clear(self._viewer_box)
        self._viewer_rows.clear()
        for viewer in viewers_for(mode):
            row = QFrame()
            row.setObjectName("viewerRow")
            line = QHBoxLayout(row)
            line.setContentsMargins(16, 12, 12, 12)
            line.setSpacing(12)
            text = QVBoxLayout()
            text.setSpacing(2)
            title = QLabel(viewer.title)
            title.setObjectName("viewerTitle")
            description = QLabel(viewer.description)
            description.setObjectName("stepHint")
            description.setWordWrap(True)
            text.addWidget(title)
            text.addWidget(description)
            button = QPushButton("Open")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=viewer: self.open_viewer(v.key))
            line.addLayout(text, 1)
            line.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
            self._viewer_box.addWidget(row)
            self._viewer_rows[viewer.key] = (row, button, description)
        self._refresh_viewers()

    def viewer_keys(self) -> list[str]:
        return list(self._viewer_rows)

    def viewer_row(self, key: str) -> QFrame | None:
        """The row for viewer *key*, or ``None`` if this mode has no such viewer."""
        row = self._viewer_rows.get(key)
        return row[0] if row else None

    def viewer_enabled(self, key: str) -> bool:
        return self._viewer_rows[key][1].isEnabled()

    # ── The run being looked at ───────────────────────────────────────────────

    def set_source(self, path: str | Path, *, open_viewer: bool = True) -> None:
        """Take *path* as the run to look at, and open the results viewer on it."""
        source = Path(path).expanduser()
        if not is_results_source(source):
            self.serving.setProperty("state", "error")
            self.serving.style().polish(self.serving)
            self.serving.setText(f"{source} is not a .meanap bundle or a folder.")
            self.source_card.show()
            return
        self.source = source.resolve()
        self.serving.setText("")
        self._refresh_source()
        if open_viewer:
            self.open_viewer("results")

    def open_viewer(self, key: str) -> None:
        """Open one of this pipeline's viewers on the run in hand."""
        if key == "spikes":
            self.spike_viewer_requested.emit()
            return
        if key == "stim_preview":
            self.stim_preview_requested.emit()
            return
        if self.source is None:
            return
        if key == "results":
            self.native_viewer_requested.emit(str(self.source), "")
        elif key == "tracking":
            self.native_viewer_requested.emit(str(self.source), "tab=tracking")
        elif key == "fr_diff":
            self.fr_diff_requested.emit(str(self.source))
        elif key == "network":
            self.network_viewer_requested.emit(str(self.source))

    def note_opened(self, path: str, url: str | None = None) -> None:
        """The window opened *path*: in the results window, or at *url* in the
        browser. Remember it and say where."""
        self._remember(path)
        self.serving.setProperty("state", "ok")
        self.serving.style().polish(self.serving)
        if url:
            self.serving.setText(
                f'✓  Open in your browser at <a href="{url}">{url}</a>. '
                "Keep MEA-NAP open while you look at it.")
        else:
            self.serving.setText("✓  Open in the results window.")
        self.refresh_recent()

    def _refresh_source(self) -> None:
        if self.source is None:
            self.source_card.hide()
        else:
            self.source_card.show()
            self.source_title.setText(self.source.stem if self.source.is_file()
                                      else self.source.name)
            self.source_path.setText(str(self.source))
        self._refresh_viewers()

    def _refresh_viewers(self) -> None:
        for key, (row, button, description) in self._viewer_rows.items():
            viewer = next(v for v in viewers_for(self._mode) if v.key == key)
            enabled = not viewer.needs_run or self.source is not None
            tip = "" if enabled else "Open a run above first."
            if enabled and key == "tracking" and not has_tracking(self.source):
                enabled, tip = False, "This run has no cell-tracking results."
            if enabled and key == "network" and not has_networks(self.source):
                enabled, tip = False, "This run stopped before the network step."
            button.setEnabled(enabled)
            row.setProperty("available", enabled)
            # The labels are styled by the row's state too, and keep their old
            # look unless they are polished again with it.
            for widget in [row, *row.findChildren(QWidget)]:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            row.setToolTip(tip)

    def _browse_bundle(self) -> None:
        start = str(self.source.parent) if self.source else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a MEA-NAP run bundle", start, f"MEA-NAP bundles (*{BUNDLE_SUFFIX})")
        if path:
            self.set_source(path)

    def _browse_folder(self) -> None:
        start = str(self.source.parent) if self.source else ""
        path = QFileDialog.getExistingDirectory(self, "Open a results folder", start)
        if path:
            self.set_source(path)

    # ── Recent ────────────────────────────────────────────────────────────────

    def _remember(self, path: str) -> None:
        recent = [p for p in _load_recent() if p != path]
        _save_recent([path] + recent)

    def refresh_recent(self) -> None:
        _clear(self._recent_box)
        shown = 0
        for path in _load_recent():
            source = Path(path)
            if not source.exists():
                continue
            button = QPushButton(f"{source.name}   ·   {source.parent}")
            button.setObjectName("recentButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(path)
            button.clicked.connect(lambda _=False, p=path: self.set_source(p))
            self._recent_box.addWidget(button)
            shown += 1
        self._recent_label.setVisible(shown > 0)

    # ── Double-click to open ──────────────────────────────────────────────────

    def _refresh_association(self) -> None:
        # A Mac gets this from the desktop app's Info.plist, and nothing here
        # can change it, so there is nothing to offer.
        if sys.platform == "darwin":
            self.association.hide()
            return
        status = file_association.status()
        self.association_status.setText(status.message)
        self.association_button.setText("Undo" if status.registered else "Set up")
        self.association_button.setToolTip(
            "Stop opening .meanap files in MEA-NAP when they are double-clicked."
            if status.registered else
            "Make double-clicking a .meanap file open it here. Only changes "
            "settings in your own user account.")

    def _toggle_association(self) -> None:
        registered = file_association.status().registered
        try:
            result = (file_association.unregister() if registered
                      else file_association.register())
        except Exception as exc:  # report, never crash the page over a desktop setting
            self.association_status.setText(f"Couldn't change this: {exc}")
            return
        self._refresh_association()
        self.association_status.setText(result.message)
