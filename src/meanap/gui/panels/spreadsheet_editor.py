"""Build and edit the batch spreadsheet without leaving the GUI.

The spreadsheet is the one input a run cannot recover from being wrong: a name
that doesn't match its data folder is not an error, it is a recording silently
missing from the results. Retyping folder names into Excel is exactly how that
happens, so the CAT-NAP scanner can hand its findings straight to this editor —
the names then come from the data rather than from memory.

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
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from meanap.pipeline.spreadsheet import (
    GROUND_COLUMN, SPREADSHEET_COLUMNS, fill_from_table, new_recording_table,
    read_recording_table, validate_recording_table, write_recording_table,
)

_FILE_FILTER = "Spreadsheets (*.csv *.xlsx *.xls)"


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
    ) -> None:
        """Open on *table*, or on the file at *path*, or on an empty sheet.

        *suggested_path* is where **Save** will offer to write a sheet that has
        no file yet — the scanned data folder, usually, since that is where the
        recordings it names live.
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

    # ── Construction ──────────────────────────────────────────────────────────

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

    # ── Saving ────────────────────────────────────────────────────────────────

    def save_to(self, path: str | Path) -> Path:
        """Write to *path* and remember it. Also the seam tests save through."""
        written = write_recording_table(path, self.table())
        self._path = str(written)
        self._refresh()
        self.saved.emit(str(written))
        return written

    @property
    def path(self) -> str:
        """Where this sheet was last saved to or opened from; "" if nowhere."""
        return self._path

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        if not self._updating:
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
            self._set_status(f"{base}  {edits}" if edits else base)

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
) -> str:
    """Open the editor modally; return the path saved to, or ``""``.

    The return value is what callers want: a spreadsheet field to point at the
    file that was just written, without either panel knowing how the editor
    works.
    """
    dialog = SpreadsheetEditor(parent, table=table, path=path,
                               suggested_path=suggested_path)
    result: list[str] = []
    dialog.saved.connect(result.append)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.exec()
    return result[-1] if result else ""
