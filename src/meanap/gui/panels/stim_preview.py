"""Interactive stimulation-detection preview.

Python port of MATLAB's ``stimDetectionApp`` (driven by ``runStimDetectionApp.m``):
pick a raw recording + detection method + params, run detection, and inspect the
result before committing to a full pipeline run — a selected-channel voltage
trace with detected stim marked, that channel's stim raster, an electrode
heatmap coloured by stimulation pattern, and an all-channel stim raster.

Raw loading (large ``.mat``) and detection (seconds on a full recording) run on
background threads so the UI stays responsive; switching the previewed channel
only re-plots from cached results (no re-detection).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from meanap.pipeline.io import load_raw_recording
from meanap.pipeline.channel_layout import get_coords_from_layout
from meanap.stim.detection import detect_stim_times, get_stim_patterns

_DETECTION_METHODS = [
    "longblank", "blanking", "absPosThreshold", "absNegThreshold", "stdNeg",
]
_LAYOUTS = ["MCS60", "MCS60old", "MCS59", "Axion64", "Axion16"]
# Pattern colours (0 = no stim → white); mirrors MATLAB's stimPatternColors head.
_PATTERN_COLORS = [
    "white", "#d62728", "#1f77b4", "#17becf", "#bcbd22", "#2ca02c",
    "#9467bd", "#ff7f0e", "#8c564b", "#e377c2",
]
_MAX_TRACE_POINTS = 12000   # decimation target for the voltage trace


def _pattern_color(pat: int) -> str:
    if not pat:
        return "white"
    return _PATTERN_COLORS[pat % len(_PATTERN_COLORS)]


# ── background workers ────────────────────────────────────────────────────────

class _LoadRawWorker(QThread):
    finished_ok = pyqtSignal(object)   # (dat, channels, fs)
    failed = pyqtSignal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            dat, channels, fs = load_raw_recording(self._path)
            self.finished_ok.emit((dat.astype(np.float64), channels, float(fs)))
        except Exception as exc:
            self.failed.emit(str(exc))


class _DetectWorker(QThread):
    finished_ok = pyqtSignal(object)   # (stim_info, patterns)
    failed = pyqtSignal(str)

    def __init__(self, dat, channels, coords, params: dict) -> None:
        super().__init__()
        self._dat, self._channels, self._coords, self._params = dat, channels, coords, params

    def run(self) -> None:
        try:
            dat = self._dat
            if self._params.get("stimRawDataProcessing") == "medianAbs":
                dat = np.abs(dat - np.median(dat, axis=0))
            info = detect_stim_times(dat, self._params, self._channels, self._coords)
            info, patterns = get_stim_patterns(info, self._params)
            self.finished_ok.emit((info, patterns))
        except Exception as exc:
            self.failed.emit(str(exc))


# ── canvas ────────────────────────────────────────────────────────────────────

class _PreviewCanvas(FigureCanvasQTAgg):
    def __init__(self) -> None:
        self._fig = Figure(figsize=(8, 8), tight_layout=True)
        super().__init__(self._fig)
        gs = self._fig.add_gridspec(3, 2, height_ratios=[1.1, 0.6, 1.6])
        self.ax_trace = self._fig.add_subplot(gs[0, :])
        self.ax_raster = self._fig.add_subplot(gs[1, :], sharex=self.ax_trace)
        self.ax_heatmap = self._fig.add_subplot(gs[2, 0])
        self.ax_all = self._fig.add_subplot(gs[2, 1])
        for ax in (self.ax_trace, self.ax_raster, self.ax_heatmap, self.ax_all):
            ax.text(0.5, 0.5, "", ha="center", va="center", transform=ax.transAxes)
        self.draw()

    def clear_all(self) -> None:
        for ax in (self.ax_trace, self.ax_raster, self.ax_heatmap, self.ax_all):
            ax.clear()

    def draw_channel_trace(self, dat, fs, ch_idx, ch_name, stim_times, method, det_val):
        ax = self.ax_trace
        ax.clear()
        n = dat.shape[0]
        step = max(1, n // _MAX_TRACE_POINTS)
        t = np.arange(0, n, step) / fs
        ax.plot(t, dat[::step, ch_idx], lw=0.5, color="#333333")
        if method in ("absPosThreshold", "absNegThreshold"):
            ax.axhline(det_val, color="tab:orange", lw=1, ls="--", label="threshold")
        elif method == "stdNeg":
            trace = dat[:, ch_idx]
            ax.axhline(trace.mean() - trace.std(ddof=1) * det_val,
                       color="tab:orange", lw=1, ls="--", label="threshold")
        for st in np.asarray(stim_times, float).ravel():
            ax.axvline(st, color="tab:red", lw=0.6, alpha=0.7)
        ax.set_ylabel("Voltage")
        ax.set_title(f"Channel {ch_name} — {len(stim_times)} stim event(s) detected",
                     fontsize=10, fontweight="bold")
        ax.margins(x=0)

    def draw_channel_raster(self, fs, n_samples, stim_times, stim_dur):
        ax = self.ax_raster
        ax.clear()
        dur_s = n_samples / fs
        m = max(2, round(dur_s * 1000))
        t = np.linspace(0, dur_s, m)
        vec = np.zeros(m)
        for st in np.asarray(stim_times, float).ravel():
            vec[(t >= st) & (t <= st + stim_dur)] = 1.0
        ax.plot(t, vec, color="tab:red", lw=0.8)
        ax.set_ylim(-0.5, 1.5)
        ax.set_yticks([0, 1])
        ax.set_ylabel("Stim")
        ax.set_xlabel("Time (s)")
        ax.margins(x=0)

    def draw_heatmap(self, stim_info):
        ax = self.ax_heatmap
        ax.clear()
        for info in stim_info:
            xc, yc = float(info.coords[0]), float(info.coords[1])
            if np.isnan(xc) or np.isnan(yc):
                continue
            pat = info.pattern or 0
            color = _pattern_color(pat)
            ax.add_patch(Circle((xc, yc), 0.45, facecolor=color,
                                edgecolor="black", lw=0.8, zorder=2))
            ax.text(xc, yc, str(int(info.channel_name)), ha="center", va="center",
                    fontsize=6, color="black" if pat == 0 else "white", zorder=3)
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.margins(0.08)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title("Stim electrodes (by pattern)", fontsize=10)

    def draw_all_raster(self, stim_info, fs, n_samples, stim_dur, n_patterns):
        ax = self.ax_all
        ax.clear()
        dur_s = n_samples / fs
        m = max(2, round(dur_s * 1000))
        t = np.linspace(0, dur_s, m)
        for i, info in enumerate(stim_info):
            vec = np.zeros(m)
            for st in np.asarray(info.elec_stim_times, float).ravel():
                vec[(t >= st) & (t <= st + stim_dur)] = 1.0
            offset = i * 1.2
            if n_patterns >= 2:
                color = "#bfbfbf" if not info.pattern else _pattern_color(info.pattern)
            else:
                color = "#1f77b4"
            ax.plot(t, vec + offset, color=color, lw=0.5)
        ax.set_yticks([])
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Channel (offset)")
        ax.set_title("All-channel stim raster", fontsize=10)
        ax.margins(x=0)


# ── panel ─────────────────────────────────────────────────────────────────────

class StimPreviewPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dat = None
        self._channels = None
        self._fs = 25000.0
        self._coords = None
        self._stim_info = None
        self._patterns = None
        self._raw_worker = None
        self._detect_worker = None

        root = QHBoxLayout(self)
        root.addWidget(self._build_controls(), 0)
        self._canvas = _PreviewCanvas()
        root.addWidget(self._canvas, 1)

    # --- controls ---------------------------------------------------------------
    def _build_controls(self) -> QWidget:
        w = QWidget()
        w.setMaximumWidth(340)
        layout = QVBoxLayout(w)

        file_box = QGroupBox("Recording")
        fform = QFormLayout(file_box)
        self._path = QLineEdit()
        self._path.setPlaceholderText("raw recording .mat")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._on_browse)
        prow = QHBoxLayout(); prow.addWidget(self._path); prow.addWidget(browse)
        self._layout_combo = QComboBox(); self._layout_combo.addItems(_LAYOUTS)
        self._channel_combo = QComboBox()
        self._channel_combo.currentTextChanged.connect(self._on_channel_changed)
        fform.addRow("File", prow)
        fform.addRow("Channel layout", self._layout_combo)
        fform.addRow("Preview channel", self._channel_combo)

        det_box = QGroupBox("Detection")
        dform = QFormLayout(det_box)
        self._method = QComboBox(); self._method.addItems(_DETECTION_METHODS)
        self._processing = QComboBox(); self._processing.addItems(["none", "medianAbs"])
        self._det_val = _dspin(-1e6, 1e6, 3, 150.0)
        self._refractory = _dspin(0.0, 3600.0, 4, 2.9, " s")
        self._min_blank = _dspin(0.0, 10.0, 5, 0.004, " s")
        self._pattern_thresh = _dspin(0.0, 10.0, 5, 0.005, " s")
        self._stim_dur_plot = _dspin(0.0, 10.0, 4, 0.1, " s")
        dform.addRow("Method", self._method)
        dform.addRow("Raw processing", self._processing)
        dform.addRow("Detection value", self._det_val)
        dform.addRow("Refractory period", self._refractory)
        dform.addRow("Min blanking duration", self._min_blank)
        dform.addRow("Pattern time-diff", self._pattern_thresh)
        dform.addRow("Stim duration (plot)", self._stim_dur_plot)

        self._detect_btn = QPushButton("Detect")
        self._detect_btn.setObjectName("primary")
        self._detect_btn.setEnabled(False)
        self._detect_btn.clicked.connect(self._on_detect)

        self._status = QLabel("Load a recording to begin.")
        self._status.setWordWrap(True)

        layout.addWidget(file_box)
        layout.addWidget(det_box)
        layout.addWidget(self._detect_btn)
        layout.addWidget(self._status)
        layout.addStretch()
        return w

    def load_defaults(self, params) -> None:
        """Pre-fill detection controls from a Params object (optional)."""
        try:
            self._method.setCurrentText(params.stim_detection_method)
            self._processing.setCurrentText(params.stim_raw_data_processing)
            self._det_val.setValue(params.stim_detection_val)
            self._refractory.setValue(params.stim_refractory_period)
            self._min_blank.setValue(params.min_blanking_duration)
            self._pattern_thresh.setValue(params.stim_time_diff_threshold)
            self._stim_dur_plot.setValue(params.stim_duration_for_plotting)
            self._layout_combo.setCurrentText(params.channel_layout)
        except Exception:
            pass

    # --- raw loading ------------------------------------------------------------
    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select raw recording", "",
                                              "MAT files (*.mat);;All files (*)")
        if not path:
            return
        self._path.setText(path)
        self._status.setText("Loading raw recording…")
        self._detect_btn.setEnabled(False)
        self._raw_worker = _LoadRawWorker(path)
        self._raw_worker.finished_ok.connect(self._on_raw_loaded)
        self._raw_worker.failed.connect(lambda m: self._status.setText(f"Load failed: {m}"))
        self._raw_worker.start()

    def _on_raw_loaded(self, payload) -> None:
        dat, channels, fs = payload
        self._dat, self._channels, self._fs = dat, channels, fs
        self._stim_info = self._patterns = None
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        self._channel_combo.addItems([str(int(c)) for c in np.sort(channels)])
        self._channel_combo.blockSignals(False)
        self._detect_btn.setEnabled(True)
        self._status.setText(
            f"Loaded {dat.shape[1]} channels, {dat.shape[0]/fs:.0f} s @ {fs:.0f} Hz. "
            "Set parameters and click Detect.")

    # --- detection --------------------------------------------------------------
    def _params_dict(self) -> dict:
        return {
            "stimDetectionMethod": self._method.currentText(),
            "stimRawDataProcessing": self._processing.currentText(),
            "stimDetectionVal": self._det_val.value(),
            "stimRefractoryPeriod": self._refractory.value(),
            "minBlankingDuration": self._min_blank.value(),
            "stimTimeDiffThreshold": self._pattern_thresh.value(),
            "stimDuration": 0.00012,
            "fs": self._fs,
        }

    def _on_detect(self) -> None:
        if self._dat is None:
            return
        try:
            ids, xy = get_coords_from_layout(self._layout_combo.currentText())
            by_id = {int(c): p for c, p in zip(ids, xy)}
        except Exception:
            by_id = {}
        self._coords = np.array([by_id.get(int(c), (np.nan, np.nan)) for c in self._channels],
                                dtype=float)
        self._status.setText("Running detection…")
        self._detect_btn.setEnabled(False)
        self._detect_worker = _DetectWorker(self._dat, self._channels, self._coords,
                                            self._params_dict())
        self._detect_worker.finished_ok.connect(self._on_detected)
        self._detect_worker.failed.connect(self._on_detect_failed)
        self._detect_worker.start()

    def _on_detect_failed(self, msg: str) -> None:
        self._detect_btn.setEnabled(True)
        self._status.setText(f"Detection failed: {msg}")

    def _on_detected(self, payload) -> None:
        self._stim_info, self._patterns = payload
        n_elec = sum(1 for s in self._stim_info if s.pattern and s.pattern > 0)
        self._status.setText(
            f"Detection complete: {len(self._patterns)} pattern(s), "
            f"{n_elec} stimulating electrode(s).")
        self._detect_btn.setEnabled(True)
        self._canvas.draw_heatmap(self._stim_info)
        self._canvas.draw_all_raster(self._stim_info, self._fs, self._dat.shape[0],
                                     self._stim_dur_plot.value(), len(self._patterns))
        self._redraw_channel()
        self._canvas.draw()

    # --- channel switching (no re-detection) ------------------------------------
    def _on_channel_changed(self, _text: str) -> None:
        if self._dat is not None:
            self._redraw_channel()
            self._canvas.draw()

    def _redraw_channel(self) -> None:
        txt = self._channel_combo.currentText()
        if not txt or self._dat is None:
            return
        ch_name = int(txt)
        ch_idx = int(np.flatnonzero(self._channels == ch_name)[0])
        stim_times = np.array([])
        if self._stim_info is not None:
            stim_times = self._stim_info[ch_idx].elec_stim_times
        self._canvas.draw_channel_trace(self._dat, self._fs, ch_idx, ch_name,
                                        stim_times, self._method.currentText(),
                                        self._det_val.value())
        self._canvas.draw_channel_raster(self._fs, self._dat.shape[0], stim_times,
                                         self._stim_dur_plot.value())


def _dspin(lo, hi, decimals, val, suffix=""):
    sb = QDoubleSpinBox(); sb.setRange(lo, hi); sb.setDecimals(decimals); sb.setValue(val)
    if suffix:
        sb.setSuffix(suffix)
    return sb
