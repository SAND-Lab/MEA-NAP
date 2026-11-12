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

from meanap.gui.advanced import AdvancedSection
from meanap.gui.panels.paths import PathRow
from meanap.params import Params
from meanap.stim.events import EVENT_METHODS

_DETECTION_METHODS = [
    "longblank", "blanking", "absPosThreshold", "absNegThreshold",
    "stdNeg", "axionStimEvents", *EVENT_METHODS,
]
_CONDITION_MODES = (("All events one condition", "single"),
                    ("Alternate labels (e.g. ON, OFF)", "alternate"))
_NETWORK_NULLS = (("Trial shuffle — beyond shared stimulus drive", "trial_shuffle"),
                  ("Circular shift — total co-activity (step 3's test)", "circular"))
_NETWORK_STTC = (("Within each trial, averaged over trials", "trial_mean"),
                 ("Over all trial windows joined end to end", "pooled"))
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
        self.group_sequences = QCheckBox("Group pulses into sequences")
        self.group_sequences.setToolTip(
            "For temporal patterns (e.g. a left-to-right sweep and a right-to-left "
            "one): pulses on any electrodes that follow each other within the gap "
            "below are one stimulus, and stimuli with the same electrodes in the "
            "same order are one condition. Off: MATLAB's grouping, which joins "
            "electrodes pulsed at the same times and splits a sweep into one "
            "pattern per electrode. Name conditions with a StimConditions column "
            "in the spreadsheet, e.g. LtoR=12>13>14; RtoL=14>13>12.")
        self.sequence_gap = _dspin(0.1, 5000.0, 1, 50.0, " ms")
        self.sequence_gap.setToolTip(
            "Longest pause between two pulses of one stimulus. Must be longer than "
            "the delays within a sequence and shorter than the time between stimuli.")
        dform.addRow("", self.group_sequences)
        dform.addRow("Sequence gap", self.sequence_gap)
        self.group_sequences.toggled.connect(self.sequence_gap.setEnabled)
        self.sequence_gap.setEnabled(False)

        # ── Event-driven stimulation ──────────────────────────────────────────
        # Light, sound, anything logged as events rather than seen in the
        # voltage: shown instead of the voltage detection box for those methods.
        self.event_box = QGroupBox("Stimulus events (light, TTL, event log)")
        eform = QFormLayout(self.event_box)
        self.events_folder = PathRow(self)
        self.events_folder.setToolTip(
            "eventsCSV: where <recording>_events.csv is (columns time_s and, "
            "optionally, condition). maxwellTTL: where the MaxWell raw file is, "
            "if not in the raw data folder. Empty: the raw data folder.")
        self.ttl_rule = QLineEdit("auto")
        self.ttl_rule.setToolTip(
            "Which TTL changes are stimuli. auto: the rarest-changing bit (a "
            "projector frame sync toggles every frame; the stimulus marker is "
            "the rare one) — the run log says which it picked. Or rise:<bit>, "
            "fall:<bit>, value:<word>.")
        self.event_min_interval = _dspin(0.0, 60.0, 4, 0.05, " s")
        self.event_min_interval.setToolTip("Markers closer than this merge into one event.")
        self.condition_mode = QComboBox()
        for label, value in _CONDITION_MODES:
            self.condition_mode.addItem(label, value)
        self.condition_labels = QLineEdit()
        self.condition_labels.setPlaceholderText("ON, OFF")
        self.condition_labels.setToolTip(
            "Comma-separated condition names, in event order for 'alternate'. "
            "Nothing in a TTL marker says which transition is ON — check the "
            "stimulus protocol.")
        eform.addRow("Events folder", self.events_folder)
        eform.addRow("TTL rule", self.ttl_rule)
        eform.addRow("Conditions", self.condition_mode)
        eform.addRow("Condition labels", self.condition_labels)
        ev_advanced = AdvancedSection()
        ev_advanced.form().addRow("Merge events closer than", self.event_min_interval)
        eform.addRow(ev_advanced)

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
        self.drop_artifacts = QCheckBox("Spike detection drops detections in the stimulation blank")
        self.drop_artifacts.setToolTip(
            "The amplifier coming out of its blank looks like a spike to every detector, "
            "once per stimulus on every electrode. Ticked, step 1 drops detections from "
            "the blank's start to its end plus the ignore duration above (what this "
            "analysis always removes), so they stay out of the step-1 checks and steps 2-4.")
        an_advanced.form().addRow("", self.drop_artifacts)
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

        # ── Stimulus-triggered networks ───────────────────────────────────────
        net_box = AdvancedSection("Stimulus-triggered networks")
        nform = net_box.form()
        self.stim_network = QCheckBox("Evoked vs baseline networks and noise correlations")
        self.stim_network.setToolTip(
            "Per condition and lag: the STTC network of the windows after each "
            "event and of equally long windows before it, plus correlations of "
            "trial-by-trial spike counts. For electrical stimulation the evoked "
            "window starts after the blanked artifact and stimulating electrodes "
            "are left out.")
        self.trial_consistency = QCheckBox("Trial-by-trial consistency and drift")
        self.trial_consistency.setToolTip(
            "Per condition: each node's evoked − baseline response on every trial, "
            "its trend over trials, first-spike latency, and whether the response "
            "pattern of trials far apart is less alike than of trials close together "
            "(tested against shuffled trial order; the baseline window is the control).")
        self.split_half = QCheckBox("Split-half networks (odd/even, first/second half)")
        self.split_half.setToolTip(
            "Networks from half the trials each. Odd vs even trials: how reliable "
            "the network is. First vs second half: whether it changed over the "
            "recording. Agreement is the edge-weight correlation, with a Mantel test.")
        self.net_win_start = _dspin(-10.0, 10.0, 3, 0.0, " s")
        self.net_win_end = _dspin(0.001, 60.0, 3, 0.5, " s")
        self.post_auto = QCheckBox("Post-stimulus window: as long as the evoked one, right after it")
        self.post_auto.setChecked(True)
        self.post_auto.setToolTip(
            "A third network after the evoked window, for whether the network "
            "outlasts the stimulus (figure 16 draws all three on the array). Ticked: "
            "the same length as the evoked window and starting where it ends, so the "
            "three are comparable (STTC depends on window length). Unticked: the "
            "window set below, in seconds after the stimulus.")
        self.post_win_start = _dspin(0.0, 60.0, 3, 0.05, " s")
        self.post_win_end = _dspin(0.001, 60.0, 3, 0.1, " s")
        for w in (self.post_win_start, self.post_win_end):
            w.setEnabled(False)
            self.post_auto.toggled.connect(lambda on, w=w: w.setEnabled(not on))
        self.net_null = QComboBox()
        for label, value in _NETWORK_NULLS:
            self.net_null.addItem(label, value)
        self.net_sttc = QComboBox()
        for label, value in _NETWORK_STTC:
            self.net_sttc.addItem(label, value)
        self.net_sttc.setToolTip(
            "Within each trial: STTC is computed in each trial's window and averaged "
            "over the trials in which both nodes fired, so slow shared activity states "
            "do not pass for edges (needs the trial-shuffle test; a pair needs 5 such "
            "trials). Joined: one STTC over all the windows laid end to end.")
        self.net_reps = QSpinBox()
        self.net_reps.setRange(10, 100000)
        self.net_reps.setValue(200)
        self.net_alpha = _dspin(0.0001, 0.5, 4, 0.05)
        nform.addRow("", self.stim_network)
        nform.addRow("Evoked window start", self.net_win_start)
        nform.addRow("Evoked window end", self.net_win_end)
        nform.addRow("", self.post_auto)
        nform.addRow("Post window start", self.post_win_start)
        nform.addRow("Post window end", self.post_win_end)
        nform.addRow("STTC", self.net_sttc)
        nform.addRow("Edge test", self.net_null)
        nform.addRow("Surrogates", self.net_reps)
        nform.addRow("Alpha", self.net_alpha)
        nform.addRow("", self.trial_consistency)
        nform.addRow("", self.split_half)
        self.stim_group_plots = QCheckBox("Group comparisons by condition (half violins)")
        self.stim_group_plots.setToolTip(
            "The step-4 half violins of the stimulus networks, by group and DIV, "
            "with each stimulation condition as its own violin: the evoked - "
            "baseline change, the two epochs side by side, and split-half "
            "agreement and response summaries. Conditions are matched across "
            "recordings by electrodes or by the spreadsheet's StimConditions labels.")
        nform.addRow("", self.stim_group_plots)

        self._det_box = det_box
        for box in (mode_box, det_box, self.event_box, an_box, sig_box, net_box):
            layout.addWidget(box)
        layout.addStretch()

        self.method.currentTextChanged.connect(self._on_method_changed)
        self._on_method_changed(self.method.currentText())

    def _on_method_changed(self, method: str) -> None:
        """Only the Axion method uses the CSV field; event methods have no
        voltage to detect in and show their own settings instead."""
        self.axion_csv.setEnabled(method == "axionStimEvents")
        events = method in EVENT_METHODS
        self._det_box.setVisible(not events)
        self.event_box.setVisible(events)

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
        self.drop_artifacts.setChecked(params.stim_drop_artifact_spikes)
        self.raster_bin.setValue(params.stim_raster_bin_width)
        self.stim_dur_plot.setValue(params.stim_duration_for_plotting)
        self.n_shuffles.setValue(params.stim_n_shuffles)
        self.shuffle_alpha.setValue(params.stim_shuffle_alpha)
        self.events_folder.set_value(params.stim_events_folder)
        self.ttl_rule.setText(params.stim_event_ttl_rule)
        self.event_min_interval.setValue(params.stim_event_min_interval)
        idx = self.condition_mode.findData(params.stim_event_condition_mode)
        self.condition_mode.setCurrentIndex(max(idx, 0))
        self.condition_labels.setText(", ".join(params.stim_event_condition_labels))
        self.stim_network.setChecked(params.stim_network)
        nwin = params.stim_network_window or [0.0, 0.5]
        self.net_win_start.setValue(float(nwin[0]))
        self.net_win_end.setValue(float(nwin[1]))
        post = list(params.stim_network_post_window or [])
        self.post_auto.setChecked(not post)
        if post:
            self.post_win_start.setValue(float(post[0]))
            self.post_win_end.setValue(float(post[1]))
        idx = self.net_null.findData(params.stim_network_null)
        self.net_null.setCurrentIndex(max(idx, 0))
        idx = self.net_sttc.findData(params.stim_network_sttc)
        self.net_sttc.setCurrentIndex(max(idx, 0))
        self.net_reps.setValue(params.stim_network_rep_num)
        self.net_alpha.setValue(params.stim_network_alpha)
        self.trial_consistency.setChecked(params.stim_trial_consistency)
        self.split_half.setChecked(params.stim_split_half)
        self.stim_group_plots.setChecked(params.stim_group_plots)
        self.group_sequences.setChecked(params.stim_group_sequences)
        self.sequence_gap.setValue(params.stim_sequence_gap)
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
        params.stim_drop_artifact_spikes = self.drop_artifacts.isChecked()
        params.stim_raster_bin_width = self.raster_bin.value()
        params.stim_duration_for_plotting = self.stim_dur_plot.value()
        params.stim_n_shuffles = self.n_shuffles.value()
        params.stim_shuffle_alpha = self.shuffle_alpha.value()
        params.stim_events_folder = self.events_folder.value
        params.stim_event_ttl_rule = self.ttl_rule.text().strip() or "auto"
        params.stim_event_min_interval = self.event_min_interval.value()
        params.stim_event_condition_mode = self.condition_mode.currentData()
        params.stim_event_condition_labels = [s.strip() for s in self.condition_labels.text().split(",")
                                              if s.strip()]
        params.stim_network = self.stim_network.isChecked()
        params.stim_network_window = [self.net_win_start.value(), self.net_win_end.value()]
        params.stim_network_post_window = (
            [] if self.post_auto.isChecked()
            else [self.post_win_start.value(), self.post_win_end.value()])
        params.stim_network_null = self.net_null.currentData()
        params.stim_network_sttc = self.net_sttc.currentData()
        params.stim_network_rep_num = self.net_reps.value()
        params.stim_network_alpha = self.net_alpha.value()
        params.stim_trial_consistency = self.trial_consistency.isChecked()
        params.stim_split_half = self.split_half.isChecked()
        params.stim_group_plots = self.stim_group_plots.isChecked()
        params.stim_group_sequences = self.group_sequences.isChecked()
        params.stim_sequence_gap = self.sequence_gap.value()


def _dspin(lo: float, hi: float, decimals: int, val: float, suffix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(decimals)
    sb.setValue(val)
    if suffix:
        sb.setSuffix(suffix)
    return sb
