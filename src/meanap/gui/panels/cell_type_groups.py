"""Editor for CAT-NAP cell-type subnetwork groups.

Lets the user say which immunohistochemistry markers make up which subnetwork —
"Excitatory = NeuN+ but not GAD+/PV+/SST+", "Inhibitory = any of GAD+/PV+/SST+"
— without writing the boolean expressions that
:mod:`meanap.catnap.subnetwork` actually consumes.

The editor is a grid: one row per group, one column per marker found in the
recording's cell-type spreadsheet, and each cell set to *ignore* / *include* /
*exclude*. A per-row **Match** control decides whether the included markers are
OR-ed ("any") or AND-ed ("all"); excluded markers are always AND-NOT-ed. That
covers every group shape the marker panels in practice call for, and each row
shows the expression it compiles to so nothing is hidden.

Groups are unlimited: two rows are created by default and **Add group** appends
more. Anything the grid cannot express (nested parentheses, mixed operators) is
still supported through the free-text expression mode in the parent panel — see
:meth:`CellTypeGroupEditor.set_groups`, which reports when it cannot round-trip
a stored expression.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from meanap.catnap.subnetwork import (
    GroupExpressionError, build_group_expression, parse_group_expression_terms,
)

# Cell states, in the order they appear in each marker combo box.
IGNORE, INCLUDE, EXCLUDE = "—", "include", "exclude"
_CELL_STATES = [IGNORE, INCLUDE, EXCLUDE]

_MATCH_LABELS = {"any": "any of", "all": "all of"}

# Fixed leading columns; marker columns follow, then the expression preview.
_COL_NAME, _COL_MATCH = 0, 1
_N_LEAD = 2


class CellTypeGroupEditor(QWidget):
    """Grid of groups × markers. Emits :attr:`changed` on every edit."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._markers: list[str] = []
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._hint = QLabel(
            "Load a cell-type spreadsheet to list its markers, then assign each "
            "marker to a group."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: gray; font-size: 10px;")

        self._table = QTableWidget(0, _N_LEAD + 1)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)
        self._apply_headers()

        buttons = QHBoxLayout()
        self._add_btn = QPushButton("Add group")
        self._add_btn.clicked.connect(lambda: self._append_row(f"Group {self._table.rowCount() + 1}"))
        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.clicked.connect(self._on_remove)
        buttons.addWidget(self._add_btn)
        buttons.addWidget(self._remove_btn)
        buttons.addStretch()

        layout.addWidget(self._hint)
        layout.addWidget(self._table)
        layout.addLayout(buttons)

        # Two rows to start with — the excitatory/inhibitory case — but the
        # editor is not limited to two; Add group appends as many as needed.
        self._append_row("Excitatory")
        self._append_row("Inhibitory")

    # ── Markers ───────────────────────────────────────────────────────────────

    def markers(self) -> list[str]:
        return list(self._markers)

    def set_markers(self, markers: list[str]) -> None:
        """Rebuild the marker columns, preserving selections *by marker name*.

        Loading a different recording's spreadsheet therefore keeps whatever
        assignments still apply and quietly drops the ones whose marker is gone.
        """
        previous = self._row_states()
        self._markers = list(markers)
        self._updating = True
        try:
            # Rebuild rows wholesale: the marker columns *and* the trailing
            # expression column all move, so patching cells in place would
            # leave stale widgets behind.
            self._table.setRowCount(0)
            self._apply_headers()
            for name, match, include, exclude in previous:
                self._append_row(name, emit=False)
                self._apply_row_state(self._table.rowCount() - 1, match, include, exclude)
        finally:
            self._updating = False
        self._hint.setVisible(not self._markers)
        self._refresh_expressions()
        self.changed.emit()

    # ── Group values ──────────────────────────────────────────────────────────

    def groups(self) -> dict[str, str]:
        """``{group name: expression}``, skipping unnamed or empty rows."""
        out: dict[str, str] = {}
        for name, match, include, exclude in self._row_states():
            if not name or (not include and not exclude):
                continue
            out[name] = build_group_expression(include, exclude, match)
        return out

    def set_groups(self, groups: dict[str, str]) -> bool:
        """Populate from stored expressions.

        Returns ``False`` (leaving the grid untouched) when any expression is
        richer than the include/exclude form — the caller should then switch to
        the free-text mode rather than show a grid that silently misrepresents
        what will run.
        """
        markers = self._markers or None
        parsed = []
        for name, expr in groups.items():
            try:
                terms = parse_group_expression_terms(expr, markers)
            except GroupExpressionError:
                # Names a marker this spreadsheet does not have — the grid has
                # no column to show it in, so treat it like any other shape the
                # grid cannot represent.
                return False
            if terms is None:
                return False
            parsed.append((name, *terms))

        # Expressions may name markers no spreadsheet has been loaded for yet;
        # adopt them as columns so the grid can show the stored configuration.
        if not self._markers:
            seen: list[str] = []
            for _n, _m, inc, exc in parsed:
                for marker in inc + exc:
                    if marker not in seen:
                        seen.append(marker)
            if seen:
                self.set_markers(seen)

        self._updating = True
        try:
            self._table.setRowCount(0)
            for name, match, include, exclude in parsed:
                self._append_row(name, emit=False)
                self._apply_row_state(self._table.rowCount() - 1, match, include, exclude)
            if self._table.rowCount() == 0:
                self._append_row("Excitatory", emit=False)
                self._append_row("Inhibitory", emit=False)
        finally:
            self._updating = False
        self._refresh_expressions()
        return True

    # ── Row plumbing ──────────────────────────────────────────────────────────

    def _apply_headers(self) -> None:
        headers = ["Group", "Match"] + self._markers + ["Expression"]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        header = self._table.horizontalHeader()
        # Group names are user-typed and often long; marker columns only need to
        # fit a combo box. Give the leftover width to the expression preview.
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_NAME, 150)
        for col in range(_N_LEAD, len(headers) - 1):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)

    def _append_row(self, name: str, emit: bool = True) -> None:
        row = self._table.rowCount()
        was_updating = self._updating
        self._updating = True
        try:
            self._table.insertRow(row)
            self._table.setItem(row, _COL_NAME, QTableWidgetItem(name))

            match_combo = QComboBox()
            match_combo.addItems([_MATCH_LABELS["any"], _MATCH_LABELS["all"]])
            match_combo.setToolTip(
                "How the markers set to 'include' combine:\n"
                "  any of — a cell needs at least one of them\n"
                "  all of — a cell needs every one of them\n"
                "Markers set to 'exclude' must always be absent."
            )
            match_combo.currentIndexChanged.connect(self._on_cell_changed)
            self._table.setCellWidget(row, _COL_MATCH, match_combo)

            self._build_marker_cells(row)

            expr_item = QTableWidgetItem("")
            expr_item.setFlags(expr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, self._expr_col(), expr_item)
        finally:
            self._updating = was_updating
        self._refresh_expressions()
        if emit and not self._updating:
            self.changed.emit()

    def _build_marker_cells(self, row: int) -> None:
        for col, marker in enumerate(self._markers, start=_N_LEAD):
            combo = QComboBox()
            combo.addItems(_CELL_STATES)
            combo.setToolTip(
                f"Whether a cell must be {marker} to belong to this group:\n"
                f"  —        {marker} is irrelevant\n"
                f"  include  the cell must be {marker}\n"
                f"  exclude  the cell must NOT be {marker}"
            )
            combo.currentIndexChanged.connect(self._on_cell_changed)
            self._table.setCellWidget(row, col, combo)

    def _expr_col(self) -> int:
        return self._table.columnCount() - 1

    def _name_of(self, row: int) -> str:
        item = self._table.item(row, _COL_NAME)
        return item.text().strip() if item else ""

    def _row_states(self) -> list[tuple[str, str, list[str], list[str]]]:
        states = []
        for row in range(self._table.rowCount()):
            match_combo = self._table.cellWidget(row, _COL_MATCH)
            match = "all" if match_combo and match_combo.currentIndex() == 1 else "any"
            include, exclude = [], []
            for col, marker in enumerate(self._markers, start=_N_LEAD):
                combo = self._table.cellWidget(row, col)
                if combo is None:
                    continue
                if combo.currentText() == INCLUDE:
                    include.append(marker)
                elif combo.currentText() == EXCLUDE:
                    exclude.append(marker)
            states.append((self._name_of(row), match, include, exclude))
        return states

    def _apply_row_state(self, row: int, match: str, include: list[str],
                         exclude: list[str]) -> None:
        match_combo = self._table.cellWidget(row, _COL_MATCH)
        if match_combo:
            match_combo.setCurrentIndex(1 if match == "all" else 0)
        for col, marker in enumerate(self._markers, start=_N_LEAD):
            combo = self._table.cellWidget(row, col)
            if combo is None:
                continue
            state = (INCLUDE if marker in include
                     else EXCLUDE if marker in exclude else IGNORE)
            combo.setCurrentIndex(_CELL_STATES.index(state))

    def _refresh_expressions(self) -> None:
        col = self._expr_col()
        for row, (_name, match, include, exclude) in enumerate(self._row_states()):
            item = self._table.item(row, col)
            if item is None:
                continue
            expr = build_group_expression(include, exclude, match)
            item.setText(expr or "(no markers selected — group ignored)")
            # The column is often too narrow for the whole expression, and this
            # is the one place the user can confirm what will actually run.
            item.setToolTip(expr)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_remove(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            rows = [self._table.rowCount() - 1] if self._table.rowCount() else []
        for row in rows:
            self._table.removeRow(row)
        self.changed.emit()

    def _on_cell_changed(self, _index: int) -> None:
        if self._updating:
            return
        self._refresh_expressions()
        self.changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != _COL_NAME:
            return
        self.changed.emit()
