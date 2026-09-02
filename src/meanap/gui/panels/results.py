"""The Results tab: everything you do once a run has finished.

Looking at results was spread across the window. **View report** was a fourth
button in the Run tab's row, beside Run and Stop, which is the row you look at
while something is *running*. **Open bundle…** was in the toolbar, next to New and
Save params, which is where you look for a file you are about to open — not for
a run you are about to read. The Network Viewer was a tab of its own, sitting
before Run in the strip — so the workflow ran left to right until the very end, then jumped
backwards.

They are one tab now, and it is the last one: configure on the left, run, then
look at what came out.

The panel also says *what* the buttons would open, which the buttons themselves
never did. **View report** falls back to the folder this run's settings describe
when nothing has run this session, so it could act on yesterday's results, on a
folder that does not exist yet, or on an express bundle instead of a report —
and gave no clue which until you pressed it.

**Make bundle…** is here for the same reason the other two are. A bundle used
to be something you had to ask for *before* the run, by ticking Express mode,
and a full run that turned out to be worth sending had no way to become one
short of running it again. Packing a finished folder needs nothing the folder
does not already hold, so it belongs beside the buttons that open one.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from meanap.gui.panels.network_viewer import NetworkViewerPanel

__all__ = ["ResultsPanel"]


class ResultsPanel(QWidget):
    """Open a finished run, pack it up, and explore its networks."""

    view_report_requested = pyqtSignal()
    make_bundle_requested = pyqtSignal()
    open_bundle_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        #: Whether there is a folder to pack — read back by :meth:`set_bundling`
        #: so finishing a pack restores the button to the right state rather
        #: than to "enabled".
        self._can_bundle = False

        layout.addWidget(self._build_open_box())
        layout.addWidget(self._build_viewer_box(), stretch=1)

        self.set_target(None, None)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_open_box(self) -> QWidget:
        box = QGroupBox("A finished run")
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        self.view_report_btn = QPushButton("🌐  View report")
        self.view_report_btn.setFixedHeight(40)
        self.view_report_btn.setObjectName("secondary")
        self.view_report_btn.setToolTip(
            "Open this run's results in your browser. A normal run gets an "
            "HTML report of the figures in the output folder; an express run "
            "opens its .meanap bundle in the viewer instead, which draws any "
            "figure on demand in PNG or editable SVG."
        )
        self.view_report_btn.clicked.connect(self.view_report_requested)
        row.addWidget(self.view_report_btn)

        # Between the two: it acts on *this* run, like View report, while Open
        # bundle acts on a file from anywhere. Grouping them by what they act on
        # rather than by the word "bundle" keeps the two bundle buttons from
        # reading as a pair of alternatives.
        self.make_bundle_btn = QPushButton("📦  Make bundle…")
        self.make_bundle_btn.setFixedHeight(40)
        self.make_bundle_btn.setObjectName("secondary")
        self.make_bundle_btn.setToolTip(
            "Pack this run's output folder into a single .meanap file you can "
            "email or attach to a paper — typically around 25× smaller, because "
            "every figure the viewer can redraw is left out. Nothing is "
            "recomputed and the output folder is left exactly as it is."
        )
        self.make_bundle_btn.clicked.connect(self.make_bundle_requested)
        row.addWidget(self.make_bundle_btn)

        self.bundle_btn = QPushButton("📦  Open bundle…")
        self.bundle_btn.setFixedHeight(40)
        self.bundle_btn.setObjectName("secondary")
        self.bundle_btn.setToolTip(
            "Open a .meanap run bundle — from an express run of your own, or "
            "one someone sent you — and draw any of its figures in the viewer. "
            "You can also drag the file onto this window."
        )
        self.bundle_btn.clicked.connect(self.open_bundle_requested)
        row.addWidget(self.bundle_btn)
        outer.addLayout(row)

        # What the buttons above would act on. Written out because "View report"
        # acts on a folder the user never named — the dated default — as often
        # as on one they did.
        self.target_label = QLabel()
        self.target_label.setWordWrap(True)
        self.target_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.target_label.setStyleSheet("font-size: 11px; color: gray;")
        outer.addWidget(self.target_label)
        return box

    def _build_viewer_box(self) -> QWidget:
        box = QGroupBox("Network viewer")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        self.viewer = NetworkViewerPanel()
        layout.addWidget(self.viewer)
        return box

    # ── What the buttons point at ─────────────────────────────────────────────

    def set_target(self, output_root: Path | None, bundle: Path | None) -> None:
        """Say which run **View report** would open, and in which form.

        Called whenever the answer could have changed — a run finishing, or the
        tab being shown after the output paths were edited.
        """
        # **Make bundle…** needs the folder itself, which is a different
        # question from the one below: an express run's folder is removed once
        # its bundle reads back, so there is a run to *open* and nothing left to
        # pack. The label already explains the no-folder case.
        self._can_bundle = output_root is not None and output_root.is_dir()
        self.make_bundle_btn.setEnabled(self._can_bundle)
        if bundle is not None and bundle.is_file():
            self.target_label.setText(
                f"Opens the bundle <b>{bundle.name}</b> in the viewer, which "
                f"draws any figure from it on demand.<br>{bundle.parent}")
            self.view_report_btn.setEnabled(True)
        elif output_root is not None and output_root.is_dir():
            self.target_label.setText(
                f"Opens an HTML report of the figures in "
                f"<b>{output_root.name}</b>.<br>{output_root.parent}")
            self.view_report_btn.setEnabled(True)
        elif output_root is not None:
            # Named but not there yet: better to say so than to disable a button
            # with no explanation, or to let it open a warning box.
            self.target_label.setText(
                f"Nothing to open yet — <b>{output_root.name}</b> does not "
                f"exist. It is where a run started now would write.<br>"
                f"{output_root.parent}")
            self.view_report_btn.setEnabled(False)
        else:
            self.target_label.setText(
                "Nothing to open yet. Run the pipeline, or set the output "
                "folder on the Data tab to an existing MEA-NAP run — or open a "
                ".meanap bundle from anywhere.")
            self.view_report_btn.setEnabled(False)

    def set_bundling(self, running: bool) -> None:
        """Show that packing is under way, and stop a second one starting.

        Zipping a large batch takes long enough that an unchanged button reads
        as a click that did nothing, and short enough that it does not want a
        progress bar of its own — the status log carries the detail.
        """
        self.make_bundle_btn.setEnabled(not running and self._can_bundle)
        self.make_bundle_btn.setText(
            "\U0001f4e6  Packing…" if running else "\U0001f4e6  Make bundle…")
