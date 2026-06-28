"""Spike detection settings panel."""

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QSpinBox,
    QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt

from meanap.params import Params

WAVELET_METHODS = ["bior1.5", "bior1.3", "db2", "mea"]
SPIKE_METHODS = ["bior1p5", "bior1p3", "mergedAll", "mergedWavelet", "thr4p5", "thr5p0", "thr3p5"]
TEMPLATE_METHODS = ["PCA", "spikeWidthAndAmplitude", "amplitudeAndWidthAndSymmetry"]


class SpikeDetectionPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Detection control ─────────────────────────────────────────────────
        ctrl_box = QGroupBox("Detection control")
        form0 = QFormLayout(ctrl_box)

        self.detect_spikes = QCheckBox()
        self.detect_spikes.setChecked(True)
        self.run_spike_check = QCheckBox()

        form0.addRow("Detect spikes", self.detect_spikes)
        form0.addRow("Re-check previous spike data", self.run_spike_check)

        # ── Thresholds ────────────────────────────────────────────────────────
        thr_box = QGroupBox("Thresholds")
        form = QFormLayout(thr_box)

        self.thresholds = QLineEdit("-3.5, -4.5, -5.5")
        self.thresholds.setPlaceholderText("e.g. -3.5, -4.5, -5.5")
        self.abs_thresholds = QLineEdit()
        self.abs_thresholds.setPlaceholderText("Leave blank to use relative thresholds")

        form.addRow("Relative thresholds (σ)", self.thresholds)
        form.addRow("Absolute thresholds (µV)", self.abs_thresholds)

        # ── Wavelet settings ──────────────────────────────────────────────────
        wav_box = QGroupBox("Wavelet")
        form2 = QFormLayout(wav_box)

        self.wname_list = QListWidget()
        self.wname_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.wname_list.setMaximumHeight(90)
        for name in WAVELET_METHODS:
            item = QListWidgetItem(name)
            self.wname_list.addItem(item)
            if name == "bior1.5":
                item.setSelected(True)

        self.cost_list = QDoubleSpinBox()
        self.cost_list.setRange(-10, 10)
        self.cost_list.setDecimals(2)
        self.cost_list.setSingleStep(0.01)
        self.cost_list.setValue(-0.12)

        self.spikes_method = QComboBox()
        self.spikes_method.addItems(SPIKE_METHODS)

        form2.addRow("Wavelet methods", self.wname_list)
        form2.addRow("Wavelet cost", self.cost_list)
        form2.addRow("Spike method for analysis", self.spikes_method)

        # ── Filtering ─────────────────────────────────────────────────────────
        filt_box = QGroupBox("Bandpass filter")
        form3 = QFormLayout(filt_box)

        self.filter_low_pass = QDoubleSpinBox()
        self.filter_low_pass.setRange(0, 20000)
        self.filter_low_pass.setDecimals(0)
        self.filter_low_pass.setSuffix(" Hz")
        self.filter_low_pass.setValue(600)

        self.filter_high_pass = QDoubleSpinBox()
        self.filter_high_pass.setRange(0, 50000)
        self.filter_high_pass.setDecimals(0)
        self.filter_high_pass.setSuffix(" Hz")
        self.filter_high_pass.setValue(8000)

        form3.addRow("Low-pass cutoff", self.filter_low_pass)
        form3.addRow("High-pass cutoff", self.filter_high_pass)

        # ── Template & refractory ─────────────────────────────────────────────
        tmpl_box = QGroupBox("Template & refractory period")
        form4 = QFormLayout(tmpl_box)

        self.ref_period = QDoubleSpinBox()
        self.ref_period.setRange(0, 100)
        self.ref_period.setDecimals(1)
        self.ref_period.setSuffix(" ms")
        self.ref_period.setValue(2.0)

        self.n_spikes = QSpinBox()
        self.n_spikes.setRange(10, 10000)
        self.n_spikes.setValue(100)

        self.multiple_templates = QCheckBox()
        self.multi_template_method = QComboBox()
        self.multi_template_method.addItems(TEMPLATE_METHODS)

        form4.addRow("Refractory period", self.ref_period)
        form4.addRow("Max spikes for template", self.n_spikes)
        form4.addRow("Multiple templates", self.multiple_templates)
        form4.addRow("Template method", self.multi_template_method)

        layout.addWidget(ctrl_box)
        layout.addWidget(thr_box)
        layout.addWidget(wav_box)
        layout.addWidget(filt_box)
        layout.addWidget(tmpl_box)
        layout.addStretch()

    def load(self, params: Params) -> None:
        self.detect_spikes.setChecked(params.detect_spikes)
        self.run_spike_check.setChecked(params.run_spike_check_on_prev_spike_data)
        self.thresholds.setText(", ".join(str(t) for t in params.thresholds))
        self.abs_thresholds.setText(", ".join(str(t) for t in params.abs_thresholds))
        self.cost_list.setValue(params.cost_list)
        idx = self.spikes_method.findText(params.spikes_method)
        if idx >= 0:
            self.spikes_method.setCurrentIndex(idx)
        self.filter_low_pass.setValue(params.filter_low_pass)
        self.filter_high_pass.setValue(params.filter_high_pass)
        self.ref_period.setValue(params.ref_period)
        self.n_spikes.setValue(params.n_spikes)
        self.multiple_templates.setChecked(params.multiple_templates)
        idx = self.multi_template_method.findText(params.multi_template_method)
        if idx >= 0:
            self.multi_template_method.setCurrentIndex(idx)

        for i in range(self.wname_list.count()):
            item = self.wname_list.item(i)
            item.setSelected(item.text() in params.wname_list)

    def save(self, params: Params) -> None:
        params.detect_spikes = self.detect_spikes.isChecked()
        params.run_spike_check_on_prev_spike_data = self.run_spike_check.isChecked()

        raw = self.thresholds.text().strip()
        params.thresholds = [float(x) for x in raw.split(",") if x.strip()]

        raw_abs = self.abs_thresholds.text().strip()
        params.abs_thresholds = [float(x) for x in raw_abs.split(",") if x.strip()]

        params.wname_list = [self.wname_list.item(i).text()
                             for i in range(self.wname_list.count())
                             if self.wname_list.item(i).isSelected()]
        params.cost_list = self.cost_list.value()
        params.spikes_method = self.spikes_method.currentText()
        params.filter_low_pass = self.filter_low_pass.value()
        params.filter_high_pass = self.filter_high_pass.value()
        params.ref_period = self.ref_period.value()
        params.n_spikes = self.n_spikes.value()
        params.multiple_templates = self.multiple_templates.isChecked()
        params.multi_template_method = self.multi_template_method.currentText()
