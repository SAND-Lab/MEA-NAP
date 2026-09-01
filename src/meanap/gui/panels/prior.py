"""Which earlier runs this one may read from.

This used to sit on the Paths tab, three groups below the folders it had nothing
to do with, while the switch that turns it on — **Use prior analysis** — was on
another tab entirely. You could fill these in and have them do nothing, or tick
the box and have it fail on a folder you never set.

So it lives with its switch now, and is disabled until the switch is on. What it
holds is unchanged: one folder, plus a list for any others. Merging runs is just
naming more than one previous analysis and giving the run a spreadsheet that
lists recordings from all of them, so the field that already means "read from an
earlier run" grows rather than a second concept appearing.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget, QPushButton,
    QVBoxLayout, QWidget,
)

from meanap.gui.panels.paths import PathRow
from meanap.gui.widgets import pin_width
from meanap.params import Params

__all__ = ["PriorAnalysisPanel"]


class PriorAnalysisPanel(QWidget):
    """The previous-analysis folders, and the buttons for listing more."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        # Indented under the checkbox that enables it, so the two read as
        # one setting rather than as a group that happens to follow.
        form.setContentsMargins(24, 2, 0, 8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.prior_analysis_path = PathRow(self)
        form.addRow("Previous analysis folder", self.prior_analysis_path)

        self.extra_priors = QListWidget()
        self.extra_priors.setMaximumHeight(74)
        self.extra_priors.setToolTip(
            "Further previous analyses, searched after the one above. A run "
            "whose spreadsheet lists recordings from several of these produces "
            "one pooled analysis over all of them, recomputing none.\n\n"
            "Each may be an OutputData… folder or a .meanap bundle."
        )
        self.add_prior_btn = QPushButton("Add…")
        pin_width(self.add_prior_btn, 80)
        self.add_prior_btn.clicked.connect(self._on_add_prior)
        self.remove_prior_btn = QPushButton("Remove")
        pin_width(self.remove_prior_btn, 80)
        self.remove_prior_btn.clicked.connect(self._on_remove_prior)

        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.add_prior_btn)
        buttons.addWidget(self.remove_prior_btn)
        buttons.addStretch()

        extra_row = QHBoxLayout()
        extra_row.setContentsMargins(0, 0, 0, 0)
        extra_row.addWidget(self.extra_priors)
        extra_row.addLayout(buttons)
        form.addRow("Additional folders", extra_row)

        hint = QLabel("Naming more than one combines them: a spreadsheet listing "
                      "recordings from several runs is analysed as one batch.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 10px;")
        form.addRow("", hint)

    # ── The list ──────────────────────────────────────────────────────────────

    def _on_add_prior(self) -> None:
        start = self.prior_analysis_path.value.strip()
        # Either kind: a run folder, or the bundle an express run left instead.
        path = QFileDialog.getExistingDirectory(
            self, "Select another previous analysis folder", start)
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "…or a .meanap bundle", start, "Run bundles (*.meanap)")
        if path and not self._prior_listed(path):
            self.extra_priors.addItem(path)

    def _on_remove_prior(self) -> None:
        for item in self.extra_priors.selectedItems():
            self.extra_priors.takeItem(self.extra_priors.row(item))

    def _prior_listed(self, path: str) -> bool:
        """Whether this folder is already named, here or as the first one.

        Listing one twice is harmless — the lookup takes the first hit — but it
        reads as though it were contributing twice, which it is not.
        """
        listed = {self.prior_analysis_path.value.strip()}
        listed |= {self.extra_priors.item(i).text()
                   for i in range(self.extra_priors.count())}
        return path in listed

    def extra_prior_paths(self) -> list[str]:
        return [self.extra_priors.item(i).text()
                for i in range(self.extra_priors.count())]

    # ── Parameters ────────────────────────────────────────────────────────────

    def load(self, params: Params) -> None:
        self.prior_analysis_path.set_value(params.prior_analysis_path)
        self.extra_priors.clear()
        for extra in params.prior_analysis_paths:
            self.extra_priors.addItem(extra)

    def save(self, params: Params) -> None:
        params.prior_analysis_path = self.prior_analysis_path.value
        params.prior_analysis_paths = self.extra_prior_paths()
