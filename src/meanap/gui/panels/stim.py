"""Stimulation (MEA-Stim) settings panel.

Binds the stim analysis parameters to :class:`meanap.params.Params`. When
"Stimulation mode" is enabled, the pipeline runs the stim analysis after step 4
(see ``meanap.pipeline.stim_step``). Detection methods and defaults mirror the
ported ``meanap.stim`` subsystem (``python/MEASTIM_PORT_PLAN.md``).
"""

from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLineEdit,
    QSpinBox, QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
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

        processing = AdvancedSection()
        processing.form().addRow("Raw data processing", self.processing)
        mform.addRow(processing)

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
        # The detection value is the one that changes per experiment; the
        # durations below it describe the stimulator, and the CSV only applies
        # to one of the six methods.
        dform.addRow("Detection value", self.detection_val)
        dform.addRow("Refractory period", self.refractory)

        det_advanced = AdvancedSection()
        det_advanced.form().addRow("Min blanking duration", self.min_blank)
        det_advanced.form().addRow("Stim duration", self.stim_duration)
        det_advanced.form().addRow("Pattern time-diff threshold", self.pattern_thresh)
        det_advanced.form().addRow("Axion stim CSV", self.axion_csv)
        dform.addRow(det_advanced)

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

        an_advanced = AdvancedSection()
        an_advanced.form().addRow("Post-stim ignore duration", self.post_ignore)
        an_advanced.form().addRow("Raster bin width", self.raster_bin)
        an_advanced.form().addRow("Stim duration (plotting)", self.stim_dur_plot)
        aform.addRow(an_advanced)

        # ── Significance ──────────────────────────────────────────────────────
        # Both of these are the conventional values; the group folds whole
        # rather than becoming a box holding one collapsed header.
        sig_box = AdvancedSection("Shuffle significance test")
        sform = sig_box.form()
        self.n_shuffles = QSpinBox()
        self.n_shuffles.setRange(1, 100000)
        self.n_shuffles.setValue(500)
        self.shuffle_alpha = _dspin(0.0001, 0.5, 4, 0.05)
        sform.addRow("Number of shuffles", self.n_shuffles)
        sform.addRow("Alpha", self.shuffle_alpha)

        # ── Firing-rate change from baseline ─────────────────────────────────
        # Which recordings are compared with which, read from the file names,
        # and which channels say nothing about the tissue. The Stim FR Δ tab
        # redraws with whatever is set here, so a mistyped condition can be
        # corrected without running the pipeline again.
        fr_box = QGroupBox("Firing-rate change from baseline")
        fform = QFormLayout(fr_box)
        self.fr_baseline = QLineEdit()
        self.fr_baseline.setToolTip(
            "The condition of the baseline recording: the token after DIV<n>_ in "
            "its file name, e.g. prestim in R250929CT1A_DIV250_prestim. Each "
            "slice's stimulated recordings are compared with its own baseline, "
            "matched on the run ID and slice (R250929 and CT1A).")
        self.fr_patterns = QLineEdit()
        self.fr_patterns.setPlaceholderText("stim1=Spatial 1, stim3=Spatial 3")
        self.fr_patterns.setToolTip(
            "The stimulation conditions, comma-separated, each as token=legend "
            "name (or just the token). Recordings of any other condition are "
            "ignored.")
        self.fr_require_all = QCheckBox("Only slices recorded under every pattern")
        self.fr_require_all.setToolTip(
            "When ticked a slice needs its baseline and every pattern above to "
            "be plotted; when not, its baseline and any one of them will do.")
        self.fr_grounded = QLineEdit()
        self.fr_grounded.setToolTip(
            "Channels left out of every comparison, e.g. a grounded reference "
            "electrode. Comma-separated channel IDs.")
        self.fr_stimulating = QLineEdit()
        self.fr_stimulating.setToolTip(
            "The stimulating electrodes, left out of every pattern: they read "
            "0 Hz by design. Comma-separated channel IDs.")
        fform.addRow("Baseline condition", self.fr_baseline)
        fform.addRow("Stimulation patterns", self.fr_patterns)
        fform.addRow("", self.fr_require_all)
        fform.addRow("Grounded channels", self.fr_grounded)
        fform.addRow("Stimulating channels", self.fr_stimulating)

        for box in (mode_box, det_box, an_box, sig_box, fr_box):
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
        self.fr_baseline.setText(params.fr_diff_baseline)
        self.fr_patterns.setText(format_patterns(params.fr_diff_patterns))
        self.fr_require_all.setChecked(params.fr_diff_require_all_patterns)
        self.fr_grounded.setText(format_channels(params.fr_diff_grounded_channels))
        self.fr_stimulating.setText(format_channels(params.fr_diff_stimulating_channels))
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
        params.fr_diff_baseline = self.fr_baseline.text().strip()
        params.fr_diff_patterns = parse_patterns(self.fr_patterns.text())
        params.fr_diff_require_all_patterns = self.fr_require_all.isChecked()
        params.fr_diff_grounded_channels = parse_channels(self.fr_grounded.text())
        params.fr_diff_stimulating_channels = parse_channels(self.fr_stimulating.text())


def format_patterns(patterns: dict[str, str]) -> str:
    """``{"stim1": "Spatial 1"}`` as ``stim1=Spatial 1``; a bare token when unlabelled."""
    return ", ".join(t if not label or label == t else f"{t}={label}"
                     for t, label in (patterns or {}).items())


def parse_patterns(text: str) -> dict[str, str]:
    """``stim1=Spatial 1, stim3`` as ``{"stim1": "Spatial 1", "stim3": "stim3"}``."""
    patterns = {}
    for item in text.split(","):
        token, _, label = item.partition("=")
        token, label = token.strip(), label.strip()
        if token:
            patterns[token] = label or token
    return patterns


def format_channels(channels) -> str:
    return ", ".join(str(int(c)) for c in channels or ())


def parse_channels(text: str) -> list[int]:
    """Every whole number in ``text``, in order, once: ``"21, 31 41"`` -> [21, 31, 41]."""
    return list(dict.fromkeys(int(n) for n in re.findall(r"\d+", text)))


def _dspin(lo: float, hi: float, decimals: int, val: float, suffix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(decimals)
    sb.setValue(val)
    if suffix:
        sb.setSuffix(suffix)
    return sb
