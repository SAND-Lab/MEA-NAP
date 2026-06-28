"""CAT-NAP panel: suite2p folder scanner, denoising settings, trace preview."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from meanap.catnap.scanner import Suite2pRecording, find_suite2p_recordings
from meanap.catnap.loader import Suite2pData, load_suite2p
from meanap.catnap.denoising import oasis_available
from meanap.params import Params

ACTIVITY_TYPES = ["peaks", "denoised F", "F", "spks"]


# ── Background worker threads ─────────────────────────────────────────────────

class _ScanWorker(QThread):
    finished = pyqtSignal(list)  # list[Suite2pRecording]

    def __init__(self, root: str) -> None:
        super().__init__()
        self._root = root

    def run(self) -> None:
        recordings = find_suite2p_recordings(self._root)
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._recordings: list[Suite2pRecording] = []
        self._current_data: Suite2pData | None = None
        self._current_plane0: str = ""

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
        self._folder_edit.setPlaceholderText("Raw data folder…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(72)
        self._browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(self._browse_btn)

        self._scan_btn = QPushButton("Scan for suite2p folders")
        self._scan_btn.clicked.connect(self._on_scan)

        self._recording_list = QListWidget()
        self._recording_list.currentRowChanged.connect(self._on_recording_selected)

        scan_layout.addLayout(folder_row)
        scan_layout.addWidget(self._scan_btn)
        scan_layout.addWidget(QLabel("Found recordings:"))
        scan_layout.addWidget(self._recording_list)

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
        denoise_form.addRow("Time before peak", self._time_before)
        denoise_form.addRow("Time after peak", self._time_after)
        denoise_form.addRow("Redo if already exists", self._redo_denoising)

        self._denoise_btn = QPushButton("Run denoising on selected recording")
        self._denoise_btn.setEnabled(False)
        self._denoise_btn.clicked.connect(self._on_denoise)

        layout.addWidget(scan_box)
        layout.addWidget(info_box)
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

        # Status log
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        log_layout.addWidget(self._log)

        layout.addWidget(ctrl_box)
        layout.addWidget(self._canvas, stretch=1)
        layout.addWidget(log_box)
        return w

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
            self._log_msg("Please enter or browse to a raw data folder first.")
            return

        self._scan_btn.setEnabled(False)
        self._log_msg(f"Scanning {root}…")

        self._scan_worker = _ScanWorker(root)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_done(self, recordings: list[Suite2pRecording]) -> None:
        self._recordings = recordings
        self._recording_list.clear()
        for rec in recordings:
            icon = "✓" if rec.has_denoised else "○"
            item = QListWidgetItem(f"{icon}  {rec.name}")
            self._recording_list.addItem(item)

        self._log_msg(f"Found {len(recordings)} suite2p recording(s).")
        self._scan_btn.setEnabled(True)

    def _on_recording_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._recordings):
            return

        rec = self._recordings[row]
        self._current_plane0 = str(rec.suite2p_dir)
        self._log_msg(f"Loading {rec.name}…")
        self._denoise_btn.setEnabled(False)

        self._load_worker = _LoadWorker(self._current_plane0)
        self._load_worker.finished.connect(self._on_load_done)
        self._load_worker.error.connect(lambda e: self._log_msg(f"Load error: {e}"))
        self._load_worker.start()

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

    # ── Params sync ───────────────────────────────────────────────────────────

    def load(self, params: Params) -> None:
        self._folder_edit.setText(params.raw_data)
        idx = self._activity_combo.findText(params.twop_activity)
        if idx >= 0:
            self._activity_combo.setCurrentIndex(idx)
        self._redo_denoising.setChecked(params.twop_redo_denoising)
        self._remove_no_peaks.setChecked(params.remove_nodes_with_no_peaks)
        self._denoise_threshold.setValue(params.twop_denoising_threshold)
        self._time_before.setValue(params.twop_denoising_time_before_peak)
        self._time_after.setValue(params.twop_denoising_time_after_peak)

    def save(self, params: Params) -> None:
        params.raw_data = self._folder_edit.text()
        params.twop_activity = self._activity_combo.currentText()
        params.twop_redo_denoising = self._redo_denoising.isChecked()
        params.remove_nodes_with_no_peaks = self._remove_no_peaks.isChecked()
        params.twop_denoising_threshold = self._denoise_threshold.value()
        params.twop_denoising_time_before_peak = self._time_before.value()
        params.twop_denoising_time_after_peak = self._time_after.value()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_msg(self, text: str) -> None:
        self._log.append(text)
        self.log_message.emit(text)
