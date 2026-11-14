"""The results viewer's **Parameters** page: the settings a run used.

The same numbers as the run's ``params.json``, grouped by the section of
:class:`~meanap.params.Params` each belongs to
(:func:`meanap.params_summary.summarise_params`), with the ones the run changed
from the default picked out. By default only those are listed — what makes
this run different is usually the question — and the rest are a click away.

The settings can be saved as a params file, to load into MEA-NAP and run again.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

__all__ = ["ParamsView", "format_value"]

#: The section list's first entry: every section at once.
ALL = None
#: Settings in the file this version has no field for.
UNKNOWN = "Not recognised by this version"


def format_value(value) -> str:
    """A setting as it reads in ``params.json``: lists and text as JSON, floats short."""
    if isinstance(value, float):
        return f"{value:g}"
    if value == "":
        return "(empty)"
    if isinstance(value, (list, tuple, dict)) or value is None:
        return json.dumps(value)
    return str(value)


def _made_with(stamp: dict) -> str:
    """"Made with MEA-NAP 1.25.0 (…)", or that it predates the stamp."""
    if not stamp:
        return "Made before runs recorded which version made them."
    text = f"Made with {stamp.get('pipeline_name', 'MEA-NAP')} {stamp.get('version', '?')}"
    others = {k: v for k, v in (stamp.get("versions") or {}).items()
              if v != stamp.get("version")}
    if others:
        text += " (" + ", ".join(f"{k} {v}" for k, v in others.items()) + ")"
    return text + "."


class ParamsView(QWidget):
    """Sections on the left, their settings on the right."""

    hovered = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary: dict | None = None
        self._params = None
        self._stamp: dict = {}

        self.made_with = QLabel()
        self.made_with.setObjectName("muted")
        self.count = QLabel()
        self.count.setObjectName("muted")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a setting…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._fill_table())
        self.changed_only = QCheckBox("Show only what changed")
        self.changed_only.setChecked(True)
        self.changed_only.setToolTip(
            "Only the settings this run set to something other than the default.")
        self.changed_only.toggled.connect(lambda _on: self._refill())
        self.save_button = QPushButton("Save as params file…")
        self.save_button.setObjectName("ghost")
        self.save_button.setToolTip(
            "Write these settings to a .json file that MEA-NAP's Open params loads, "
            "to run the analysis again the same way.")
        self.save_button.clicked.connect(self._save)

        self.sections = QListWidget()
        self.sections.currentItemChanged.connect(lambda *_: self._fill_table())
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Setting", "Value", "Default"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        left = QFrame()
        left.setObjectName("card")
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(12, 12, 12, 12)
        title = QLabel("SECTIONS")
        title.setObjectName("cardTitle")
        left_box.addWidget(title)
        left_box.addWidget(self.sections, 1)

        right = QFrame()
        right.setObjectName("card")
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(12, 12, 12, 12)
        right_box.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(self.made_with, 1)
        top.addWidget(self.save_button)
        controls = QHBoxLayout()
        controls.addWidget(self.search, 1)
        controls.addWidget(self.changed_only)
        controls.addWidget(self.count)
        right_box.addLayout(top)
        right_box.addLayout(controls)
        right_box.addWidget(self.table, 1)
        right_box.addWidget(self.empty)

        splitter = QSplitter()
        splitter.setHandleWidth(10)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 900])
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(splitter)

    # ── content ──────────────────────────────────────────────────────────────

    def load(self, summary: dict | None, stamp: dict | None = None, params=None) -> None:
        """Show *summary* (``ParamsSummary.as_dict()``); *params*, if given, is
        the :class:`~meanap.params.Params` that "Save as params file" writes."""
        self._summary, self._params, self._stamp = summary, params, dict(stamp or {})
        self.made_with.setText(_made_with(stamp or {}))
        self.save_button.setEnabled(params is not None)
        self._refill()

    def _groups(self) -> list[dict]:
        if not self._summary:
            return []
        groups = list(self._summary.get("groups", []))
        unknown = self._summary.get("unknown") or {}
        if unknown:
            groups.append({"name": UNKNOWN, "changed": len(unknown), "entries": [
                {"name": k, "value": v, "default": None, "changed": True, "redacted": False,
                 "unknown": True} for k, v in unknown.items()]})
        return groups

    def _refill(self) -> None:
        """The section list for the current filter, keeping the section chosen."""
        current = self.sections.currentItem()
        wanted = current.data(Qt.ItemDataRole.UserRole) if current is not None else ALL
        only = self.changed_only.isChecked()
        self.sections.blockSignals(True)
        self.sections.clear()
        total = sum(len(g["entries"]) for g in self._groups())
        changed = sum(g["changed"] for g in self._groups())
        every = QListWidgetItem(f"All sections\n{changed} changed of {total}")
        every.setData(Qt.ItemDataRole.UserRole, ALL)
        self.sections.addItem(every)
        chosen = every
        for group in self._groups():
            if only and not group["changed"]:
                continue
            n = len(group["entries"])
            item = QListWidgetItem(
                f"{group['name']}\n" + (f"{group['changed']} changed of {n}"
                                        if group["changed"] else f"{n} at their defaults"))
            item.setData(Qt.ItemDataRole.UserRole, group["name"])
            self.sections.addItem(item)
            if group["name"] == wanted:
                chosen = item
        self.sections.setCurrentItem(chosen)
        self.sections.blockSignals(False)
        self._fill_table()

    def _rows(self) -> list[tuple[str, dict]]:
        current = self.sections.currentItem()
        section = current.data(Qt.ItemDataRole.UserRole) if current is not None else ALL
        text = self.search.text().strip().lower()
        only = self.changed_only.isChecked() and not text
        rows = []
        for group in self._groups():
            if section is not ALL and group["name"] != section:
                continue
            for entry in group["entries"]:
                if only and not entry["changed"]:
                    continue
                if text and text not in entry["name"].lower() \
                        and text not in format_value(entry["value"]).lower():
                    continue
                rows.append((group["name"], entry))
        return rows

    def _fill_table(self) -> None:
        rows = self._rows()
        self.table.setRowCount(0)
        heading = None
        bold = QFont()
        bold.setBold(True)
        current = self.sections.currentItem()
        many = current is None or current.data(Qt.ItemDataRole.UserRole) is ALL
        for group, entry in rows:
            if many and group != heading:
                heading = group
                r = self.table.rowCount()
                self.table.insertRow(r)
                head = QTableWidgetItem(group)
                head.setFont(bold)
                head.setForeground(QColor("#6b7280"))
                head.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(r, 0, head)
                self.table.setSpan(r, 0, 1, 3)
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = QTableWidgetItem(entry["name"])
            value = QTableWidgetItem("(withheld: it names a remote location)"
                                     if entry.get("redacted") else format_value(entry["value"]))
            default = QTableWidgetItem(
                "" if not entry["changed"] or entry.get("unknown")
                else "default " + format_value(entry["default"]))
            if entry["changed"]:
                for item in (name, value):
                    item.setFont(bold)
                value.setForeground(QColor("#1d4ed8"))
            if entry.get("redacted"):
                value.setForeground(QColor("#9ca3af"))
            default.setForeground(QColor("#6b7280"))
            value.setToolTip(format_value(entry["value"]))
            for column, item in enumerate((name, value, default)):
                self.table.setItem(r, column, item)
        self.table.resizeRowsToContents()
        shown = sum(1 for _g, _e in rows)
        if self._summary is None:
            message = "This run did not record its settings."
        elif not shown and self.search.text().strip():
            message = "No setting matches."
        elif not shown:
            message = "This run left every setting here at its default."
        else:
            message = ""
        self.empty.setText(message)
        self.empty.setVisible(bool(message))
        self.table.setVisible(not message)
        self.count.setText(f"{shown} shown")

    # ── saving ───────────────────────────────────────────────────────────────

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the run's settings", "params.json", "MEA-NAP params (*.json)")
        if path:
            self.save(path)

    def save(self, path: str | Path) -> Path:
        """Write the settings where ``load_params`` (Open params) reads them."""
        import dataclasses

        payload = dataclasses.asdict(self._params)
        # The stamp of the version that made the run, as its params.json has
        # it; MEA-NAP reads past it when loading.
        if self._stamp:
            payload["_meanap"] = self._stamp
        path = Path(path)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return path
