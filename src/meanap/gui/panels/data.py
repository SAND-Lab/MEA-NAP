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
recordings carry their own frame rate and have no electrodes. So is the
spike-data folder, which names spikes detected outside the pipeline for a step
CAT-NAP does not have — and the input folder is renamed there, since "raw data"
describes nothing a suite2p run reads. See :meth:`DataPanel.set_mode`.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.panels.paths import PathRow
from meanap.gui.widgets import pin_width
from meanap.params import Params, is_remote_url

__all__ = ["DataPanel", "CHANNEL_LAYOUTS", "POTENTIAL_UNITS",
           "RAW_DATA_LABEL", "CATNAP_DATA_LABEL"]

CHANNEL_LAYOUTS = ["MCS60", "Axion64", "Mea256", "Custom", "FromFile"]

#: Colours of the detection notes under the Recording settings.
_NOTE_OK = "#15803d"
_NOTE_WARN = "#b45309"
_NOTE_MUTED = "#6b7280"
#: Wait this long after the folder stops changing before reading its files.
DETECT_DEBOUNCE_MS = 400
POTENTIAL_UNITS = ["uV", "mV", "V"]

#: What the input folder is called, per pipeline. The ephys modes read raw
#: traces off the recorder; CAT-NAP reads suite2p output, where "raw data" names
#: nothing the user has. See :meth:`DataPanel.set_mode`.
RAW_DATA_LABEL = "Raw data folder"
CATNAP_DATA_LABEL = "Recordings folder (suite2p)"

RAW_DATA_TOOLTIP = (
    "Folder holding your recordings — or paste a Dropbox folder share link to "
    "analyse them without downloading the whole dataset. Recordings are then "
    "fetched one at a time and discarded once analysed; the cache and denoising "
    "outputs go under the output folder."
)
CATNAP_DATA_TOOLTIP = (
    "The folder holding every recording — not one recording's folder. Each "
    "sub-folder's name becomes that recording's name, and each holds a "
    "suite2p/plane0 directory. A Dropbox folder share link works here too: it "
    "is scanned without downloading anything and the run fetches one recording "
    "at a time. This is the same setting as the CAT-NAP tab's folder box."
)


