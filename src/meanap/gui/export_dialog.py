"""Choose which figures to export, before any are drawn.

A run's figures number in the hundreds — every network figure for every
recording at every lag — and an export usually wants a few kinds of them, or
a few recordings, for a paper or a colleague. So the export button opens this
page first: figure kinds by section on one side, recordings on the other,
each with Select all / Deselect all, the format, and where they go.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QRadioButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

__all__ = ["ExportDialog", "FORMATS"]

#: ``(format, label)`` the export can write.
FORMATS = (("png", "PNG images (300 dpi)"),
           ("svg", "SVG (editable vector)"),
           ("pdf", "PDF (editable vector)"))

_CHECKED, _UNCHECKED = Qt.CheckState.Checked, Qt.CheckState.Unchecked


def _all_none(title: str, on_all, on_none) -> QWidget:
    """A heading with Select all / Deselect all beside it."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    heading = QLabel(f"<b>{title}</b>")
    layout.addWidget(heading)
    layout.addStretch(1)
    for text, slot in (("Select all", on_all), ("Deselect all", on_none)):
        button = QPushButton(text)
        button.setObjectName("ghost")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        layout.addWidget(button)
    return row


class ExportDialog(QDialog):
    """The figures, recordings, format and folder of an export.

    *jobs* are :class:`meanap.pipeline.export.ExportJob` (listed, not drawn),
    from which the page counts what each choice would draw.
    """

    def __init__(self, jobs, recordings: list[str], dest: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export figures")
        self.resize(820, 600)
        self._jobs = list(jobs)
        self.dest = Path(dest)

        layout = QVBoxLayout(self)
        intro = QLabel("Choose the figures to draw into a results folder, with a "
                       "report.html to browse them. Figures that compare "
                       "recordings are drawn whichever recordings you choose.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        lists = QHBoxLayout()
        figures_column = QVBoxLayout()
        figures_column.addWidget(_all_none("Figures", lambda: self._set_figures(True),
                                           lambda: self._set_figures(False)))
        self.figures = QTreeWidget()
        self.figures.setHeaderHidden(True)
        self._sections: dict[str, QTreeWidgetItem] = {}
        for kind in dict.fromkeys(job.kind for job in self._jobs):
            section, figure = kind
            parent_item = self._sections.get(section)
            if parent_item is None:
                parent_item = QTreeWidgetItem(self.figures, [section])
                parent_item.setFlags(parent_item.flags() | Qt.ItemFlag.ItemIsAutoTristate
                                     | Qt.ItemFlag.ItemIsUserCheckable)
                parent_item.setExpanded(True)
                self._sections[section] = parent_item
            item = QTreeWidgetItem(parent_item, [figure])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(0, Qt.ItemDataRole.UserRole, kind)
            item.setCheckState(0, _CHECKED)
        figures_column.addWidget(self.figures)
        lists.addLayout(figures_column, 3)

        recordings_column = QVBoxLayout()
        recordings_column.addWidget(_all_none("Recordings", lambda: self._set_recordings(True),
                                              lambda: self._set_recordings(False)))
        self.recordings = QListWidget()
        for name in recordings:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(_CHECKED)
            self.recordings.addItem(item)
        recordings_column.addWidget(self.recordings)
        lists.addLayout(recordings_column, 2)
        layout.addLayout(lists, 1)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("<b>Format</b>"))
        self._formats = QButtonGroup(self)
        for i, (fmt, text) in enumerate(FORMATS):
            button = QRadioButton(text)
            button.setProperty("fmt", fmt)
            button.setChecked(i == 0)
            self._formats.addButton(button)
            format_row.addWidget(button)
        format_row.addStretch(1)
        layout.addLayout(format_row)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("<b>Into</b>"))
        self.dest_label = QLabel(str(self.dest))
        self.dest_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dest_row.addWidget(self.dest_label, 1)
        change = QPushButton("Change…")
        change.clicked.connect(self._choose_dest)
        dest_row.addWidget(change)
        layout.addLayout(dest_row)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.export_button = self.buttons.addButton(
            "Export", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.figures.itemChanged.connect(lambda *_: self._update())
        self.recordings.itemChanged.connect(lambda *_: self._update())
        self._update()

    # ── choosing ─────────────────────────────────────────────────────────────

    def _set_figures(self, on: bool) -> None:
        for section in self._sections.values():
            section.setCheckState(0, _CHECKED if on else _UNCHECKED)

    def _set_recordings(self, on: bool) -> None:
        for i in range(self.recordings.count()):
            self.recordings.item(i).setCheckState(_CHECKED if on else _UNCHECKED)

    def _choose_dest(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Export into", str(self.dest.parent))
        if folder:
            # Into a new folder of the export's own name inside the one chosen,
            # so an export never spills its folders over someone else's.
            self.dest = Path(folder) / self.dest.name
            self.dest_label.setText(str(self.dest))

    # ── what was chosen ──────────────────────────────────────────────────────

    def chosen_figures(self) -> set[tuple[str, str]]:
        out = set()
        for section in self._sections.values():
            for i in range(section.childCount()):
                child = section.child(i)
                if child.checkState(0) == _CHECKED:
                    out.add(child.data(0, Qt.ItemDataRole.UserRole))
        return out

    def chosen_recordings(self) -> set[str]:
        return {self.recordings.item(i).text() for i in range(self.recordings.count())
                if self.recordings.item(i).checkState() == _CHECKED}

    def fmt(self) -> str:
        return self._formats.checkedButton().property("fmt")

    def everything_chosen(self) -> bool:
        """Every figure kind and every recording ticked: an export of it all."""
        return (len(self.chosen_figures()) == len({job.kind for job in self._jobs})
                and len(self.chosen_recordings()) == self.recordings.count())

    def chosen_jobs(self) -> list:
        figures, recordings = self.chosen_figures(), self.chosen_recordings()
        return [job for job in self._jobs if job.kind in figures
                and (job.recording is None or job.recording in recordings)]

    def _count_kinds(self) -> None:
        """Beside each kind, how many it draws from the recordings ticked."""
        recordings = self.chosen_recordings()
        per_kind = Counter(job.kind for job in self._jobs
                           if job.recording is None or job.recording in recordings)
        self.figures.blockSignals(True)
        for section in self._sections.values():
            for i in range(section.childCount()):
                child = section.child(i)
                kind = child.data(0, Qt.ItemDataRole.UserRole)
                n = per_kind[kind]
                child.setText(0, kind[1] + (f"  ({n})" if n != 1 else ""))
        self.figures.blockSignals(False)

    def _update(self) -> None:
        self._count_kinds()
        jobs = self.chosen_jobs()
        recordings = {job.recording for job in jobs if job.recording is not None}
        if jobs:
            self.summary.setText(
                f"{len(jobs)} figure{'s' * (len(jobs) != 1)} to draw"
                + (f", from {len(recordings)} recording{'s' * (len(recordings) != 1)}"
                   if recordings else ""))
        else:
            self.summary.setText("Nothing chosen to export.")
        self.export_button.setEnabled(bool(jobs))
