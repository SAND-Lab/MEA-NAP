"""The results viewer's covariate picker, beside figure 5A4.

5A4 asks whether each age and genotype effect survives holding something
fixed. Which something is the question a reader is exploring — firing rate,
then rate and active units, then perhaps burst rate — so the figure refits as
it is changed rather than being fixed at whatever step 5 was run with.

Each ticked preset is one covariate set (one line of dots in the figure).
The columns ticked under "Your own set" are held fixed *together*, as one more
set. The panel only says what is chosen; the viewer refits and redraws.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

__all__ = ["AdjustPanel"]


class AdjustPanel(QWidget):
    """Preset covariate sets and a free set of columns; :attr:`changed` on any edit."""

    changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        intro = QLabel("Each effect is refitted holding these fixed. A dot that moves to "
                       "zero was carried by what was held fixed.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        heading = QLabel("<b>Sets</b>")
        layout.addWidget(heading)
        self._preset_box = QVBoxLayout()
        self._preset_box.setSpacing(2)
        layout.addLayout(self._preset_box)
        self.presets: dict[str, QCheckBox] = {}

        own = QLabel("<b>Your own set</b>")
        layout.addWidget(own)
        hint = QLabel("Columns ticked here are held fixed together, as one more set.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a metric…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        # Check boxes in a scroll area rather than a checkable list: the
        # viewer's list styling replaces Qt's drawn indicators with blank
        # squares, and check boxes look like the sets above them.
        holder = QWidget()
        self._column_box = QVBoxLayout(holder)
        self._column_box.setContentsMargins(0, 0, 0, 0)
        self._column_box.setSpacing(2)
        self._column_box.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        #: What is ticked, named — a search can hide ticked columns from view.
        self.own_summary = QLabel()
        self.own_summary.setObjectName("muted")
        self.own_summary.setWordWrap(True)
        layout.addWidget(self.own_summary)
        #: ``column -> its check box``, in the run's metric order.
        self.columns: dict[str, QCheckBox] = {}
        self.clear_own = QPushButton("Clear your set")
        self.clear_own.setObjectName("ghost")
        self.clear_own.clicked.connect(self._clear_own)
        layout.addWidget(self.clear_own)
        self._loading = False

    # ── filling ──────────────────────────────────────────────────────────────

    def load(self, choices: dict) -> None:
        """Fill from :func:`meanap.pipeline.render.adjustment_choices`."""
        self._loading = True
        try:
            while self._preset_box.count():
                widget = self._preset_box.takeAt(0).widget()
                if widget is not None:
                    widget.deleteLater()
            self.presets = {}
            chosen = list(choices.get("chosen", []))
            for name, label, available, why in choices.get("presets", []):
                box = QCheckBox(label)
                box.setEnabled(available)
                box.setChecked(available and name in chosen)
                box.setToolTip(why[:1].upper() + why[1:] + "." if why else "")
                box.toggled.connect(lambda _on: self._on_edit())
                self._preset_box.addWidget(box)
                self.presets[name] = box
            # A custom set the run used comes back ticked in the column list.
            own = next((c for c in chosen if c not in self.presets), "")
            own_columns = set(own.split("+")) if own else set()
            for box in self.columns.values():
                self._column_box.removeWidget(box)
                box.deleteLater()
            self.columns = {}
            for column, label in choices.get("columns", []):
                box = QCheckBox(label)
                box.setToolTip(f"Column {column}")
                box.setChecked(column in own_columns)
                box.toggled.connect(lambda _on: self._on_edit())
                self._column_box.insertWidget(self._column_box.count() - 1, box)
                self.columns[column] = box
            self._filter(self.search.text())
            self._summarise()
        finally:
            self._loading = False

    # ── what is chosen ───────────────────────────────────────────────────────

    def own_set(self) -> list[str]:
        return [column for column, box in self.columns.items() if box.isChecked()]

    def sets(self) -> list[str]:
        """The covariate sets, as step 5 names them (``"rate"``, ``"FRmean+aN"``)."""
        out = [name for name, box in self.presets.items() if box.isChecked()]
        own = self.own_set()
        if own:
            out.append("+".join(own))
        return out

    def query(self) -> str:
        """The ``adjust_for`` override: the sets, comma-separated."""
        return ",".join(self.sets())

    # ── editing ──────────────────────────────────────────────────────────────

    def _on_edit(self) -> None:
        self._summarise()
        if not self._loading:
            self.changed.emit()

    def _summarise(self) -> None:
        own = [box.text() for box in self.columns.values() if box.isChecked()]
        self.own_summary.setText(("Held fixed together: " + " + ".join(own)) if own
                                 else "Nothing ticked here.")

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for column, box in self.columns.items():
            box.setHidden(bool(needle) and needle not in (box.text() + " " + column).lower())

    def _clear_own(self) -> None:
        self._loading = True
        for box in self.columns.values():
            box.setChecked(False)
        self._loading = False
        self._summarise()
        self.changed.emit()
