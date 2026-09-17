"""Spike detection settings.

Thirteen settings, of which two decide what a run does: which thresholds, and
which method's spikes feed steps 2-4. A third, above them, decides whether the
nodes are electrodes or *sorted units* — spike sorting replaces the detectors
when it is on (see :mod:`meanap.pipeline.spike_sorting`), so its own settings
sit in a section that only opens when it is. The bandpass corners, the refractory
period and the template clustering are the defaults MEA-NAP has always shipped —
real settings, occasionally changed, but not part of setting a run up. Those are
folded away; see :mod:`meanap.gui.advanced`.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.widgets import show_auto_or_value
from meanap.params import Params
from meanap.pipeline.spike_sorting import (
    SUPPORTED_SORTERS, installed_sorters, sorting_available,
)

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

        # ── Spike source ─────────────────────────────────────────────────────
        # Electrodes or units as nodes. Sorting is a different first step, not
        # another detector: it needs the ``sorting`` extra, so the choice is
        # offered only when that is installed and says why otherwise.
        self.spike_source = QComboBox()
        self.spike_source.addItem("Detect spikes on each electrode", "detect")
        self.spike_source.addItem("Sort spikes into units (each unit becomes a node)", "sort")
        self.spike_source.setToolTip(
            "What the nodes of the network are.\n\n"
            "Detect: one node per electrode, its spikes found by the threshold "
            "and wavelet detectors below — what MEA-NAP has always done.\n\n"
            "Sort: a spike sorter separates the neurons an electrode hears "
            "by waveform, and each becomes its own node. Several nodes per "
            "electrode where the sorter finds several neurons. Needs the "
            "'sorting' extra (pip install meanap[sorting]).")
        self.sorter_name = QComboBox()
        for name in installed_sorters() or SUPPORTED_SORTERS:
            self.sorter_name.addItem(name)
        self.sorter_name.setToolTip(
            "Which sorter. Tridesclous2 is the default: built for few-channel "
            "data, and on MEA-NAP's synthetic low-density ground truth it "
            "recovered the most neurons with no false or duplicated units. "
            "MountainSort5 is the faster alternative. The others run but are "
            "tuned for dense probes; Kilosort4 needs a GPU to be worth it.")
        form0.addRow("Spike source", self.spike_source)
        form0.addRow("Sorter", self.sorter_name)
        self.sorting_hint = QLabel()
        self.sorting_hint.setWordWrap(True)
        self.sorting_hint.setStyleSheet("color: palette(mid); font-size: 11px;")
        form0.addRow("", self.sorting_hint)
        if not sorting_available():
            self.spike_source.model().item(1).setEnabled(False)
            self.sorting_hint.setText(
                "Spike sorting is not installed — run "
                "'uv sync --extra sorting' (or pip install meanap[sorting]) "
                "to enable it.")
        self.spike_source.currentIndexChanged.connect(self._on_spike_source_changed)

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

        # The wavelet detectors' own refractory period. Separate from the one
        # above because that one has only ever applied to the threshold
        # detectors, and because the right value differs: long enough to
        # collapse a spike detected twice, short enough to keep the
        # population spikes a busy electrode really does see 0.5–2 ms apart.
        self.wavelet_ref_period = QDoubleSpinBox()
        self.wavelet_ref_period.setRange(0, 100)
        self.wavelet_ref_period.setDecimals(2)
        self.wavelet_ref_period.setSuffix(" ms")
        self.wavelet_ref_period.setSpecialValueText("off (MATLAB behaviour)")
        self.wavelet_ref_period.setValue(0.5)
        self.wavelet_ref_period.setToolTip(
            "Refractory period for the wavelet detectors (bior1.5 etc.). The "
            "period above applies only to the threshold detectors; the "
            "wavelet path never had one, and on a dense culture 5–6 % of a "
            "busy electrode's bior1.5 spikes were the same spike detected "
            "twice, always less than 0.5 ms apart. 0.5 ms removes exactly "
            "those. Spikes 0.5–2 ms apart on one electrode are almost all "
            "distinct (several neurons firing in a burst), so the full "
            "refractory period would discard real activity. Set to 0 for the "
            "old behaviour, which is what MATLAB MEA-NAP still does.")

        self.n_spikes = QSpinBox()
        self.n_spikes.setRange(10, 10000)
        self.n_spikes.setValue(100)

        self.multiple_templates = QCheckBox()
        self.multi_template_method = QComboBox()
        self.multi_template_method.addItems(TEMPLATE_METHODS)

        form4.addRow("Refractory period (threshold detectors)", self.ref_period)
        form4.addRow("Refractory period (wavelet detectors)", self.wavelet_ref_period)
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

        # ── Spike sorting ─────────────────────────────────────────────────────
        # Only meaningful when the source is "sort"; folded away otherwise so
        # a detection run's tab looks as it always did.
        self.sort_box = AdvancedSection("Spike sorting")
        form6 = self.sort_box.form()

        self.sort_freq_min = QDoubleSpinBox()
        self.sort_freq_min.setRange(1, 20000)
        self.sort_freq_min.setDecimals(0)
        self.sort_freq_min.setSuffix(" Hz")
        self.sort_freq_min.setValue(300)
        self.sort_freq_max = QDoubleSpinBox()
        self.sort_freq_max.setRange(1, 50000)
        self.sort_freq_max.setDecimals(0)
        self.sort_freq_max.setSuffix(" Hz")
        self.sort_freq_max.setValue(6000)
        band = QHBoxLayout()
        band.addWidget(self.sort_freq_min)
        band.addWidget(QLabel("to"))
        band.addWidget(self.sort_freq_max)
        band.addStretch()
        self.sort_freq_min.setToolTip(
            "The band the sorter sees. Separate from the detectors' bandpass "
            "above: sorters cluster on waveform shape and the conventional "
            "300–6000 Hz keeps the shape while dropping the field potential.")
        self.sort_freq_max.setToolTip(self.sort_freq_min.toolTip())

        self.sort_common_reference = QComboBox()
        self.sort_common_reference.addItem("Global median across electrodes", "global_median")
        self.sort_common_reference.addItem("None", "none")
        self.sort_common_reference.setToolTip(
            "Subtract the median of all electrodes at every sample before "
            "sorting, removing noise the whole dish picks up together. "
            "Switch off if most electrodes fire synchronously enough that "
            "the median itself contains spikes.")

        self.electrode_pitch = QDoubleSpinBox()
        self.electrode_pitch.setRange(0, 5000)
        self.electrode_pitch.setDecimals(0)
        self.electrode_pitch.setSuffix(" µm")
        self.electrode_pitch.setSpecialValueText("layout default")
        self.electrode_pitch.setValue(0)
        self.electrode_pitch.setToolTip(
            "Centre-to-centre electrode spacing. 0 uses the layout's known "
            "pitch (200 µm for MCS 60MEA, 350 µm for Axion). Only needed for "
            "a custom array; the sorters' neighbourhoods are set from it.")

        self.sort_auto_merge = QCheckBox()
        self.sort_auto_merge.setToolTip(
            "Merge units the sorter split that look like one neuron "
            "(SpikeInterface's auto-merge on cross-correlograms and template "
            "similarity). Off by default: on the synthetic ground truth it "
            "did not improve either default sorter.")

        self.sort_censor = QDoubleSpinBox()
        self.sort_censor.setRange(0, 5)
        self.sort_censor.setDecimals(2)
        self.sort_censor.setSuffix(" ms")
        self.sort_censor.setValue(0.3)
        self.sort_censor.setToolTip(
            "Two spikes of one unit closer than this are one spike counted "
            "twice — a sorter resolving a burst can do that — so the second is "
            "dropped. Shorter than any real interval; 0 disables.")

        self.curation_min_snr = QDoubleSpinBox()
        self.curation_min_snr.setRange(0, 100)
        self.curation_min_snr.setDecimals(1)
        self.curation_min_snr.setValue(4.0)
        self.curation_min_snr.setToolTip(
            "A unit whose template peak is less than this many noise "
            "standard deviations is labelled noise and dropped.")

        self.curation_refractory = QDoubleSpinBox()
        self.curation_refractory.setRange(0.1, 20)
        self.curation_refractory.setDecimals(1)
        self.curation_refractory.setSuffix(" ms")
        self.curation_refractory.setValue(1.5)
        self.curation_refractory.setToolTip(
            "A neuron cannot fire twice within its refractory period, so "
            "intervals shorter than this are spikes from more than one neuron.")

        self.curation_max_rp = QDoubleSpinBox()
        self.curation_max_rp.setRange(0, 100)
        self.curation_max_rp.setDecimals(1)
        self.curation_max_rp.setSuffix(" %")
        self.curation_max_rp.setValue(5.0)
        self.curation_max_rp.setToolTip(
            "A unit with more than this share of its intervals inside the "
            "refractory period is labelled multi-unit (mua): real activity, "
            "but from more than one neuron. This is a fraction of the unit's "
            "own intervals, not the Poisson-normalised ratio some tools "
            "report, which is meaningless for bursting cultures.")

        self.curation_min_rate = QDoubleSpinBox()
        self.curation_min_rate.setRange(0, 100)
        self.curation_min_rate.setDecimals(2)
        self.curation_min_rate.setSuffix(" Hz")
        self.curation_min_rate.setValue(0.05)
        self.curation_min_rate.setToolTip(
            "Units firing more slowly than this are dropped — too few spikes "
            "to place in a network.")

        self.keep_good = QCheckBox("good")
        self.keep_good.setChecked(True)
        self.keep_mua = QCheckBox("multi-unit")
        self.keep_mua.setChecked(True)
        keep = QHBoxLayout()
        keep.addWidget(self.keep_good)
        keep.addWidget(self.keep_mua)
        keep.addStretch()
        self.keep_good.setToolTip(
            "Which curation labels become nodes. Keeping multi-unit clusters "
            "keeps the busiest electrodes in the network as a pooled node, "
            "as detection would; dropping them keeps only single neurons.")
        self.keep_mua.setToolTip(self.keep_good.toolTip())

        self.keep_sorter_output = QCheckBox()
        self.keep_sorter_output.setToolTip(
            "Keep the sorter's own output folder and the filtered copy of the "
            "recording it worked from, beside the spike file — for opening in "
            "Phy or a second look. Off because that copy is as large as the "
            "recording.")

        form6.addRow("Bandpass for sorting", band)
        form6.addRow("Common reference", self.sort_common_reference)
        form6.addRow("Electrode pitch", self.electrode_pitch)
        form6.addRow("Auto-merge split units", self.sort_auto_merge)
        form6.addRow("Drop duplicate spikes within", self.sort_censor)
        form6.addRow("Curation: min SNR", self.curation_min_snr)
        form6.addRow("Curation: refractory period", self.curation_refractory)
        form6.addRow("Curation: max refractory violations", self.curation_max_rp)
        form6.addRow("Curation: min firing rate", self.curation_min_rate)
        form6.addRow("Keep units labelled", keep)
        form6.addRow("Keep sorter output", self.keep_sorter_output)

        layout.addWidget(ctrl_box)
        layout.addWidget(self.sort_box)
        layout.addWidget(thr_box)
        layout.addWidget(wav_box)
        layout.addWidget(filt_box)
        layout.addWidget(tmpl_box)
        layout.addWidget(burst_box)
        layout.addStretch()
        self._on_spike_source_changed()

    def _on_spike_source_changed(self) -> None:
        sorting = self.spike_source.currentData() == "sort"
        self.sorter_name.setEnabled(sorting)
        self.sort_box.setVisible(sorting)
        if sorting_available():
            self.sorting_hint.setText(
                "The detector settings below are not used; every later step "
                "reads the sorted units." if sorting else "")

    def load(self, params: Params) -> None:
        self.detect_spikes.setChecked(params.detect_spikes)
        idx = self.spike_source.findData(params.spike_source)
        self.spike_source.setCurrentIndex(max(idx, 0))
        idx = self.sorter_name.findText(params.sorter_name)
        if idx < 0:
            self.sorter_name.addItem(params.sorter_name)
            idx = self.sorter_name.count() - 1
        self.sorter_name.setCurrentIndex(idx)
        self.sort_freq_min.setValue(params.sort_freq_min)
        self.sort_freq_max.setValue(params.sort_freq_max)
        idx = self.sort_common_reference.findData(params.sort_common_reference)
        self.sort_common_reference.setCurrentIndex(max(idx, 0))
        self.electrode_pitch.setValue(params.electrode_pitch_um or 0)
        self.sort_auto_merge.setChecked(params.sort_auto_merge)
        self.sort_censor.setValue(params.sort_censor_ms)
        self.curation_min_snr.setValue(params.curation_min_snr)
        self.curation_refractory.setValue(params.curation_refractory_ms)
        self.curation_max_rp.setValue(params.curation_max_rp_violation_frac * 100)
        self.curation_min_rate.setValue(params.curation_min_firing_rate)
        self.keep_good.setChecked("good" in params.curation_keep_labels)
        self.keep_mua.setChecked("mua" in params.curation_keep_labels)
        self.keep_sorter_output.setChecked(params.keep_sorter_output)
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
        self.wavelet_ref_period.setValue(params.wavelet_ref_period_ms or 0)
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
        params.spike_source = self.spike_source.currentData()
        params.sorter_name = self.sorter_name.currentText()
        params.sort_freq_min = self.sort_freq_min.value()
        params.sort_freq_max = self.sort_freq_max.value()
        params.sort_common_reference = self.sort_common_reference.currentData()
        params.electrode_pitch_um = self.electrode_pitch.value() or None
        params.sort_auto_merge = self.sort_auto_merge.isChecked()
        params.sort_censor_ms = self.sort_censor.value()
        params.curation_min_snr = self.curation_min_snr.value()
        params.curation_refractory_ms = self.curation_refractory.value()
        params.curation_max_rp_violation_frac = self.curation_max_rp.value() / 100
        params.curation_min_firing_rate = self.curation_min_rate.value()
        params.curation_keep_labels = [lab for lab, box in
                                       (("good", self.keep_good), ("mua", self.keep_mua))
                                       if box.isChecked()]
        params.keep_sorter_output = self.keep_sorter_output.isChecked()
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
        params.wavelet_ref_period_ms = self.wavelet_ref_period.value() or None
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