class DataPanel(QWidget):
    """Input folders, what the recordings are, and where output goes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._mode_key = "meanap"
        #: (folder, its raw files) → what they said about layout and rate.
        self._layout_guesses: dict = {}

        layout.addWidget(self._build_input())
        layout.addWidget(self._build_recording())
        layout.addWidget(self._build_output())
        layout.addStretch()

        self._detect_timer = QTimer(self)
        self._detect_timer.setSingleShot(True)
        self._detect_timer.setInterval(DETECT_DEBOUNCE_MS)
        self._detect_timer.timeout.connect(self.refresh_detection)
        self.raw_data.line_edit.textChanged.connect(lambda _t: self._detect_timer.start())
        self.channel_layout.currentTextChanged.connect(lambda _t: self._show_detection())
        self._show_detection()

    # ── Input ─────────────────────────────────────────────────────────────────

    def _build_input(self) -> QWidget:
        box = QGroupBox("Input")
        form = self._input_form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.raw_data = PathRow(self)
        self.raw_data.setToolTip(RAW_DATA_TOOLTIP)

        self.spreadsheet = PathRow(
            self, is_file=True, file_filter="Spreadsheets (*.csv *.xlsx *.xls)")
        # The spreadsheet is the one input whose mistakes are silent — a name
        # that matches no folder drops a recording from the batch without
        # complaint — so it gets an editor that checks as you type.
        self.edit_spreadsheet_btn = QPushButton("Edit…")
        pin_width(self.edit_spreadsheet_btn, 64)
        self.edit_spreadsheet_btn.setToolTip(
            "Open the recording spreadsheet in a table editor, or start a new "
            "one. Names, DIVs and groups are checked as you edit."
        )
        self.edit_spreadsheet_btn.clicked.connect(self._on_edit_spreadsheet)
        sheet_row = QHBoxLayout()
        sheet_row.setContentsMargins(0, 0, 0, 0)
        sheet_row.addWidget(self.spreadsheet)
        sheet_row.addWidget(self.edit_spreadsheet_btn)

        form.addRow(RAW_DATA_LABEL, self.raw_data)
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

        # Truncation is a property of the input — "analyse only the first N
        # seconds of each recording" — so it sits with the data it applies to.
        # It used to live under the STTC settings on the Connectivity tab,
        # which is where it is *used* rather than what it is about, and that
        # tab is not shown at all until connectivity is the thing being set up.
        self.trunc_rec = QCheckBox()
        self.trunc_rec.setToolTip(
            "Analyse only part of every recording, so recordings of different "
            "lengths are compared over the same window. Applies to MEA spike "
            "times and to calcium imaging (suite2p) traces alike.")
        self.trunc_length = QDoubleSpinBox()
        self.trunc_length.setRange(1, 100000)
        self.trunc_length.setDecimals(0)
        self.trunc_length.setSuffix(" s")
        self.trunc_length.setValue(120)
        self.trunc_keep = QComboBox()
        self.trunc_keep.addItem("First part of the recording", "first")
        self.trunc_keep.addItem("Last part of the recording", "last")
        self.trunc_keep.setToolTip(
            "Which end of each recording to keep. The last part is re-timed to "
            "start at 0 s, so rasters and rates cover the kept window only.")
        # Length and end mean nothing until truncation is on.
        self.trunc_rec.toggled.connect(self.trunc_length.setEnabled)
        self.trunc_rec.toggled.connect(self.trunc_keep.setEnabled)
        self.trunc_length.setEnabled(False)
        self.trunc_keep.setEnabled(False)

        # The default range covers any spreadsheet anyone will write, the group
        # order only changes how figures are ordered, most people have no
        # externally-detected spikes, and most recordings are analysed whole —
        # none of these is part of setting a run up.
        advanced = self._input_advanced = AdvancedSection()
        advanced.form().addRow("Spreadsheet range", self.spreadsheet_range)
        advanced.form().addRow("Custom group order", self.custom_grp_order)
        advanced.form().addRow("Spike data folder", self.spike_detected_data)
        advanced.form().addRow("Truncate recording", self.trunc_rec)
        advanced.form().addRow("Truncation length", self.trunc_length)
        advanced.form().addRow("Keep", self.trunc_keep)
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
        self.fs.setToolTip(
            "Saved with the run's settings for the record only: every step reads "
            "each recording's own sampling rate from its file, so recordings made "
            "at different rates are each analysed at the right one.")

        self.channel_layout = QComboBox()
        self.channel_layout.addItems(CHANNEL_LAYOUTS)
        self.channel_layout.setEditable(True)
        self.channel_layout.setToolTip(
            "Which electrode grid the recordings came off, which is what puts "
            "each channel in the right place in the spatial plots.\n\n"
            "FromFile: each recording's own electrode positions, as an import "
            "of sorted units writes them — for arrays with no fixed layout, "
            "such as MaxWell HD-MEAs."
        )

        self.d_samp_f = QDoubleSpinBox()
        self.d_samp_f.setRange(1, 100_000)
        self.d_samp_f.setDecimals(0)
        self.d_samp_f.setSuffix(" Hz")
        self.d_samp_f.setValue(1000)

        self.potential_difference_unit = QComboBox()
        self.potential_difference_unit.addItems(POTENTIAL_UNITS)

        # Both are read from the recordings (see refresh_detection), so each
        # says so beneath it — a bare "25000 Hz" read as a setting someone had
        # to get right, and as wrong whenever the files were at another rate.
        # The rate is not editable at all: no step reads it, each recording is
        # analysed at its own. The spin box stays, hidden, to carry the value
        # into the saved settings.
        self.fs.hide()
        self.fs_note = QLabel()
        self.fs_note.setTextFormat(Qt.TextFormat.RichText)
        self.fs_note.setWordWrap(True)
        self.fs_note.setToolTip(self.fs.toolTip())
        fs_field = QWidget()
        fs_column = QVBoxLayout(fs_field)
        fs_column.setContentsMargins(0, 0, 0, 0)
        fs_column.addWidget(self.fs_note)
        fs_column.addWidget(self.fs)

        self.layout_note = QLabel()
        self.layout_note.setWordWrap(True)
        self.layout_use_button = QPushButton()
        self.layout_use_button.setFlat(True)
        self.layout_use_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.layout_use_button.setStyleSheet(
            "QPushButton { border: none; color: #2563eb; padding: 0 4px; }")
        self.layout_use_button.clicked.connect(self._use_detected_layout)
        self.layout_use_button.hide()
        note_row = QHBoxLayout()
        note_row.setContentsMargins(0, 0, 0, 0)
        note_row.addWidget(self.layout_note, 1)
        note_row.addWidget(self.layout_use_button, 0, Qt.AlignmentFlag.AlignTop)
        layout_field = QWidget()
        layout_column = QVBoxLayout(layout_field)
        layout_column.setContentsMargins(0, 0, 0, 0)
        layout_column.setSpacing(3)
        layout_column.addWidget(self.channel_layout)
        layout_column.addLayout(note_row)

        form.addRow("Sampling frequency", fs_field)
        form.addRow("Channel layout", layout_field)

        advanced = AdvancedSection()
        advanced.form().addRow("Downsample frequency", self.d_samp_f)
        advanced.form().addRow("Potential difference unit",
                               self.potential_difference_unit)
        form.addRow(advanced)
        return self.recording_box

    # ── Reading layout and rate from the recordings ───────────────────────────

    def layout_guess(self):
        """What the raw data folder's files say about layout and rate; cached.

        Read again only when the folder or the files in it change. The first
        time a folder is read, its layout goes into the setting, so a run uses
        it without anyone pressing anything; after that a layout the person
        picks is left alone (and flagged if it disagrees). ``FromFile`` is
        never replaced: it is a deliberate choice for imported sorted units.
        """
        from meanap.pipeline.io import RAW_EXTENSIONS
        from meanap.pipeline.recording_probe import detect_layout, probe_folder

        folder = self.raw_data.value.strip()
        if (self._mode_key == "catnap" or not folder or is_remote_url(folder)
                or not Path(folder).is_dir()):
            return None
        try:
            files = tuple(sorted(p.name for p in Path(folder).iterdir()
                                 if p.suffix.lower() in RAW_EXTENSIONS))
        except OSError:
            return None
        key = (folder, files)
        if key not in self._layout_guesses:
            try:
                guess = detect_layout(probe_folder(folder))
            except Exception:  # unreadable files: say so rather than guess
                guess = None
            self._layout_guesses[key] = guess
            if guess is not None and guess.layout:
                if self.channel_layout.currentText() != "FromFile":
                    self.channel_layout.setCurrentText(guess.layout)
                if len(set(guess.rates)) == 1:
                    self.fs.setValue(guess.rates[0])
        return self._layout_guesses[key]

    def refresh_detection(self) -> None:
        """Read the folder's files if they are new, and update the notes."""
        self._detect_timer.stop()
        self.layout_guess()
        self._show_detection()

    def _use_detected_layout(self) -> None:
        guess = self.layout_guess()
        if guess is not None and guess.layout:
            self.channel_layout.setCurrentText(guess.layout)

    @staticmethod
    def _note(label: QLabel, text: str, colour: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"color: {colour}; font-size: 11px;")

    def _show_detection(self) -> None:
        """Say where the rate and layout come from, and whether they agree."""
        from meanap.gui.simple_checks import describe_rates

        folder = self.raw_data.value.strip()
        remote = bool(folder) and is_remote_url(folder)
        guess = None
        if folder and not remote:
            # Only what is already cached: reading files is refresh_detection's
            # job, after typing stops, not every keystroke's.
            guess = next((g for (f, _files), g in self._layout_guesses.items()
                          if f == folder), None)
        self.layout_use_button.hide()

        rates = describe_rates(guess.rates) if guess is not None else ""
        if rates and len(set(guess.rates)) > 1:
            self.fs_note.setText(
                f"<b>{rates}</b> <span style='color:{_NOTE_MUTED}'>— read from the "
                "recordings; each is analysed at its own rate</span>")
        elif rates:
            self.fs_note.setText(
                f"<b>{rates}</b> <span style='color:{_NOTE_MUTED}'>— read from "
                "the recordings</span>")
        else:
            self.fs_note.setText(
                f"<span style='color:{_NOTE_MUTED}'>Read from each recording "
                "when the run starts</span>")

        chosen = self.channel_layout.currentText()
        if guess is None or not guess.layout:
            if remote:
                text = ("Can't be checked against a share link before the run, "
                        "so make sure this is the array you recorded on.")
            elif folder and Path(folder).is_dir():
                text = "Couldn't be read from these files; choose the array you recorded on."
            else:
                text = "Detected from the recordings once a raw data folder is chosen."
            self._note(self.layout_note, text, _NOTE_MUTED)
        elif chosen == "FromFile":
            self._note(self.layout_note, "Electrode positions come from each "
                       "recording's own file.", _NOTE_MUTED)
        elif chosen != guess.layout:
            self._note(self.layout_note,
                       f"⚠ You chose {chosen}, but the recordings look like "
                       f"{guess.layout}. {guess.reason}", _NOTE_WARN)
            self.layout_use_button.setText(f"Use {guess.layout}")
            self.layout_use_button.show()
        elif guess.sure:
            self._note(self.layout_note, f"✓ Detected from the recordings. {guess.reason}",
                       _NOTE_OK)
        else:
            self._note(self.layout_note, f"Detected from the recordings, but check "
                       f"it: {guess.reason}", _NOTE_WARN)

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

        # Where a *remote* run does its working storage. Both default to
        # sitting under the output folder, and both survive the run — the
        # derived one deliberately, since it holds the denoising output and is
        # what lets a re-run skip that work. It is also routinely far larger
        # than the run's own result (GBs against MBs), so it needs somewhere to
        # be steered rather than only a default.
        self.cache_dir = PathRow(self)
        self.cache_dir.line_edit.setPlaceholderText(
            "<output folder>/MEANAP-cache — streamed data, cleared as it goes")
        self.derived_data_folder = PathRow(self)
        self.derived_data_folder.line_edit.setPlaceholderText(
            "<output folder>/MEANAP-derived — denoising output, kept between runs")
        self.cache_budget_gb = QDoubleSpinBox()
        self.cache_budget_gb.setRange(0.0, 10000.0)
        self.cache_budget_gb.setDecimals(1)
        self.cache_budget_gb.setSuffix(" GB")
        self.cache_budget_gb.setSpecialValueText("Automatic")
        self.cache_budget_gb.setToolTip(
            "Ceiling for the streamed-data cache. Automatic uses a quarter of "
            "free disk, capped at 50 GB.")

        form.addRow("Output data folder", self.output_data_folder)
        form.addRow("Output folder name", self.output_data_folder_name)

        remote_advanced = AdvancedSection("Remote data (streamed runs)")
        remote_advanced.form().addRow("Cache folder", self.cache_dir)
        remote_advanced.form().addRow("Cache size limit", self.cache_budget_gb)
        remote_advanced.form().addRow("Derived data folder", self.derived_data_folder)
        form.addRow(remote_advanced)
        return box

    # ── Modes ─────────────────────────────────────────────────────────────────

    def set_mode(self, mode_key: str) -> None:
        """Hide — and rename — what this pipeline has no use for.

        CAT-NAP reads suite2p output, which carries its own frame rate and has
        no electrodes, so every setting in the Recording group is meaningless
        there, as is a folder of spikes detected elsewhere: CAT-NAP has no
        spike-detection step to skip. Hidden rather than removed: the values
        stay in ``Params`` and come back if the mode does.

        "Raw data" is an ephys word — there is no raw trace in a CAT-NAP run,
        only suite2p output — so the folder is named for what it holds in each
        mode, matching the CAT-NAP tab's own wording.
        """
        catnap = mode_key == "catnap"
        self._mode_key = mode_key
        self.recording_box.setVisible(not catnap)

        label = self._input_form.labelForField(self.raw_data)
        if label is not None:
            label.setText(CATNAP_DATA_LABEL if catnap else RAW_DATA_LABEL)
        self.raw_data.setToolTip(
            CATNAP_DATA_TOOLTIP if catnap else RAW_DATA_TOOLTIP)

        self._input_advanced.form().setRowVisible(
            self.spike_detected_data, not catnap)
        # The header's count is now one out; it only recomputes on show, and a
        # mode can be switched while this tab is the one being looked at.
        self._input_advanced.refresh_label()

    # ── The spreadsheet editor ────────────────────────────────────────────────

    def _on_edit_spreadsheet(self) -> None:
        self.edit_spreadsheet()

    def edit_spreadsheet(self, names: list[str] | None = None) -> None:
        """Edit the configured spreadsheet, or start one where it would go.

        A new sheet starts with one row per recording in the raw-data folder
        (or *names*, for a caller that found them another way, as CAT-NAP's
        suite2p scan does), with group and DIV suggested from the names.
        """
        from meanap.gui.panels.spreadsheet_editor import edit_spreadsheet
        from meanap.pipeline.spreadsheet import new_recording_table, raw_recording_names

        current = self.spreadsheet.value.strip()
        raw = self.raw_data.value.strip()
        local = bool(raw) and not is_remote_url(raw)
        # A share link is not somewhere a file can be written; offer the output
        # folder, then the working directory, instead.
        near = raw if local else (self.output_data_folder.value.strip() or ".")
        suggested = current or str(Path(near) / "recordings.csv")

        table = None
        if not (current and Path(current).is_file()):
            if names is None and local:
                try:
                    names = raw_recording_names(raw)
                except ValueError:  # not a folder (yet)
                    names = None
            if names:
                table = new_recording_table(names)
        path = edit_spreadsheet(self, path=current, table=table,
                                suggested_path=suggested, suggest=table is not None)
        if path:
            self.spreadsheet.set_value(path)

    # ── Parameters ────────────────────────────────────────────────────────────

    def load(self, params: Params) -> None:
        self.raw_data.set_value(params.raw_data)
        self.spreadsheet.set_value(params.spreadsheet_file_name)
        self.spreadsheet_range.setText(params.spreadsheet_range)
        self.custom_grp_order.setText(",".join(params.custom_grp_order))
        self.spike_detected_data.set_value(params.spike_detected_data)
        self.trunc_rec.setChecked(params.trunc_rec)
        self.trunc_length.setValue(params.trunc_length)
        self.trunc_keep.setCurrentIndex(
            max(0, self.trunc_keep.findData(params.trunc_keep)))
        self.output_data_folder.set_value(params.output_data_folder)
        self.output_data_folder_name.setText(params.output_data_folder_name)
        self.cache_dir.set_value(params.cache_dir)
        self.derived_data_folder.set_value(params.derived_data_folder)
        # None means "work it out from free disk", which the spinbox shows as
        # Automatic at its minimum.
        self.cache_budget_gb.setValue(
            0.0 if params.cache_budget_gb is None else float(params.cache_budget_gb))

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
        self._detect_timer.start()

    def save(self, params: Params) -> None:
        params.raw_data = self.raw_data.value
        params.spreadsheet_file_name = self.spreadsheet.value
        params.spreadsheet_range = self.spreadsheet_range.text()
        params.custom_grp_order = [
            g.strip() for g in self.custom_grp_order.text().split(",") if g.strip()]
        params.spike_detected_data = self.spike_detected_data.value
        params.trunc_rec = self.trunc_rec.isChecked()
        params.trunc_length = self.trunc_length.value()
        params.trunc_keep = self.trunc_keep.currentData()
        params.output_data_folder = self.output_data_folder.value
        params.output_data_folder_name = self.output_data_folder_name.text()
        params.cache_dir = self.cache_dir.value
        params.derived_data_folder = self.derived_data_folder.value
        budget = self.cache_budget_gb.value()
        params.cache_budget_gb = None if budget <= 0 else budget

        params.fs = self.fs.value()
        params.d_samp_f = self.d_samp_f.value()
        params.potential_difference_unit = self.potential_difference_unit.currentText()
        params.channel_layout = self.channel_layout.currentText()
