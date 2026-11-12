"""Build and edit the batch spreadsheet without leaving the GUI.

The spreadsheet is the one input a run cannot recover from being wrong: a name
that doesn't match its data folder is not an error, it is a recording silently
missing from the results. Retyping folder names into Excel is exactly how that
happens, so the CAT-NAP scanner can hand its findings straight to this editor —
the names then come from the data rather than from memory.

A new sheet built from a folder starts with the group and DIV read out of the
recording names (:mod:`meanap.pipeline.name_parts`), as suggestions: the
cells are tinted until edited or saved, the suggested group values can be
renamed in one place (``WT`` → ``Wildtype``), and any part of the names can be
picked as the group or DIV instead.

What the editor adds beyond a table widget is the check it runs after every
keystroke: blank names, duplicates, non-numeric DIVs and empty groups are
reported *while editing*, not discovered by a run an hour later. Saving with
problems outstanding is allowed — a half-filled sheet is a legitimate thing to
come back to — but never silent.

The file work lives in :mod:`meanap.pipeline.spreadsheet`, so what this writes
is by construction what :func:`~meanap.pipeline.spreadsheet.read_recording_csv`
reads.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

from meanap.pipeline.name_parts import (
    div_from_part, name_parts, part_values, suggest_name_parts,
)

from meanap.pipeline.spreadsheet import (
    GROUND_COLUMN, SPREADSHEET_COLUMNS, fill_from_table, new_recording_table,
    read_recording_table, validate_recording_table, write_recording_table,
)

_FILE_FILTER = "Spreadsheets (*.csv *.xlsx *.xls)"
#: Columns by position, as ``read_recording_csv`` reads them.
_DIV_COLUMN, _GROUP_COLUMN = 1, 2
#: Cells filled from the names, until the person edits them or saves: amber
#: italic text, since the theme's alternating row shading hides a background.
_SUGGESTED = QBrush(QColor("#b45309"))
_SUGGESTED_TIP = "Suggested from the recording name. Edit it if it's wrong."
_RENAMES_PER_ROW = 3


def _clear_layout(layout) -> None:
    """Empty *layout* now; its widgets are detached at once and deleted later."""
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class SpreadsheetEditor(QDialog):
    """Table editor for the batch spreadsheet. Emits :attr:`saved` with a path."""

    saved = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        table: pd.DataFrame | None = None,
        path: str = "",
        suggested_path: str = "",
        suggest: bool = False,
    ) -> None:
        """Open on *table*, or on the file at *path*, or on an empty sheet.

        *suggested_path* is where **Save** will offer to write a sheet that has
        no file yet — the scanned data folder, usually, since that is where the
        recordings it names live.

        *suggest*: fill the blank group and DIV cells from the recording names,
        marked as suggestions. For a sheet just built from a folder.
        """
        super().__init__(parent)
        self.setWindowTitle("Recording spreadsheet")
        self.setMinimumSize(720, 460)

        self._path = str(path or "")
        self._suggested_path = str(suggested_path or "")
        self._updating = False
        #: Recording names as this sheet was opened, or None for a new one.
        #: Editing an existing list is how a batch is added to or trimmed, and
        #: the run has a cheaper way of handling that than starting again — but
        #: only if the person editing knows it exists.
        self._opened_with: set[str] | None = None
        #: The name part each group cell was filled from, by row; renaming a
        #: suggested value rewrites every cell that came from it.
        self._group_origin: list[str] | None = None
        self._group_part: int | None = None
        self._div_part: int | None = None

        layout = QVBoxLayout(self)

        self._file_label = QLabel()
        self._file_label.setWordWrap(True)
        self._file_label.setStyleSheet("font-size: 11px; color: gray;")

        self._table = QTableWidget(0, 0)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.itemChanged.connect(self._on_item_changed)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 11px;")

        layout.addWidget(self._file_label)
        layout.addWidget(self._build_name_parts())
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(self._status)
        layout.addLayout(self._build_buttons())

        if table is None and self._path and Path(self._path).exists():
            try:
                table = read_recording_table(self._path)
            except Exception as e:  # a file too broken to parse is still fixable
                QMessageBox.warning(self, "Could not read spreadsheet",
                                    f"{Path(self._path).name}: {e}\n\n"
                                    "Starting from an empty sheet instead.")
                table = None
        self.set_table(table if table is not None else new_recording_table([]))
        if self._path:
            self._opened_with = self._recording_names()
        if suggest:
            self.apply_suggestions()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_name_parts(self) -> QFrame:
        """The strip that reads group and DIV out of the names.

        One chip per part of the first recording's name; a chip's menu fills
        the group or DIV column from that part of every name. Below it, once a
        group has been read from the names, one field per distinct value to
        rename it with.
        """
        self.name_parts_box = QFrame()
        self.name_parts_box.setObjectName("namePartsBox")
        self.name_parts_box.setStyleSheet(
            "#namePartsBox { background: #f6f8fb; border: 1px solid #e3e7ee;"
            " border-radius: 8px; }"
            " QToolButton { border: 1px solid #cfd6e1; border-radius: 6px;"
            " padding: 3px 8px; background: white; }"
            " QToolButton[role=\"group\"] { background: #dce8fd; border-color: #4f8ef7; }"
            " QToolButton[role=\"div\"] { background: #dcf3e3; border-color: #16a34a; }")
        box = QVBoxLayout(self.name_parts_box)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(6)

        heading = QLabel("<b>From the names</b> — click a part to fill a column from it "
                         "in every recording's name:")
        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(4)
        self.name_parts_note = QLabel()
        self.name_parts_note.setWordWrap(True)
        self.name_parts_note.setStyleSheet("font-size: 11px; color: #555;")
        self._rename_box = QWidget()
        self._rename_grid = QGridLayout(self._rename_box)
        self._rename_grid.setContentsMargins(0, 0, 0, 0)
        self._rename_grid.setHorizontalSpacing(8)
        self._rename_box.setVisible(False)

        box.addWidget(heading)
        box.addLayout(self._chips_row)
        box.addWidget(self.name_parts_note)
        box.addWidget(self._rename_box)
        self._chips: list[QToolButton] = []
        return self.name_parts_box

    def _refresh_name_parts(self) -> None:
        """Rebuild the chips from the first recording name."""
        names = [n for n in self.table().iloc[:, 0] if str(n).strip()] \
            if self._table.rowCount() else []
        _clear_layout(self._chips_row)
        self._chips = []
        self.name_parts_box.setVisible(bool(names))
        if not names:
            return
        for index, part in enumerate(name_parts(names[0])):
            chip = QToolButton()
            chip.setText(part)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(f"Part {index + 1} of each name. Click to use it.")
            chip.setProperty("role", "group" if index == self._group_part
                             else "div" if index == self._div_part else "")
            chip.clicked.connect(lambda _=False, i=index, c=chip: self._chip_menu(i, c))
            self._chips_row.addWidget(chip)
            self._chips.append(chip)
        self._chips_row.addStretch(1)

    def _chip_menu(self, index: int, chip: QToolButton) -> None:
        menu = QMenu(self)
        group = SPREADSHEET_COLUMNS[_GROUP_COLUMN]
        div = SPREADSHEET_COLUMNS[_DIV_COLUMN]
        as_group = menu.addAction(f"Fill {group} from this part")
        as_group.triggered.connect(lambda: self.fill_group_from_part(index))
        as_div = menu.addAction(f"Fill {div} from this part")
        as_div.triggered.connect(lambda: self.fill_div_from_part(index))
        menu.exec(chip.mapToGlobal(chip.rect().bottomLeft()))

    def apply_suggestions(self) -> None:
        """Fill blank group and DIV cells from the names, where they say."""
        names = self._names_by_row()
        suggestion = suggest_name_parts(names)
        notes = []
        if suggestion.group_part is not None and self._column_blank(_GROUP_COLUMN):
            self.fill_group_from_part(suggestion.group_part, announce=False)
            notes.append(suggestion.group_reason + " Check it, and rename the values "
                         "below if your groups go by other names.")
        if suggestion.div_part is not None and self._column_blank(_DIV_COLUMN):
            self.fill_div_from_part(suggestion.div_part, announce=False)
        elif self._mark_div_from_names():
            self._div_part = suggestion.div_part
            notes.append(f"{SPREADSHEET_COLUMNS[_DIV_COLUMN]} is read from the "
                         "DIV in each name.")
        if not notes and names:
            notes.append("Nothing in the names says which group a recording is "
                         "in. Fill the column in, or click a part of the names above.")
        self.name_parts_note.setText(" ".join(notes))
        self._refresh_name_parts()
        self._refresh()

    def fill_group_from_part(self, index: int, *, announce: bool = True) -> None:
        """Set every group cell to part *index* of its recording's name."""
        values = part_values(self._names_by_row(), index)
        self._fill_column(_GROUP_COLUMN, values)
        self._group_origin = values
        self._group_part = index
        self._build_renames()
        self._refresh_name_parts()
        if announce:
            distinct = sorted({v for v in values if v}, key=str.lower)
            self.name_parts_note.setText(
                f"{SPREADSHEET_COLUMNS[_GROUP_COLUMN]} filled from part {index + 1}: "
                f"{', '.join(distinct) or 'nothing'}. Rename the values below if "
                "your groups go by other names.")

    def fill_div_from_part(self, index: int, *, announce: bool = True) -> None:
        """Set every DIV cell to the number in part *index* of its name."""
        values = [div_from_part(v) for v in part_values(self._names_by_row(), index)]
        self._fill_column(_DIV_COLUMN, values)
        self._div_part = index
        self._refresh_name_parts()
        if announce:
            missing = sum(1 for v in values if not v)
            self.name_parts_note.setText(
                f"{SPREADSHEET_COLUMNS[_DIV_COLUMN]} filled from part {index + 1}."
                + (f" {missing} name(s) have no number there — fill those in."
                   if missing else ""))

    def _names_by_row(self) -> list[str]:
        if not self._table.rowCount():
            return []
        return [str(n) for n in self.table().iloc[:, 0]]

    def _column_blank(self, column: int) -> bool:
        return column < self._table.columnCount() and all(
            not (self._table.item(r, column) and self._table.item(r, column).text().strip())
            for r in range(self._table.rowCount()))

    def _mark_div_from_names(self) -> bool:
        """Tint DIVs that :func:`new_recording_table` read from the names."""
        marked = False
        # Restyling a cell emits itemChanged, which would read as an edit.
        self._updating = True
        try:
            for r in range(self._table.rowCount()):
                item = self._table.item(r, _DIV_COLUMN)
                if item is not None and item.text().strip():
                    self._mark_suggested(item)
                    marked = True
        finally:
            self._updating = False
        return marked

    def _fill_column(self, column: int, values: list[str]) -> None:
        if column >= self._table.columnCount():
            return
        self._updating = True
        try:
            for r, value in enumerate(values):
                item = QTableWidgetItem(value)
                if value:
                    self._mark_suggested(item)
                self._table.setItem(r, column, item)
        finally:
            self._updating = False
        self._refresh()

    @staticmethod
    def _mark_suggested(item: QTableWidgetItem) -> None:
        item.setForeground(_SUGGESTED)
        font = item.font()
        font.setItalic(True)
        item.setFont(font)
        item.setToolTip(_SUGGESTED_TIP)

    @staticmethod
    def _unmark(item: QTableWidgetItem) -> None:
        item.setForeground(QBrush())
        font = item.font()
        font.setItalic(False)
        item.setFont(font)
        item.setToolTip("")

    def is_suggested(self, row: int, column: int) -> bool:
        item = self._table.item(row, column)
        return item is not None and item.foreground() == _SUGGESTED

    def _clear_suggestions(self) -> None:
        self._updating = True
        try:
            for r in range(self._table.rowCount()):
                for c in range(self._table.columnCount()):
                    if self.is_suggested(r, c):
                        self._unmark(self._table.item(r, c))
        finally:
            self._updating = False

    def _build_renames(self) -> None:
        """One field per suggested group value, to give it the lab's name."""
        _clear_layout(self._rename_grid)
        self.rename_fields: dict[str, QLineEdit] = {}
        distinct = sorted({v for v in self._group_origin or [] if v}, key=str.lower)
        if not distinct:
            self._rename_box.setVisible(False)
            return
        label = QLabel(f"Call each {SPREADSHEET_COLUMNS[_GROUP_COLUMN].lower()}:")
        self._rename_grid.addWidget(label, 0, 0, 1, 2 * _RENAMES_PER_ROW)
        for i, value in enumerate(distinct):
            field = QLineEdit(value)
            field.setPlaceholderText(value)
            field.setMaximumWidth(170)
            field.textEdited.connect(lambda text, v=value: self.rename_group(v, text))
            row, col = 1 + i // _RENAMES_PER_ROW, 2 * (i % _RENAMES_PER_ROW)
            self._rename_grid.addWidget(QLabel(f"{value} →"), row, col,
                                        Qt.AlignmentFlag.AlignRight)
            self._rename_grid.addWidget(field, row, col + 1)
            self.rename_fields[value] = field
        self._rename_grid.setColumnStretch(2 * _RENAMES_PER_ROW, 1)
        self._rename_box.setVisible(True)

    def rename_group(self, original: str, name: str) -> None:
        """Rename every group cell filled from *original* to *name*."""
        if self._group_origin is None:
            return
        self._updating = True
        try:
            for r, origin in enumerate(self._group_origin):
                if origin == original and r < self._table.rowCount():
                    item = QTableWidgetItem(name.strip())
                    self._mark_suggested(item)
                    self._table.setItem(r, _GROUP_COLUMN, item)
        finally:
            self._updating = False
        self._refresh()

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.add_row_btn = QPushButton("Add row")
        self.add_row_btn.clicked.connect(self._on_add_row)

        self.remove_row_btn = QPushButton("Remove selected rows")
        self.remove_row_btn.clicked.connect(self._on_remove_rows)

        self.fill_btn = QPushButton("Fill column…")
        self.fill_btn.setToolTip(
            "Set every selected cell in one column to the same value — for the "
            "genotype of a single-group batch, typically."
        )
        self.fill_btn.clicked.connect(self._on_fill_column)

        self.import_btn = QPushButton("Fill from another sheet…")
        self.import_btn.setToolTip(
            "Copy the DIV and genotype for each recording from an existing "
            "spreadsheet, matched by name. The names here are kept as they "
            "are — a folder that gained a trailing word still matches its row."
        )
        self.import_btn.clicked.connect(self._on_fill_from_sheet)

        self.ground_check = QCheckBox("Ground column")
        self.ground_check.setToolTip(
            "Add the optional fourth column listing electrodes to ground per "
            "recording. MEA recordings only; CAT-NAP ignores it."
        )
        self.ground_check.toggled.connect(self._on_toggle_ground)

        row.addWidget(self.add_row_btn)
        row.addWidget(self.remove_row_btn)
        row.addWidget(self.fill_btn)
        row.addWidget(self.import_btn)
        row.addStretch()
        row.addWidget(self.ground_check)
        return row

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.load_btn = QPushButton("Open…")
        self.load_btn.clicked.connect(self._on_open)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._on_save)

        self.save_as_btn = QPushButton("Save as…")
        self.save_as_btn.clicked.connect(self._on_save_as)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)

        row.addWidget(self.load_btn)
        row.addStretch()
        row.addWidget(self.close_btn)
        row.addWidget(self.save_as_btn)
        row.addWidget(self.save_btn)
        return row

    # ── Table ↔ DataFrame ─────────────────────────────────────────────────────

    def set_table(self, table: pd.DataFrame) -> None:
        """Replace the contents with *table*."""
        self._updating = True
        try:
            columns = [str(c) for c in table.columns] or list(SPREADSHEET_COLUMNS)
            self._table.setColumnCount(len(columns))
            self._table.setHorizontalHeaderLabels(columns)
            self._table.setRowCount(len(table))
            for r in range(len(table)):
                for c in range(len(columns)):
                    value = table.iloc[r, c]
                    text = "" if pd.isna(value) else str(value)
                    self._table.setItem(r, c, QTableWidgetItem(text))

            header = self._table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for c in range(1, len(columns)):
                header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

            with_ground = GROUND_COLUMN.lower() in [c.lower() for c in columns]
            self.ground_check.setChecked(with_ground)
        finally:
            self._updating = False
        self._group_origin = None
        self._group_part = self._div_part = None
        if hasattr(self, "rename_fields"):
            self._build_renames()
        self._refresh_name_parts()
        self._refresh()

    def table(self) -> pd.DataFrame:
        """The current contents, as the DataFrame that would be written."""
        columns = [self._table.horizontalHeaderItem(c).text()
                   for c in range(self._table.columnCount())]
        rows = []
        for r in range(self._table.rowCount()):
            rows.append([
                (self._table.item(r, c).text().strip()
                 if self._table.item(r, c) is not None else "")
                for c in range(self._table.columnCount())
            ])
        return pd.DataFrame(rows, columns=columns, dtype=str)

    def set_recordings(self, names) -> None:
        """Fill the sheet from a list of recording names (a scan's output)."""
        self.set_table(new_recording_table(names, ground=self.ground_check.isChecked()))
        self.apply_suggestions()

    # ── Saving ────────────────────────────────────────────────────────────────

    def save_to(self, path: str | Path) -> Path:
        """Write to *path* and remember it. Also the seam tests save through."""
        written = write_recording_table(path, self.table())
        self._path = str(written)
        # Saved is confirmed: what was suggested is now what the sheet says.
        self._clear_suggestions()
        self._refresh()
        self.saved.emit(str(written))
        return written

    @property
    def path(self) -> str:
        """Where this sheet was last saved to or opened from; "" if nowhere."""
        return self._path

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        # An edited cell is the person's answer, not a suggestion any more.
        if item.foreground() == _SUGGESTED:
            self._updating = True
            try:
                self._unmark(item)
            finally:
                self._updating = False
        if item.column() == 0:
            self._refresh_name_parts()
        self._refresh()

    def _on_add_row(self) -> None:
        self._updating = True
        try:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for c in range(self._table.columnCount()):
                self._table.setItem(row, c, QTableWidgetItem(""))
        finally:
            self._updating = False
        self._table.setCurrentCell(self._table.rowCount() - 1, 0)
        self._refresh()

    def _on_remove_rows(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            self._set_status("Select a cell in the row(s) you want to remove.",
                             warn=True)
            return
        self._updating = True
        try:
            for row in rows:
                self._table.removeRow(row)
        finally:
            self._updating = False
        self._refresh()

    def _on_fill_column(self) -> None:
        selected = self._table.selectedIndexes()
        column = selected[0].column() if selected else self._table.currentColumn()
        if column < 0:
            self._set_status("Select the column to fill first.", warn=True)
            return
        header = self._table.horizontalHeaderItem(column).text()

        # Selected cells if the user made a selection, otherwise the whole
        # column — the common case being one genotype for the entire batch.
        rows = sorted({i.row() for i in selected if i.column() == column})
        if not rows:
            rows = list(range(self._table.rowCount()))
        if not rows:
            return

        value, ok = QInputDialog.getText(
            self, "Fill column", f"Set {header} for {len(rows)} row(s) to:")
        if not ok:
            return

        self._updating = True
        try:
            for row in rows:
                self._table.setItem(row, column, QTableWidgetItem(value.strip()))
        finally:
            self._updating = False
        self._refresh()

    def _on_fill_from_sheet(self) -> None:
        """Take DIV and genotype from an existing sheet, keeping these names.

        The case this is for: a lab's master spreadsheet covers hundreds of
        recordings under slightly different names from the folders on disk. It
        holds the metadata; the scan holds the names. Neither alone is right.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Fill from spreadsheet", self._suggested_path, _FILE_FILTER)
        if not path:
            return
        try:
            source = read_recording_table(path)
        except Exception as e:
            QMessageBox.warning(self, "Could not read spreadsheet", str(e))
            return

        table = self.table()
        filled, matched = fill_from_table(table, source)
        self.set_table(filled)

        missed = len(table) - matched
        if matched:
            self._set_status(
                f"Filled {matched} of {len(table)} recording(s) from "
                f"{Path(path).name}." + (f" {missed} had no matching row — fill "
                                         "those in by hand." if missed else ""),
                warn=bool(missed))
        else:
            self._set_status(
                f"No recording here matches a row in {Path(path).name}. Check it "
                "is the spreadsheet for this dataset.", warn=True)

    def _on_toggle_ground(self, on: bool) -> None:
        if self._updating:
            return
        table = self.table()
        has = GROUND_COLUMN.lower() in [str(c).lower() for c in table.columns]
        if on and not has:
            table[GROUND_COLUMN] = ""
        elif not on and has:
            table = table.drop(columns=[c for c in table.columns
                                        if str(c).lower() == GROUND_COLUMN.lower()])
        else:
            return
        self.set_table(table)

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open recording spreadsheet", self._path or self._suggested_path,
            _FILE_FILTER)
        if not path:
            return
        try:
            self.set_table(read_recording_table(path))
        except Exception as e:
            QMessageBox.warning(self, "Could not read spreadsheet", str(e))
            return
        self._path = path
        self._refresh()

    def _on_save(self) -> None:
        if not self._path:
            self._on_save_as()
            return
        self._save(self._path)

    def _on_save_as(self) -> None:
        start = self._path or self._suggested_path
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recording spreadsheet", start, _FILE_FILTER)
        if path:
            self._save(path)

    def _save(self, path: str) -> None:
        try:
            self.save_to(path)
        except Exception as e:
            QMessageBox.warning(self, "Could not save spreadsheet", str(e))
            return
        self._set_status(f"Saved to {path}")

    # ── Validation display ────────────────────────────────────────────────────

    def _recording_names(self) -> set[str]:
        return {str(n).strip() for n in self.table().iloc[:, 0]
                if str(n).strip()} if self._table.rowCount() else set()

    def _describe_edits(self) -> str:
        """What changed since this sheet was opened, and what it means for a run.

        Only for a sheet that was opened from disk: a new one has nothing to
        have changed from.
        """
        if self._opened_with is None:
            return ""
        now = self._recording_names()
        added = now - self._opened_with
        removed = self._opened_with - now
        if not added and not removed:
            return ""

        parts = []
        if added:
            parts.append(f"{len(added)} added")
        if removed:
            parts.append(f"{len(removed)} removed")
        return (f"{' and '.join(parts)}. Tick “Continue previous run” on the "
                f"Run tab and only the new recording(s) are analysed — "
                f"everything pooled across the batch is redone either way."
                + (" Removed recordings' figures stay in the output folder "
                   "unless you also tick the option below it."
                   if removed else ""))

    def _refresh(self) -> None:
        self._file_label.setText(
            f"Editing {self._path}" if self._path
            else "Unsaved spreadsheet — use “Save as…” to choose where it goes."
        )
        problems = validate_recording_table(self.table())
        # Shown alongside any problems rather than instead of them: what needs
        # fixing and what the edit means for the next run are different
        # questions, and the second is the one nobody would think to ask.
        edits = self._describe_edits()
        if problems:
            self._set_status(" ".join(problems) + (f"  —  {edits}" if edits else ""),
                             warn=True)
        else:
            n = self._table.rowCount()
            base = f"{n} recording(s), ready to use."
            if self._has_suggestions():
                base += (" The amber cells were suggested from the names: check "
                         "them before saving.")
            self._set_status(f"{base}  {edits}" if edits else base)

    def _has_suggestions(self) -> bool:
        return any(self.is_suggested(r, c) for r in range(self._table.rowCount())
                   for c in (_DIV_COLUMN, _GROUP_COLUMN)
                   if c < self._table.columnCount())

    def _set_status(self, text: str, warn: bool = False) -> None:
        self._status.setText(("⚠ " if warn else "") + text)
        self._status.setStyleSheet(
            "font-size: 11px; color: " + ("#aa6600;" if warn else "gray;"))


def edit_spreadsheet(
    parent: QWidget | None,
    path: str = "",
    *,
    table: pd.DataFrame | None = None,
    suggested_path: str = "",
    suggest: bool = False,
) -> str:
    """Open the editor modally; return the path saved to, or ``""``.

    The return value is what callers want: a spreadsheet field to point at the
    file that was just written, without either panel knowing how the editor
    works.
    """
    dialog = SpreadsheetEditor(parent, table=table, path=path,
                               suggested_path=suggested_path, suggest=suggest)
    result: list[str] = []
    dialog.saved.connect(result.append)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.exec()
    return result[-1] if result else ""
