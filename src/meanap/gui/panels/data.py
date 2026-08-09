"""The Data tab: what you are analysing, and where the results go.

Paths and Recording were two tabs holding one question between them. Recording
had four settings on it — the sampling rate, the downsample rate, the units and
the electrode layout — none of which mean anything without the folder named on
the other tab, and all of which are properties of *the data you just pointed at*.
Splitting them meant the first thing anyone did was set a folder, then go and
find the tab describing it.

So the two are one tab, read top to bottom: **Input** is what to analyse,
**Recording** is what that data is, **Output** is where the results go.

Prior analysis used to be a third group here, three boxes below folders it had
nothing to do with, and its on/off switch was on another tab. It has moved to sit
with that switch — see :mod:`meanap.gui.panels.prior`.

The Recording group is hidden in CAT-NAP mode, where none of it applies: suite2p
recordings carry their own frame rate and have no electrodes.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.panels.paths import PathRow
from meanap.params import Params, is_remote_url

__all__ = ["DataPanel", "CHANNEL_LAYOUTS", "POTENTIAL_UNITS"]

CHANNEL_LAYOUTS = ["MCS60", "Axion64", "Mea256", "Custom"]
POTENTIAL_UNITS = ["uV", "mV", "V"]


class DataPanel(QWidget):
    """Input folders, what the recordings are, and where output goes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(self._build_input())
        layout.addWidget(self._build_recording())
        layout.addWidget(self._build_output())
        layout.addStretch()

    # ── Input ─────────────────────────────────────────────────────────────────

    def _build_input(self) -> QWidget:
        box = QGroupBox("Input")
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.raw_data = PathRow(self)
        self.raw_data.setToolTip(
            "Folder holding your recordings — or paste a Dropbox folder share "
            "link to analyse them without downloading the whole dataset. "
            "Recordings are then fetched one at a time and discarded once "
            "analysed; the cache and denoising outputs go under the output "
            "folder.")

        self.spreadsheet = PathRow(
            self, is_file=True, file_filter="Spreadsheets (*.csv *.xlsx *.xls)")
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

        self.spreadsheet_range = QLineEdit("A2:A100000")
        self.custom_grp_order = QLineEdit()
        self.custom_grp_order.setToolTip(
            "Comma-separated list of group names (e.g. 'WT,KO')")
        self.spike_detected_data = PathRow(self)
        self.spike_detected_data.setToolTip(
            "Spikes detected outside MEA-NAP, to analyse instead of running "
            "step 1. Leave empty unless you have them."
        )

        # The default range covers any spreadsheet anyone will write, the group
        # order only changes how figures are ordered, and most people have no
        # externally-detected spikes — none of the three is part of setting a
        # run up.
        advanced = AdvancedSection()
        advanced.form().addRow("Spreadsheet range", self.spreadsheet_range)
        advanced.form().addRow("Custom group order", self.custom_grp_order)
        advanced.form().addRow("Spike data folder", self.spike_detected_data)
        form.addRow(advanced)
        return box

    # ── Recording ─────────────────────────────────────────────────────────────

    def _build_recording(self) -> QWidget:
        self.recording_box = QGroupBox("Recording")
        form = QFormLayout(self.recording_box)

        self.fs = QDoubleSpinBox()
        self.fs.setRange(1, 1_000_000)
        self.fs.setDecimals(0)
        self.fs.setSuffix(" Hz")
        self.fs.setValue(25000)
        self.fs.setToolTip("The rate the data above was recorded at.")

        self.channel_layout = QComboBox()
        self.channel_layout.addItems(CHANNEL_LAYOUTS)
        self.channel_layout.setEditable(True)
        self.channel_layout.setToolTip(
            "Which electrode grid the recordings came off, which is what puts "
            "each channel in the right place in the spatial plots."
        )

        self.d_samp_f = QDoubleSpinBox()
        self.d_samp_f.setRange(1, 100_000)
        self.d_samp_f.setDecimals(0)
        self.d_samp_f.setSuffix(" Hz")
        self.d_samp_f.setValue(1000)

        self.potential_difference_unit = QComboBox()
        self.potential_difference_unit.addItems(POTENTIAL_UNITS)

        # The rate and the layout differ between rigs; the other two are
        # conventions almost every MEA file already follows.
        form.addRow("Sampling frequency", self.fs)
        form.addRow("Channel layout", self.channel_layout)

        advanced = AdvancedSection()
        advanced.form().addRow("Downsample frequency", self.d_samp_f)
        advanced.form().addRow("Potential difference unit",
                               self.potential_difference_unit)
        form.addRow(advanced)
        return self.recording_box

    # ── Output ────────────────────────────────────────────────────────────────

    def _build_output(self) -> QWidget:
        box = QGroupBox("Output")
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.output_data_folder = PathRow(self)
        self.output_data_folder_name = QLineEdit()
        self.output_data_folder_name.setToolTip(
            "Leave empty for OutputData<today's date>. An existing folder of "
            "the same name is never overwritten without asking."
        )

        form.addRow("Output data folder", self.output_data_folder)
        form.addRow("Output folder name", self.output_data_folder_name)
        return box

    # ── Modes ─────────────────────────────────────────────────────────────────

    def set_mode(self, mode_key: str) -> None:
        """Hide what this pipeline has no use for.

        CAT-NAP reads suite2p output, which carries its own frame rate and has
        no electrodes, so every setting in the Recording group is meaningless
        there. Hidden rather than removed: the values stay in ``Params`` and
        come back if the mode does.
        """
        self.recording_box.setVisible(mode_key != "catnap")

    # ── The spreadsheet editor ────────────────────────────────────────────────

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

    # ── Parameters ────────────────────────────────────────────────────────────

    def load(self, params: Params) -> None:
        self.raw_data.set_value(params.raw_data)
        self.spreadsheet.set_value(params.spreadsheet_file_name)
        self.spreadsheet_range.setText(params.spreadsheet_range)
        self.custom_grp_order.setText(",".join(params.custom_grp_order))
        self.spike_detected_data.set_value(params.spike_detected_data)
        self.output_data_folder.set_value(params.output_data_folder)
        self.output_data_folder_name.setText(params.output_data_folder_name)

        self.fs.setValue(params.fs)
        self.d_samp_f.setValue(params.d_samp_f)
        idx = self.potential_difference_unit.findText(params.potential_difference_unit)
        if idx >= 0:
            self.potential_difference_unit.setCurrentIndex(idx)
        idx = self.channel_layout.findText(params.channel_layout)
        if idx >= 0:
            self.channel_layout.setCurrentIndex(idx)
        else:
            self.channel_layout.setCurrentText(params.channel_layout)

    def save(self, params: Params) -> None:
        params.raw_data = self.raw_data.value
        params.spreadsheet_file_name = self.spreadsheet.value
        params.spreadsheet_range = self.spreadsheet_range.text()
        params.custom_grp_order = [
            g.strip() for g in self.custom_grp_order.text().split(",") if g.strip()]
        params.spike_detected_data = self.spike_detected_data.value
        params.output_data_folder = self.output_data_folder.value
        params.output_data_folder_name = self.output_data_folder_name.text()

        params.fs = self.fs.value()
        params.d_samp_f = self.d_samp_f.value()
        params.potential_difference_unit = self.potential_difference_unit.currentText()
        params.channel_layout = self.channel_layout.currentText()
