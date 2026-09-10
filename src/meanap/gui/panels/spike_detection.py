"""Spike detection settings.

Thirteen settings, of which two decide what a run does: which thresholds, and
which method's spikes feed steps 2-4. The bandpass corners, the refractory
period and the template clustering are the defaults MEA-NAP has always shipped —
real settings, occasionally changed, but not part of setting a run up. Those are
folded away; see :mod:`meanap.gui.advanced`.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.widgets import show_auto_or_value
from meanap.params import Params

WAVELET_METHODS = ["bior1.5", "bior1.3", "db2", "mea"]
SPIKE_METHODS = ["bior1p5", "bior1p3", "mergedAll", "mergedWavelet", "thr4p5", "thr5p0", "thr3p5"]
TEMPLATE_METHODS = ["PCA", "spikeWidthAndAmplitude", "amplitudeAndWidthAndSymmetry"]


class SpikeDetectionPanel(QWidget):
    #: Open the spike and burst viewer. The panel does not open it itself: the
    #: viewer starts from the whole ``Params`` and hands settings back to it,
    #: and only the window holds one.
    open_viewer_requested = pyqtSignal()

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

        # Settings on this tab are only checkable against real traces, and this
        # is the one place in the GUI that shows them. It sits at the top of the
        # tab rather than the bottom because looking first, then setting, is the
        # order that saves a run.
        self.open_viewer_btn = QPushButton("Open spike and burst viewer…")
        self.open_viewer_btn.setToolTip(
            "Look at a recording's traces with the detected spikes on them, "
            "check the waveforms and refractory violations, and try burst "
            "parameters — then bring the settings back here.")
        self.open_viewer_btn.clicked.connect(self.open_viewer_requested.emit)
        viewer_row = QHBoxLayout()
        viewer_row.addWidget(self.open_viewer_btn)
        viewer_row.addStretch()
        form0.addRow(viewer_row)

        rechecking = AdvancedSection()
        rechecking.form().addRow("Re-check previous spike data",
                                 self.run_spike_check)
        form0.addRow(rechecking)

        # ── Thresholds ────────────────────────────────────────────────────────
        thr_box = QGroupBox("Thresholds")
        form = QFormLayout(thr_box)

        self.thresholds = QLineEdit("3, 4, 5")
        self.thresholds.setPlaceholderText("e.g. 3, 4, 5")
        self.abs_thresholds = QLineEdit()
        self.abs_thresholds.setPlaceholderText("Leave blank to use relative thresholds")

        form.addRow("Relative thresholds (MAD multiplier below median)", self.thresholds)

        # Absolute thresholds override the relative ones, so showing both side
        # by side reads as "fill in either", which is not what it means.
        absolute = AdvancedSection()
        absolute.form().addRow("Absolute thresholds (µV)", self.abs_thresholds)
        form.addRow(absolute)

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
        form2.addRow("Spike method for analysis", self.spikes_method)

        cost = AdvancedSection()
        cost.form().addRow("Wavelet cost", self.cost_list)
        form2.addRow(cost)

        # ── Filtering ─────────────────────────────────────────────────────────
        # Nothing in this group or the next is part of configuring a run, so
        # they fold whole rather than becoming a box holding one collapsed
        # header. Named for what they hold, so a closed one still says so.
        filt_box = AdvancedSection("Bandpass filter")
        form3 = filt_box.form()

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
        tmpl_box = AdvancedSection("Spike templates and refractory period")
        form4 = tmpl_box.form()

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

        # ── Bursts ────────────────────────────────────────────────────────────
        # Burst detection reads nothing but the spikes this tab produces, so it
        # belongs beside them rather than on a tab of its own. Folded away:
        # the defaults are the published ones, and the viewer is where anyone
        # who wants to change them will have decided to.
        burst_box = AdvancedSection("Burst detection")
        form5 = burst_box.form()

        self.network_burst_min_spike = QSpinBox()
        self.network_burst_min_spike.setRange(1, 1000)
        self.network_burst_min_spike.setValue(10)

        self.network_burst_min_channel = QSpinBox()
        self.network_burst_min_channel.setRange(1, 1000)
        self.network_burst_min_channel.setValue(3)

        # "automatic" and a number are the two things this setting can be, so
        # it is two widgets: a fixed value typed into a box that says
        # "automatic" would have to be guessed at.
        self.network_burst_isi_auto = QCheckBox()
        self.network_burst_isi_auto.setChecked(True)
        self.network_burst_isi = QDoubleSpinBox()
        self.network_burst_isi.setRange(0.0001, 100)
        self.network_burst_isi.setDecimals(4)
        self.network_burst_isi.setValue(0.1)
        self.network_burst_isi.setSuffix(" s")
        self.network_burst_isi.setEnabled(False)
        self.network_burst_isi_auto.toggled.connect(
            lambda on: self.network_burst_isi.setEnabled(not on))

        self.network_burst_merge_gap = QDoubleSpinBox()
        self.network_burst_merge_gap.setRange(0, 10000)
        self.network_burst_merge_gap.setDecimals(1)
        self.network_burst_merge_gap.setValue(20.0)
        self.network_burst_merge_gap.setSuffix(" ms")
        self.network_burst_merge_gap.setToolTip(
            "Bursts less than this far apart are reported as one burst.\n\n"
            "ISIn detection splits on the gap between individual spikes, so on "
            "a densely firing array one network event arrives as a run of "
            "short fragments a few milliseconds apart, and the burst count and "
            "duration then describe fragments rather than events. Merging only "
            "rejoins bursts already found; it cannot add time or spikes the "
            "detector called quiet.\n\n"
            "Set to 0 to report every fragment separately.")

        self.single_burst_min_spike = QSpinBox()
        self.single_burst_min_spike.setRange(1, 1000)
        self.single_burst_min_spike.setValue(5)

        self.single_burst_isi_auto = QCheckBox()
        self.single_burst_isi_auto.setChecked(True)
        self.single_burst_isi = QDoubleSpinBox()
        self.single_burst_isi.setRange(0.0001, 100)
        self.single_burst_isi.setDecimals(4)
        self.single_burst_isi.setValue(0.1)
        self.single_burst_isi.setSuffix(" s")
        self.single_burst_isi.setEnabled(False)
        self.single_burst_isi_auto.toggled.connect(
            lambda on: self.single_burst_isi.setEnabled(not on))

        form5.addRow("Network burst: min spikes", self.network_burst_min_spike)
        form5.addRow("Network burst: min channels", self.network_burst_min_channel)
        form5.addRow("Network burst: automatic ISIn threshold",
                     self.network_burst_isi_auto)
        form5.addRow("Network burst: ISIn threshold", self.network_burst_isi)
        form5.addRow("Network burst: merge bursts closer than",
                     self.network_burst_merge_gap)
        form5.addRow("Single-channel burst: min spikes", self.single_burst_min_spike)
        form5.addRow("Single-channel burst: automatic ISI threshold",
                     self.single_burst_isi_auto)
        form5.addRow("Single-channel burst: ISI threshold", self.single_burst_isi)

        layout.addWidget(ctrl_box)
        layout.addWidget(thr_box)
        layout.addWidget(wav_box)
        layout.addWidget(filt_box)
        layout.addWidget(tmpl_box)
        layout.addWidget(burst_box)
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

        self.network_burst_min_spike.setValue(int(params.min_spike_network_burst))
        self.network_burst_min_channel.setValue(int(params.min_channel_network_burst))
        show_auto_or_value(self.network_burst_isi_auto, self.network_burst_isi,
                           params.bakkum_network_burst_isi_n_threshold)
        self.network_burst_merge_gap.setValue(
            float(params.bakkum_network_burst_merge_gap_ms))
        self.single_burst_min_spike.setValue(int(params.single_channel_burst_min_spike))
        show_auto_or_value(self.single_burst_isi_auto, self.single_burst_isi,
                           params.single_channel_isi_threshold)

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

        params.min_spike_network_burst = self.network_burst_min_spike.value()
        params.min_channel_network_burst = self.network_burst_min_channel.value()
        params.bakkum_network_burst_isi_n_threshold = (
            "automatic" if self.network_burst_isi_auto.isChecked()
            else self.network_burst_isi.value())
        params.bakkum_network_burst_merge_gap_ms = \
            self.network_burst_merge_gap.value()
        params.single_channel_burst_min_spike = self.single_burst_min_spike.value()
        params.single_channel_isi_threshold = (
            "automatic" if self.single_burst_isi_auto.isChecked()
            else self.single_burst_isi.value())
