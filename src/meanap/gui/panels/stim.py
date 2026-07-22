"""Stimulation (MEA-Stim) settings panel.

Binds the stim analysis parameters to :class:`meanap.params.Params`. When
"Stimulation mode" is enabled, the pipeline runs the stim analysis after step 4
(see ``meanap.pipeline.stim_step``). Detection methods and defaults mirror the
ported ``meanap.stim`` subsystem (``python/MEASTIM_PORT_PLAN.md``).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLineEdit,
    QSpinBox, QVBoxLayout, QWidget,
)

from meanap.params import Params

_DETECTION_METHODS = [
    "longblank", "blanking", "absPosThreshold", "absNegThreshold",
    "stdNeg", "axionStimEvents",
]
_PROCESSING = ["none", "medianAbs"]


class StimPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Mode ──────────────────────────────────────────────────────────────
        mode_box = QGroupBox("Stimulation mode")
        mform = QFormLayout(mode_box)
        self.stim_mode = QCheckBox("Run stimulation analysis (after spike detection)")
        self.method = QComboBox()
        self.method.addItems(_DETECTION_METHODS)
        self.processing = QComboBox()
        self.processing.addItems(_PROCESSING)
        mform.addRow("Enable", self.stim_mode)
        mform.addRow("Detection method", self.method)
        mform.addRow("Raw data processing", self.processing)

        # ── Detection ─────────────────────────────────────────────────────────
        det_box = QGroupBox("Detection")
        dform = QFormLayout(det_box)
        self.detection_val = _dspin(-1e6, 1e6, 3, 150.0)
        self.refractory = _dspin(0.0, 3600.0, 4, 2.9, " s")
        self.min_blank = _dspin(0.0, 10.0, 5, 0.004, " s")
        self.stim_duration = _dspin(0.0, 10.0, 6, 0.00012, " s")
        self.pattern_thresh = _dspin(0.0, 10.0, 5, 0.005, " s")
        self.axion_csv = QLineEdit()
        self.axion_csv.setPlaceholderText("CSV for the axionStimEvents method (rawName, well, electrode)")
        dform.addRow("Detection value", self.detection_val)
        dform.addRow("Refractory period", self.refractory)
        dform.addRow("Min blanking duration", self.min_blank)
        dform.addRow("Stim duration", self.stim_duration)
        dform.addRow("Pattern time-diff threshold", self.pattern_thresh)
        dform.addRow("Axion stim CSV", self.axion_csv)

        # ── Analysis ──────────────────────────────────────────────────────────
        an_box = QGroupBox("Response analysis")
        aform = QFormLayout(an_box)
        self.win_start = _dspin(-10.0, 0.0, 4, -0.03, " s")
        self.win_end = _dspin(0.0, 10.0, 4, 0.03, " s")
        self.post_ignore = _dspin(0.0, 1000.0, 3, 0.5, " ms")
        self.raster_bin = _dspin(0.0001, 10.0, 4, 0.1, " s")
        self.stim_dur_plot = _dspin(0.0, 10.0, 4, 0.1, " s")
        aform.addRow("Analysis window start", self.win_start)
        aform.addRow("Analysis window end", self.win_end)
        aform.addRow("Post-stim ignore duration", self.post_ignore)
        aform.addRow("Raster bin width", self.raster_bin)
        aform.addRow("Stim duration (plotting)", self.stim_dur_plot)

        # ── Significance ──────────────────────────────────────────────────────
        sig_box = QGroupBox("Shuffle significance test")
        sform = QFormLayout(sig_box)
        self.n_shuffles = QSpinBox()
        self.n_shuffles.setRange(1, 100000)
        self.n_shuffles.setValue(500)
        self.shuffle_alpha = _dspin(0.0001, 0.5, 4, 0.05)
        sform.addRow("Number of shuffles", self.n_shuffles)
        sform.addRow("Alpha", self.shuffle_alpha)

        for box in (mode_box, det_box, an_box, sig_box):
            layout.addWidget(box)
        layout.addStretch()

        self.method.currentTextChanged.connect(self._on_method_changed)
        self._on_method_changed(self.method.currentText())

    def _on_method_changed(self, method: str) -> None:
        """Only the Axion method uses the CSV field."""
        self.axion_csv.setEnabled(method == "axionStimEvents")

    def load(self, params: Params) -> None:
        self.stim_mode.setChecked(params.stimulation_mode)
        self.method.setCurrentText(params.stim_detection_method)
        self.processing.setCurrentText(params.stim_raw_data_processing)
        self.detection_val.setValue(params.stim_detection_val)
        self.refractory.setValue(params.stim_refractory_period)
        self.min_blank.setValue(params.min_blanking_duration)
        self.stim_duration.setValue(params.stim_duration)
        self.pattern_thresh.setValue(params.stim_time_diff_threshold)
        self.axion_csv.setText(params.axion_stim_csv)
        win = params.stim_analysis_window or [-0.03, 0.03]
        self.win_start.setValue(float(win[0]))
        self.win_end.setValue(float(win[1]))
        self.post_ignore.setValue(params.post_stim_window_dur)
        self.raster_bin.setValue(params.stim_raster_bin_width)
        self.stim_dur_plot.setValue(params.stim_duration_for_plotting)
        self.n_shuffles.setValue(params.stim_n_shuffles)
        self.shuffle_alpha.setValue(params.stim_shuffle_alpha)
        self._on_method_changed(self.method.currentText())

    def save(self, params: Params) -> None:
        params.stimulation_mode = self.stim_mode.isChecked()
        params.stim_detection_method = self.method.currentText()
        params.stim_raw_data_processing = self.processing.currentText()
        params.stim_detection_val = self.detection_val.value()
        params.stim_refractory_period = self.refractory.value()
        params.min_blanking_duration = self.min_blank.value()
        params.stim_duration = self.stim_duration.value()
        params.stim_time_diff_threshold = self.pattern_thresh.value()
        params.axion_stim_csv = self.axion_csv.text().strip()
        params.stim_analysis_window = [self.win_start.value(), self.win_end.value()]
        params.post_stim_window_dur = self.post_ignore.value()
        params.stim_raster_bin_width = self.raster_bin.value()
        params.stim_duration_for_plotting = self.stim_dur_plot.value()
        params.stim_n_shuffles = self.n_shuffles.value()
        params.stim_shuffle_alpha = self.shuffle_alpha.value()


def _dspin(lo: float, hi: float, decimals: int, val: float, suffix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(decimals)
    sb.setValue(val)
    if suffix:
        sb.setSuffix(suffix)
    return sb
