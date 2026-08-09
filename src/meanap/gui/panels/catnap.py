"""CAT-NAP panel: suite2p folder scanner, denoising settings, trace preview."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from meanap.catnap.scanner import Suite2pRecording, find_suite2p_recordings
from meanap.catnap.loader import Suite2pData, load_suite2p
from meanap.catnap.denoising import oasis_available
from meanap.gui.panels.cell_type_groups import CellTypeGroupEditor
from meanap.gui.advanced import AdvancedSection
from meanap.params import Params, is_remote_url

ACTIVITY_TYPES = ["peaks", "denoised F", "F", "spks"]

# Subnetwork grouping modes, in combo-box order. The stored value of
# ``Params.twop_subnetwork_groups`` is None / "E/I" / a dict of expressions;
# CUSTOM and EXPRESSIONS both produce a dict, differing only in how it is edited.
MODE_PER_MARKER = "One subnetwork per marker"
MODE_EI = "Excitatory vs inhibitory"
MODE_CUSTOM = "Custom groups"
MODE_EXPRESSIONS = "Custom groups (expressions)"
GROUP_MODES = [MODE_PER_MARKER, MODE_EI, MODE_CUSTOM, MODE_EXPRESSIONS]


# ── Background worker threads ─────────────────────────────────────────────────

class _ScanWorker(QThread):
    finished = pyqtSignal(list)  # list[Suite2pRecording]
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, root: str) -> None:
        super().__init__()
        self._root = root

    def run(self) -> None:
        # A share-link scan is one HTTP request per folder, so it both takes a
        # while and can fail — neither of which a silent "found 0" would convey.
        try:
            recordings = find_suite2p_recordings(
                self._root, progress=lambda done, total: self.progress.emit(done, total))
        except Exception as e:
            self.error.emit(str(e))
            return
        self.finished.emit(recordings)


class _LoadWorker(QThread):
    finished = pyqtSignal(object)  # Suite2pData
    error = pyqtSignal(str)

    def __init__(self, plane0_dir: str) -> None:
        super().__init__()
        self._dir = plane0_dir

    def run(self) -> None:
        try:
            data = load_suite2p(self._dir)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class _DenoiseWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, plane0_dir: str, overwrite: bool,
                 threshold: float, t_before: float, t_after: float) -> None:
        super().__init__()
        self._dir = plane0_dir
        self._overwrite = overwrite
        self._threshold = threshold
        self._t_before = t_before
        self._t_after = t_after

    def run(self) -> None:
        from meanap.catnap.denoising import process_suite2p_folder
        try:
            self.progress.emit("Running denoising…")
            process_suite2p_folder(
                self._dir,
                overwrite=self._overwrite,
                denoising_threshold=self._threshold,
                time_before_peak_s=self._t_before,
                time_after_peak_s=self._t_after,
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ── Embedded matplotlib figure ────────────────────────────────────────────────

class _TraceCanvas(FigureCanvasQTAgg):
    """A small matplotlib canvas for previewing traces."""

    def __init__(self) -> None:
        self._fig = Figure(figsize=(6, 4), tight_layout=True)
        super().__init__(self._fig)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._draw_placeholder()

    def _draw_placeholder(self) -> None:
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.text(0.5, 0.5, "Select a recording to preview traces",
                ha="center", va="center", transform=ax.transAxes,
                color="gray", fontsize=10)
        ax.axis("off")
        self.draw()

    def plot_traces(self, data: Suite2pData, cell_indices: list[int],
                    activity: str) -> None:
        self._fig.clear()
        n = len(cell_indices)
        if n == 0:
            self._draw_placeholder()
            return

        t = (data.time_points if data.time_points is not None
             else np.arange(data.n_frames) / data.fs)

        for row, cell_idx in enumerate(cell_indices):
            ax = self._fig.add_subplot(n, 1, row + 1)

            # Always show raw F
            ax.plot(t, data.F[cell_idx], color="0.6", lw=0.8, label="F")

            if activity in ("denoised F", "peaks") and data.F_denoised is not None:
                ax.plot(t, data.F_denoised[cell_idx], color="tab:red", lw=1.2, label="Denoised")

                # Mark peaks
                if activity == "peaks" and data.peak_start_frames is not None:
                    peak_frames = data.peak_start_frames[cell_idx]
                    valid = peak_frames[~np.isnan(peak_frames)].astype(int)
                    if len(valid):
                        peak_t = t[np.clip(valid, 0, len(t) - 1)]
                        peak_y = data.F_denoised[cell_idx][np.clip(valid, 0, len(t) - 1)]
                        ax.scatter(peak_t, peak_y, marker="x", color="tab:blue",
                                   zorder=5, s=30, label="Events")

            elif activity == "spks":
                ax.plot(t, data.spks[cell_idx], color="tab:green", lw=0.8, label="Spks")

            is_cell = bool(data.iscell[cell_idx, 0])
            ax.set_ylabel(f"ROI {cell_idx}\n({'cell' if is_cell else 'non-cell'})",
                          fontsize=7, rotation=0, ha="right", va="center")
            ax.tick_params(labelsize=7)
            ax.spines[["top", "right"]].set_visible(False)
            if row == 0:
                ax.legend(fontsize=7, loc="upper right", frameon=False)
            if row == n - 1:
                ax.set_xlabel("Time (s)", fontsize=8)

        self.draw()


# ── Main CAT-NAP panel ────────────────────────────────────────────────────────

class CatNapPanel(QWidget):
    log_message = pyqtSignal(str)
    #: A batch spreadsheet was written; the Data tab points itself at it.
    spreadsheet_saved = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._recordings: list[Suite2pRecording] = []
        self._current_data: Suite2pData | None = None
        self._current_plane0: str = ""
        # (n_roi_ids, n_markers) membership from the cell-type spreadsheet,
        # used to show live group sizes while editing. None until one is read.
        self._celltype_matrix: np.ndarray | None = None

        # background worker refs (kept alive)
        self._scan_worker: _ScanWorker | None = None
        self._load_worker: _LoadWorker | None = None
        self._denoise_worker: _DenoiseWorker | None = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([320, 580])

    # ── Panel construction ────────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        # Scan controls
        scan_box = QGroupBox("Suite2p recordings")
        scan_layout = QVBoxLayout(scan_box)

        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText(
            "Folder holding all your recordings, or a Dropbox share link…")
        self._folder_edit.setToolTip(
            "The folder holding every recording — or paste a Dropbox folder "
            "share link to scan it without downloading anything. Recordings "
            "found behind a link are fetched one at a time when the pipeline "
            "runs; trace preview and denoising here need a local folder."
        )
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(72)
        self._browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(self._browse_btn)

        self._scan_btn = QPushButton("Scan for suite2p folders")
        self._scan_btn.clicked.connect(self._on_scan)

        self._recording_list = QListWidget()
        self._recording_list.currentRowChanged.connect(self._on_recording_selected)

        self._make_sheet_btn = QPushButton("Make spreadsheet from these…")
        self._make_sheet_btn.setEnabled(False)
        self._make_sheet_btn.setToolTip(
            "Build the batch spreadsheet from the recordings found above, so "
            "the names match the data exactly. DIV is filled in where the name "
            "says it; the genotype/group column is yours to fill in."
        )
        self._make_sheet_btn.clicked.connect(self._on_make_spreadsheet)

        scan_layout.addLayout(folder_row)
        scan_layout.addWidget(self._scan_btn)
        scan_layout.addWidget(QLabel("Found recordings:"))
        scan_layout.addWidget(self._recording_list)
        scan_layout.addWidget(self._make_sheet_btn)

        # Recording info
        info_box = QGroupBox("Recording info")
        info_form = QFormLayout(info_box)
        self._info_cells = QLabel("—")
        self._info_fs = QLabel("—")
        self._info_duration = QLabel("—")
        self._info_denoised = QLabel("—")
        info_form.addRow("Cells (iscell):", self._info_cells)
        info_form.addRow("Sampling rate:", self._info_fs)
        info_form.addRow("Duration:", self._info_duration)
        info_form.addRow("Denoised data:", self._info_denoised)

        # Pipeline mode: master switch mirroring MATLAB Params.suite2pMode.
        # When ticked, a pipeline run analyses suite2p data via the CAT-NAP path
        # rather than raw MEA recordings.
        mode_box = QGroupBox("Pipeline mode")
        mode_form = QFormLayout(mode_box)
        self._suite2p_mode = QCheckBox()
        mode_form.addRow("Analyse suite2p data (CAT-NAP)", self._suite2p_mode)

        # Denoising settings
        denoise_box = QGroupBox("Denoising settings")
        denoise_form = QFormLayout(denoise_box)

        if not oasis_available():
            warn = QLabel("⚠ OASIS not installed — using Savitzky-Golay fallback.\n"
                          "Install from https://github.com/j-friedrich/OASIS")
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #aa6600; font-size: 10px;")
            denoise_form.addRow(warn)

        self._denoise_threshold = QDoubleSpinBox()
        self._denoise_threshold.setRange(0.1, 10.0)
        self._denoise_threshold.setDecimals(2)
        self._denoise_threshold.setSingleStep(0.1)
        self._denoise_threshold.setValue(1.3)

        self._time_before = QDoubleSpinBox()
        self._time_before.setRange(0.0, 60.0)
        self._time_before.setDecimals(2)
        self._time_before.setSuffix(" s")
        self._time_before.setValue(1.0)

        self._time_after = QDoubleSpinBox()
        self._time_after.setRange(0.0, 60.0)
        self._time_after.setDecimals(2)
        self._time_after.setSuffix(" s")
        self._time_after.setValue(2.05)

        self._redo_denoising = QCheckBox()

        denoise_form.addRow("Threshold multiplier", self._denoise_threshold)

        # The window either side of a peak is a property of the indicator, not
        # of the experiment, and redoing is a one-off.
        denoise_advanced = AdvancedSection()
        denoise_advanced.form().addRow("Time before peak", self._time_before)
        denoise_advanced.form().addRow("Time after peak", self._time_after)
        denoise_advanced.form().addRow("Redo if already exists", self._redo_denoising)
        denoise_form.addRow(denoise_advanced)

        self._denoise_btn = QPushButton("Run denoising on selected recording")
        self._denoise_btn.setEnabled(False)
        self._denoise_btn.clicked.connect(self._on_denoise)

        layout.addWidget(scan_box)
        layout.addWidget(info_box)
        layout.addWidget(mode_box)
        layout.addWidget(denoise_box)
        layout.addWidget(self._denoise_btn)
        layout.addStretch()
        return w

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        # Activity & preview controls
        ctrl_box = QGroupBox("Trace preview")
        ctrl_form = QFormLayout(ctrl_box)

        self._activity_combo = QComboBox()
        self._activity_combo.addItems(ACTIVITY_TYPES)
        self._activity_combo.currentTextChanged.connect(self._refresh_plot)

        self._n_cells_preview = QSpinBox()
        self._n_cells_preview.setRange(1, 20)
        self._n_cells_preview.setValue(3)
        self._n_cells_preview.valueChanged.connect(self._refresh_plot)

        self._remove_no_peaks = QCheckBox()

        ctrl_form.addRow("Activity type", self._activity_combo)
        ctrl_form.addRow("Cells to preview", self._n_cells_preview)
        ctrl_form.addRow("Exclude cells with no peaks", self._remove_no_peaks)

        # Embedded trace canvas
        self._canvas = _TraceCanvas()

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(ctrl_box)
        preview_layout.addWidget(self._canvas, stretch=1)

        # Trace preview and the group editor both want vertical room, and which
        # one matters depends on what the user is doing — let them decide.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(preview)
        splitter.addWidget(self._build_subnetwork_box())
        splitter.setSizes([360, 360])

        # Status log
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        log_layout.addWidget(self._log)

        layout.addWidget(splitter, stretch=1)
        layout.addWidget(log_box)
        return w

    def _build_subnetwork_box(self) -> QWidget:
        """Cell-type subnetwork settings (see catnap/subnetwork.py)."""
        box = QGroupBox("Cell-type subnetworks")
        layout = QVBoxLayout(box)

        form = QFormLayout()
        self._subnetwork_enabled = QCheckBox()
        self._subnetwork_enabled.toggled.connect(self._update_subnetwork_enabled)
        form.addRow("Analyse cell-type subnetworks", self._subnetwork_enabled)

        file_row = QHBoxLayout()
        self._celltype_file = QLineEdit()
        self._celltype_file.setPlaceholderText(
            "Auto-detect a spreadsheet in each recording's folder"
        )
        browse = QPushButton("Browse…")
        browse.setFixedWidth(72)
        browse.clicked.connect(self._on_browse_celltype)
        self._load_markers_btn = QPushButton("Load markers")
        self._load_markers_btn.setFixedWidth(96)
        self._load_markers_btn.clicked.connect(lambda: self._load_markers(verbose=True))
        file_row.addWidget(self._celltype_file)
        file_row.addWidget(browse)
        file_row.addWidget(self._load_markers_btn)
        form.addRow("Cell-type file", file_row)

        self._group_mode = QComboBox()
        self._group_mode.addItems(GROUP_MODES)
        self._group_mode.currentTextChanged.connect(self._update_subnetwork_enabled)
        form.addRow("Grouping", self._group_mode)
        layout.addLayout(form)

        self._group_editor = CellTypeGroupEditor()
        self._group_editor.changed.connect(self._validate_groups)

        self._group_text = QPlainTextEdit()
        self._group_text.setPlaceholderText(
            "One group per line, as  Name = expression\n"
            "e.g.  Inhibitory = GAD+ | PV+ | SST+\n"
            "      Excitatory = NeuN+ & ~GAD+ & ~PV+ & ~SST+\n"
            "Operators: & (and)  | (or)  ~ (not)  ( )"
        )
        self._group_text.setMaximumHeight(110)
        self._group_text.textChanged.connect(self._validate_groups)

        self._group_status = QLabel("")
        self._group_status.setWordWrap(True)
        self._group_status.setStyleSheet("font-size: 10px;")

        layout.addWidget(self._group_editor)
        layout.addWidget(self._group_text)
        layout.addWidget(self._group_status)

        self._update_subnetwork_enabled()
        return box

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select raw data folder",
                                                self._folder_edit.text())
        if path:
            self._folder_edit.setText(path)

    def _on_scan(self) -> None:
        root = self._folder_edit.text().strip()
        if not root:
            self._log_msg("Please enter or browse to a raw data folder, or paste "
                          "a Dropbox folder share link.")
            return

        self._scan_btn.setEnabled(False)
        self._log_msg("Reading share link (no data is downloaded)…" if is_remote_url(root)
                      else f"Scanning {root}…")

        self._scan_worker = _ScanWorker(root)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_progress(self, done: int, total: int) -> None:
        # Only worth saying for a scan slow enough to look stuck, and only at
        # intervals — a line per folder would bury everything else in the log.
        if total >= 10 and done and (done % 10 == 0):
            self._log_msg(f"  checked {done}/{total} folders…")

    def _on_scan_error(self, message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._log_msg(f"Scan failed: {message}")

    def _on_scan_done(self, recordings: list[Suite2pRecording]) -> None:
        self._recordings = recordings
        self._recording_list.clear()
        for rec in recordings:
            icon = "✓" if rec.has_denoised else "○"
            item = QListWidgetItem(f"{icon}  {rec.name}")
            self._recording_list.addItem(item)

        self._log_msg(f"Found {len(recordings)} suite2p recording(s).")
        if not recordings:
            self._log_msg("  Each recording should be its own sub-folder holding "
                          "suite2p/plane0/stat.npy. Point this at the folder that "
                          "contains those, not at one recording.")
        elif any(rec.is_remote for rec in recordings):
            self._log_msg("  These live behind the share link — the pipeline "
                          "fetches them one at a time when it runs. Trace preview "
                          "and denoising here need a local folder.")
        self._make_sheet_btn.setEnabled(bool(recordings))
        self._scan_btn.setEnabled(True)
        # Pick up cell-type markers as soon as we know where the recordings are,
        # so the group editor is usable without a separate click.
        self._load_markers()

    def _on_recording_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._recordings):
            return

        rec = self._recordings[row]
        if rec.is_remote:
            # Nothing to read without fetching hundreds of MB, which is the one
            # thing a scan of a share link exists to avoid.
            self._current_plane0 = ""
            self._current_data = None
            self._denoise_btn.setEnabled(False)
            for label in (self._info_cells, self._info_fs,
                          self._info_duration, self._info_denoised):
                label.setText("—")
            self._log_msg(f"{rec.name} is behind the share link — preview and "
                          "denoising need the data on this machine. The pipeline "
                          "run handles it without downloading the whole dataset.")
            return

        self._current_plane0 = str(rec.suite2p_dir)
        self._log_msg(f"Loading {rec.name}…")
        self._denoise_btn.setEnabled(False)
        self._load_markers()

        self._load_worker = _LoadWorker(self._current_plane0)
        self._load_worker.finished.connect(self._on_load_done)
        self._load_worker.error.connect(lambda e: self._log_msg(f"Load error: {e}"))
        self._load_worker.start()

    def _on_make_spreadsheet(self) -> None:
        """Turn the scan into a batch spreadsheet, opened for editing."""
        from meanap.gui.panels.spreadsheet_editor import edit_spreadsheet
        from meanap.pipeline.spreadsheet import new_recording_table

        if not self._recordings:
            return

        root = self._folder_edit.text().strip()
        # A share link has no folder to suggest, so fall back to wherever the
        # results are going — the sheet has to land somewhere local either way.
        suggested_dir = Path(root) if root and not is_remote_url(root) else Path.cwd()
        suggested = str(suggested_dir / "recordings.csv")

        path = edit_spreadsheet(
            self, table=new_recording_table(r.name for r in self._recordings),
            suggested_path=suggested)
        if path:
            self._log_msg(f"Spreadsheet saved to {path}")
            self.spreadsheet_saved.emit(path)

    def _on_load_done(self, data: Suite2pData) -> None:
        self._current_data = data
        self._info_cells.setText(f"{data.n_cells} / {len(data.iscell)} ROIs")
        self._info_fs.setText(f"{data.fs:.2f} Hz")
        self._info_duration.setText(f"{data.duration_s:.1f} s")
        self._info_denoised.setText("Yes" if data.F_denoised is not None else "No")
        self._denoise_btn.setEnabled(True)
        self._log_msg(f"Loaded: {data.n_cells} cells, {data.fs:.1f} Hz, "
                      f"{data.duration_s:.1f} s duration")
        self._refresh_plot()

    def _on_denoise(self) -> None:
        if not self._current_plane0:
            return

        self._denoise_btn.setEnabled(False)
        self._denoise_worker = _DenoiseWorker(
            plane0_dir=self._current_plane0,
            overwrite=self._redo_denoising.isChecked(),
            threshold=self._denoise_threshold.value(),
            t_before=self._time_before.value(),
            t_after=self._time_after.value(),
        )
        self._denoise_worker.progress.connect(self._log_msg)
        self._denoise_worker.finished.connect(self._on_denoise_done)
        self._denoise_worker.error.connect(lambda e: self._log_msg(f"Denoising error: {e}"))
        self._denoise_worker.start()

    def _on_denoise_done(self) -> None:
        self._log_msg("Denoising complete. Reloading data…")
        # Reload to pick up the new .npy files
        self._load_worker = _LoadWorker(self._current_plane0)
        self._load_worker.finished.connect(self._on_load_done)
        self._load_worker.error.connect(lambda e: self._log_msg(f"Reload error: {e}"))
        self._load_worker.start()

        # Update the denoised badge in the recording list
        row = self._recording_list.currentRow()
        if 0 <= row < len(self._recordings):
            self._recordings[row].has_denoised = True
            rec = self._recordings[row]
            self._recording_list.item(row).setText(f"✓  {rec.name}")

    def _refresh_plot(self) -> None:
        if self._current_data is None:
            return

        data = self._current_data
        activity = self._activity_combo.currentText()
        n = self._n_cells_preview.value()

        # Prefer cell ROIs; optionally filter to those with detected peaks
        cell_indices = list(np.where(data.cell_mask)[0])
        if self._remove_no_peaks.isChecked() and data.peak_start_frames is not None:
            cell_indices = [
                i for i in cell_indices
                if not np.all(np.isnan(data.peak_start_frames[i]))
            ]

        preview_indices = cell_indices[:n]
        self._canvas.plot_traces(data, preview_indices, activity)

    # ── Cell-type subnetwork slots ────────────────────────────────────────────

    def _update_subnetwork_enabled(self) -> None:
        """Show only the editor the current grouping mode uses."""
        on = self._subnetwork_enabled.isChecked()
        mode = self._group_mode.currentText()
        for widget in (self._celltype_file, self._load_markers_btn, self._group_mode):
            widget.setEnabled(on)
        self._group_editor.setVisible(on and mode == MODE_CUSTOM)
        self._group_text.setVisible(on and mode == MODE_EXPRESSIONS)
        self._group_status.setVisible(on)
        self._validate_groups()

    def _on_browse_celltype(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select cell-type spreadsheet", self._celltype_file.text(),
            "Spreadsheets (*.csv *.xlsx *.xls)",
        )
        if path:
            self._celltype_file.setText(path)
            self._load_markers(verbose=True)

    def _resolve_celltype_file(self) -> Path | None:
        """Explicit path if set, else auto-detect beside the selected recording."""
        from meanap.catnap.subnetwork import find_cell_type_file

        explicit = self._celltype_file.text().strip()
        if explicit:
            path = Path(explicit)
            return path if path.exists() else None

        # Remote recordings have no folder to look beside; the run reads their
        # cell-type file from the store instead.
        local = [r for r in self._recordings if not r.is_remote]
        row = self._recording_list.currentRow()
        folders = []
        if 0 <= row < len(self._recordings) and not self._recordings[row].is_remote:
            folders.append(Path(self._recordings[row].suite2p_dir).parent.parent)
        folders += [Path(r.suite2p_dir).parent.parent for r in local]
        for folder in folders:
            found = find_cell_type_file(folder.parent, folder.name)
            if found is not None:
                return found
        return None

    def _load_markers(self, verbose: bool = False) -> None:
        """Read the spreadsheet's marker columns into the group editor."""
        from meanap.catnap.subnetwork import build_marker_matrix, load_cell_type_table

        path = self._resolve_celltype_file()
        if path is None:
            if verbose:
                self._log_msg("No cell-type spreadsheet found. Browse to one, or "
                              "put a single .csv/.xlsx in each recording's folder.")
            return
        try:
            table = load_cell_type_table(path)
            markers = list(table.columns)
            # Membership over every ROI id the spreadsheet mentions — the run's
            # `channels` are not known here, so use the full id range to give
            # the validator something concrete to count against.
            max_id = int(table.max(numeric_only=True).max()) if markers else 0
            self._celltype_matrix, markers = build_marker_matrix(
                table, np.arange(1, max_id + 2)
            )
        except Exception as e:
            self._celltype_matrix = None
            self._log_msg(f"Could not read {Path(path).name}: {e}")
            return
        if not markers:
            self._celltype_matrix = None
            self._log_msg(f"{Path(path).name} has no columns with cell ids in them.")
            return

        self._group_editor.set_markers(markers)
        if verbose:
            self._log_msg(f"Loaded {len(markers)} marker(s) from {Path(path).name}: "
                          + ", ".join(markers))
        self._validate_groups()

    def _current_groups(self) -> dict[str, str] | str | None:
        """The value ``Params.twop_subnetwork_groups`` should take right now."""
        mode = self._group_mode.currentText()
        if mode == MODE_PER_MARKER:
            return None
        if mode == MODE_EI:
            return "E/I"
        if mode == MODE_CUSTOM:
            return self._group_editor.groups()
        groups: dict[str, str] = {}
        for line in self._group_text.toPlainText().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, expr = line.split("=", 1)
            if name.strip() and expr.strip():
                groups[name.strip()] = expr.strip()
        return groups

    def _validate_groups(self) -> None:
        """Report group sizes (or the first error) beneath the editor.

        Checking against the loaded markers here means a typo surfaces while
        editing rather than as a skipped analysis mid-run.
        """
        from meanap.catnap.subnetwork import (
            GroupExpressionError, default_ei_groups, eval_group_expression,
        )
        import numpy as np

        if not self._subnetwork_enabled.isChecked():
            self._group_status.setText("")
            return

        markers = self._group_editor.markers()
        mode = self._group_mode.currentText()
        if mode == MODE_PER_MARKER:
            self._group_status.setText(
                f"One subnetwork per marker: {', '.join(markers)}" if markers
                else "One subnetwork per marker column found in each spreadsheet."
            )
            self._group_status.setStyleSheet("font-size: 10px; color: gray;")
            return

        groups = self._current_groups()
        if mode == MODE_EI:
            groups = default_ei_groups(markers) if markers else None
            if markers and groups is None:
                self._set_group_status(
                    "No inhibitory marker (GAD+/PV+/SST+/VIP+/GABA+) in this file — "
                    "an E/I split cannot be derived; the run falls back to one "
                    "subnetwork per marker.", warn=True)
                return
        if not groups:
            self._set_group_status("No groups defined yet.", warn=True)
            return

        if not markers or self._celltype_matrix is None:
            self._set_group_status(
                f"{len(groups)} group(s) defined. Load a cell-type file to check "
                "them against its markers.")
            return

        # Counts are over every ROI the spreadsheet labels — an upper bound on
        # what a run sees, since iscell / no-peaks / inactive-node filtering all
        # happen later. Still the quickest way to catch a group that is empty or
        # accidentally swallows everything.
        summary = []
        for name, expr in groups.items():
            try:
                mask = eval_group_expression(expr, self._celltype_matrix, markers)
            except GroupExpressionError as e:
                self._set_group_status(f"{name}: {e}", warn=True)
                return
            if not mask.any():
                self._set_group_status(
                    f"{name!r} matches no labelled cell — it will be dropped.",
                    warn=True)
                return
            summary.append(f"{name} ({int(mask.sum())})")
        self._set_group_status(
            f"{len(groups)} group(s), cells labelled in the spreadsheet: "
            + ", ".join(summary))

    def _set_group_status(self, text: str, warn: bool = False) -> None:
        self._group_status.setText(("⚠ " if warn else "") + text)
        self._group_status.setStyleSheet(
            "font-size: 10px; color: " + ("#aa6600;" if warn else "gray;")
        )

    # ── Params sync ───────────────────────────────────────────────────────────

    def load(self, params: Params) -> None:
        self._folder_edit.setText(params.raw_data)
        self._suite2p_mode.setChecked(params.suite2p_mode)
        idx = self._activity_combo.findText(params.twop_activity)
        if idx >= 0:
            self._activity_combo.setCurrentIndex(idx)
        self._redo_denoising.setChecked(params.twop_redo_denoising)
        self._remove_no_peaks.setChecked(params.remove_nodes_with_no_peaks)
        self._denoise_threshold.setValue(params.twop_denoising_threshold)
        self._time_before.setValue(params.twop_denoising_time_before_peak)
        self._time_after.setValue(params.twop_denoising_time_after_peak)

        self._subnetwork_enabled.setChecked(params.twop_subnetwork_analysis)
        self._celltype_file.setText(params.twop_cell_type_file)
        self._load_markers()

        groups = params.twop_subnetwork_groups
        if groups is None:
            self._group_mode.setCurrentText(MODE_PER_MARKER)
        elif isinstance(groups, str):
            self._group_mode.setCurrentText(MODE_EI)
        else:
            # Prefer the grid; fall back to free text for anything it cannot
            # represent, so a hand-written expression is never silently lost.
            if self._group_editor.set_groups(groups):
                self._group_mode.setCurrentText(MODE_CUSTOM)
            else:
                self._group_text.setPlainText(
                    "\n".join(f"{name} = {expr}" for name, expr in groups.items())
                )
                self._group_mode.setCurrentText(MODE_EXPRESSIONS)
        self._update_subnetwork_enabled()

    def save(self, params: Params) -> None:
        params.raw_data = self._folder_edit.text()
        params.suite2p_mode = self._suite2p_mode.isChecked()
        params.twop_activity = self._activity_combo.currentText()
        params.twop_redo_denoising = self._redo_denoising.isChecked()
        params.remove_nodes_with_no_peaks = self._remove_no_peaks.isChecked()
        params.twop_denoising_threshold = self._denoise_threshold.value()
        params.twop_denoising_time_before_peak = self._time_before.value()
        params.twop_denoising_time_after_peak = self._time_after.value()

        params.twop_subnetwork_analysis = self._subnetwork_enabled.isChecked()
        params.twop_cell_type_file = self._celltype_file.text().strip()
        params.twop_subnetwork_groups = self._current_groups()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_msg(self, text: str) -> None:
        self._log.append(text)
        self.log_message.emit(text)
