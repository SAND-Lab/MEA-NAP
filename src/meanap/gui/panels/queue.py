"""The queue page of the Run tab: several saved analyses, run one after another.

The Run tab's other page configures *one* run. This is for the other case — a few
different analyses to get through, and nobody wanting to sit up for the
handovers. Each entry is a parameter file saved from the toolbar, so building a
queue is: configure a run, **Save params…**, change what you like, save again,
then add both here.

The list is all that is here: the Run and Stop buttons, the progress bar and the
log are the Run tab's, shared with single runs — see
:mod:`meanap.gui.panels.run`.

Deliberately a list of *files* rather than of in-memory settings. A queue that
referred to the window's current state could not be reordered, saved, or read
the next morning to see what actually ran, and would silently change under a
tab edit made while it was running.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from meanap.gui.widgets import pin_width

#: Shown against each entry as the queue proceeds.
_MARKS = {"queued": "·", "running": "▶", "done": "✓",
          "failed": "✗", "cancelled": "■", "skipped": "·"}


class QueuePanel(QWidget):
    """Build a list of saved runs, then run the lot."""

    #: Anything worth saying about the list goes to the Run tab's one log,
    #: rather than to a second one nobody would think to read.
    log_message = pyqtSignal(str)
    #: Emitted when the list changes, so the Run button's count can follow it.
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._status: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        intro = QLabel(
            "Add parameter files saved with <b>Save params…</b>. They run in "
            "order, each into its own output folder, and a run that fails does "
            "not stop the ones after it."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        layout.addWidget(self._build_list_box(), stretch=1)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_list_box(self) -> QWidget:
        box = QGroupBox("Runs")
        outer = QHBoxLayout(box)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        outer.addWidget(self.list, stretch=1)

        buttons = QVBoxLayout()
        self.add_btn = QPushButton("Add…")
        self.add_btn.clicked.connect(self._on_add)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        self.up_btn = QPushButton("Move up")
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn = QPushButton("Move down")
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.save_btn = QPushButton("Save queue…")
        self.save_btn.setToolTip(
            "Write this list to a file so the same set of runs can be loaded "
            "again — the queue itself, not the parameters, which stay in their "
            "own files."
        )
        self.save_btn.clicked.connect(self._on_save_queue)
        self.load_btn = QPushButton("Load queue…")
        self.load_btn.clicked.connect(self._on_load_queue)

        for widget in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn):
            pin_width(widget, 110)
            buttons.addWidget(widget)
        buttons.addSpacing(12)
        for widget in (self.save_btn, self.load_btn):
            pin_width(widget, 110)
            buttons.addWidget(widget)
        buttons.addStretch()
        outer.addLayout(buttons)
        return box

    # ── The list ──────────────────────────────────────────────────────────────

    def paths(self) -> list[Path]:
        return list(self._paths)

    def _refresh(self) -> None:
        self.list.clear()
        for path, status in zip(self._paths, self._status):
            item = QListWidgetItem(f"{_MARKS.get(status, '·')}  {path.stem}")
            item.setToolTip(str(path))
            if status == "failed":
                item.setForeground(Qt.GlobalColor.red)
            self.list.addItem(item)
        self.changed.emit()

    def add_paths(self, paths) -> int:
        """Add parameter files, skipping any already listed. Returns how many."""
        added = 0
        for entry in paths:
            path = Path(entry)
            if path in self._paths:
                # Running the same file twice would write to the same output
                # folder twice, which is a mistake rather than an instruction.
                self._log(f"Already queued, not added again: {path.name}")
                continue
            self._paths.append(path)
            self._status.append("queued")
            added += 1
        self._refresh()
        return added

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add saved parameter files", "",
            "MEA-NAP parameters (*.json)")
        if paths:
            self.add_paths(paths)

    def _on_remove(self) -> None:
        for row in sorted({i.row() for i in self.list.selectedIndexes()},
                          reverse=True):
            del self._paths[row]
            del self._status[row]
        self._refresh()

    def _move(self, delta: int) -> None:
        rows = sorted({i.row() for i in self.list.selectedIndexes()},
                      reverse=delta > 0)
        if not rows:
            return
        for row in rows:
            target = row + delta
            if not 0 <= target < len(self._paths):
                return
            for seq in (self._paths, self._status):
                seq[row], seq[target] = seq[target], seq[row]
        self._refresh()
        for row in rows:
            self.list.item(row + delta).setSelected(True)

    def _on_save_queue(self) -> None:
        if not self._paths:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save this queue", "", "MEA-NAP queue (*.meanapqueue *.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(
                {"runs": [str(p) for p in self._paths]}, indent=2))
        except OSError as e:
            QMessageBox.warning(self, "Could not save the queue", str(e))
            return
        self._log(f"Queue saved to {path}")

    def _on_load_queue(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load a queue", "", "MEA-NAP queue (*.meanapqueue *.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text())
            entries = [str(p) for p in data["runs"]]
        except (OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(
                self, "Could not read that queue",
                f"{Path(path).name}: {e}\n\nA queue file lists the parameter "
                f"files to run, under a 'runs' key.")
            return
        self._paths.clear()
        self._status.clear()
        added = self.add_paths(entries)
        self._log(f"Loaded {added} run(s) from {Path(path).name}")

    # ── Marks ─────────────────────────────────────────────────────────────────

    def mark(self, index: int, status: str) -> None:
        if 0 <= index < len(self._status):
            self._status[index] = status
            self._refresh()

    def start(self) -> None:
        """Clear last night's marks, so the list shows *this* run's progress."""
        self._status = ["queued"] * len(self._paths)
        self._refresh()

    def set_editable(self, editable: bool) -> None:
        """Lock the list while the queue is being worked through.

        The worker reads these paths as it goes, so a list edited mid-flight
        would mean the summary described a queue that no longer existed.
        """
        for widget in (self.add_btn, self.remove_btn, self.up_btn,
                       self.down_btn, self.load_btn):
            widget.setEnabled(editable)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        self.log_message.emit(text)
