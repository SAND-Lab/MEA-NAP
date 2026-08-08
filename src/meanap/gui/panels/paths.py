"""File path settings panel."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from meanap.params import Params, is_remote_url


def _browse_dir(line_edit: QLineEdit, parent: QWidget) -> None:
    path = QFileDialog.getExistingDirectory(parent, "Select folder", line_edit.text())
    if path:
        line_edit.setText(path)


def _browse_file(line_edit: QLineEdit, parent: QWidget, filter: str = "") -> None:
    path, _ = QFileDialog.getOpenFileName(parent, "Select file", line_edit.text(), filter)
    if path:
        line_edit.setText(path)


class PathRow(QWidget):
    """A label + line-edit + browse button row."""

    def __init__(self, parent: QWidget, initial: str = "", is_file: bool = False, file_filter: str = "") -> None:
        super().__init__(parent)
        self._is_file = is_file
        self._file_filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QLineEdit(initial)
        btn = QPushButton("Browse…")
        btn.setFixedWidth(80)
        btn.clicked.connect(self._browse)

        layout.addWidget(self.line_edit)
        layout.addWidget(btn)

    def _browse(self) -> None:
        if self._is_file:
            _browse_file(self.line_edit, self, self._file_filter)
        else:
            _browse_dir(self.line_edit, self)

    @property
    def value(self) -> str:
        return self.line_edit.text()

    def set_value(self, v: str) -> None:
        self.line_edit.setText(v)


class PathsPanel(QWidget):
    """Panel for configuring all file/folder paths."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Input paths ──────────────────────────────────────────────────────
        input_box = QGroupBox("Input")
        form = QFormLayout(input_box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.raw_data = PathRow(self)
        self.spreadsheet = PathRow(self, is_file=True, file_filter="Spreadsheets (*.csv *.xlsx *.xls)")
        self.spreadsheet_range = QLineEdit("A2:A100000")
        self.spike_detected_data = PathRow(self)
        self.custom_grp_order = QLineEdit()
        self.custom_grp_order.setToolTip("Comma-separated list of group names (e.g. 'WT,KO')")

        self.raw_data.setToolTip(
            "Folder holding your recordings — or paste a Dropbox folder share "
            "link to analyse them without downloading the whole dataset. "
            "Recordings are then fetched one at a time and discarded once "
            "analysed; the cache and denoising outputs go under the output "
            "folder.")
        # The spreadsheet is the one input whose mistakes are silent — a name
        # that matches no folder drops a recording from the batch without
        # complaint — so it gets an editor that checks as you type.
        self.edit_spreadsheet_btn = QPushButton("Edit…")
        self.edit_spreadsheet_btn.setFixedWidth(64)
        self.edit_spreadsheet_btn.setToolTip(
            "Open the recording spreadsheet in a table editor, or start a new "
            "one. Names, DIVs and groups are checked as you edit."
        )
        self.edit_spreadsheet_btn.clicked.connect(self._on_edit_spreadsheet)
        sheet_row = QHBoxLayout()
        sheet_row.setContentsMargins(0, 0, 0, 0)
        sheet_row.addWidget(self.spreadsheet)
        sheet_row.addWidget(self.edit_spreadsheet_btn)

        form.addRow("Raw data folder", self.raw_data)
        form.addRow("Spreadsheet file", sheet_row)
        form.addRow("Spreadsheet range", self.spreadsheet_range)
        form.addRow("Custom group order", self.custom_grp_order)
        form.addRow("Spike data folder", self.spike_detected_data)

        # ── Output paths ─────────────────────────────────────────────────────
        output_box = QGroupBox("Output")
        form2 = QFormLayout(output_box)
        form2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.output_data_folder = PathRow(self)
        self.output_data_folder_name = QLineEdit()

        form2.addRow("Output data folder", self.output_data_folder)
        form2.addRow("Output folder name", self.output_data_folder_name)

        # ── Prior analysis ───────────────────────────────────────────────────
        prior_box = QGroupBox("Prior analysis")
        form3 = QFormLayout(prior_box)
        form3.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.prior_analysis_path = PathRow(self)
        form3.addRow("Previous analysis folder", self.prior_analysis_path)

        layout.addWidget(input_box)
        layout.addWidget(output_box)
        layout.addWidget(prior_box)
        layout.addStretch()

    def _on_edit_spreadsheet(self) -> None:
        """Edit the configured spreadsheet, or start one where it would go."""
        from meanap.gui.panels.spreadsheet_editor import edit_spreadsheet

        current = self.spreadsheet.value.strip()
        raw = self.raw_data.value.strip()
        # A share link is not somewhere a file can be written; offer the output
        # folder, then the working directory, instead.
        near = raw if raw and not is_remote_url(raw) else (
            self.output_data_folder.value.strip() or ".")
        suggested = current or str(Path(near) / "recordings.csv")
        path = edit_spreadsheet(self, path=current, suggested_path=suggested)
        if path:
            self.spreadsheet.set_value(path)

    def load(self, params: Params) -> None:
        self.raw_data.set_value(params.raw_data)
        self.spreadsheet.set_value(params.spreadsheet_file_name)
        self.spreadsheet_range.setText(params.spreadsheet_range)
        self.custom_grp_order.setText(",".join(params.custom_grp_order))
        self.spike_detected_data.set_value(params.spike_detected_data)
        self.output_data_folder.set_value(params.output_data_folder)
        self.output_data_folder_name.setText(params.output_data_folder_name)
        self.prior_analysis_path.set_value(params.prior_analysis_path)

    def save(self, params: Params) -> None:
        params.raw_data = self.raw_data.value
        params.spreadsheet_file_name = self.spreadsheet.value
        params.spreadsheet_range = self.spreadsheet_range.text()
        params.custom_grp_order = [g.strip() for g in self.custom_grp_order.text().split(",") if g.strip()]
        params.spike_detected_data = self.spike_detected_data.value
        params.output_data_folder = self.output_data_folder.value
        params.output_data_folder_name = self.output_data_folder_name.text()
        params.prior_analysis_path = self.prior_analysis_path.value
