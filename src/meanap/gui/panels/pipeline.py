"""Pipeline control panel — step selection, run/stop, progress, status log."""

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt

from meanap.params import Params
from meanap.pipeline.progress import Progress, format_bytes, format_duration

PIPELINE_STEPS = [
    (1, "Spike detection"),
    (2, "Neuronal activity"),
    (3, "Functional connectivity"),
    (4, "Network analysis"),
]

OPTIONAL_STEPS = ["generateCSV"]
VERBOSE_LEVELS = ["Normal", "Verbose", "Debug"]


class PipelinePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Kept so the end-of-run line can report the total without the caller
        # having to time the run itself.
        self._last_elapsed = 0.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Step selection ────────────────────────────────────────────────────
        step_box = QGroupBox("Pipeline steps")
        form = QFormLayout(step_box)

        self.start_step = QSpinBox()
        self.start_step.setRange(1, 4)
        self.start_step.setValue(1)
        self.start_step.setToolTip("Step to start from (1–4)")

        self.stop_step = QSpinBox()
        self.stop_step.setRange(1, 4)
        self.stop_step.setValue(4)
        self.stop_step.setToolTip("Step to stop at, inclusive (1–4)")

        self.start_step.valueChanged.connect(
            lambda v: self.stop_step.setValue(max(self.stop_step.value(), v))
        )
        self.stop_step.valueChanged.connect(
            lambda v: self.start_step.setValue(min(self.start_step.value(), v))
        )

        # Continuing is about *recordings*, where prior analysis is about
        # *steps* — two different questions that both mean "don't redo work",
        # so they sit together and each says what it skips.
        self.continue_interrupted = QCheckBox()
        self.continue_interrupted.setToolTip(
            "Pick up a run that stopped partway. Writes into the same output "
            "folder and skips any recording already finished, so a batch cut "
            "off at recording 5 of 10 carries on at 6.\n\n"
            "This is also how you add or remove recordings: edit the "
            "spreadsheet, tick this, and only the new ones are computed. "
            "Everything pooled across the batch — group comparisons, "
            "batch-scaled axes, cartography boundaries — is redone over "
            "whatever the spreadsheet now lists."
        )

        self.prune_removed = QCheckBox()
        self.prune_removed.setEnabled(False)
        self.prune_removed.setToolTip(
            "When continuing, delete the figures of recordings the spreadsheet "
            "no longer lists. They are left out of every CSV and pooled "
            "statistic either way, but their plots stay in the output folder "
            "and the report unless removed, looking like part of the "
            "analysis.\n\n"
            "Their data files are kept regardless, so putting a recording back "
            "stays cheap."
        )
        self.continue_interrupted.toggled.connect(self.prune_removed.setEnabled)

        self.prior_analysis = QCheckBox()
        self.prior_analysis.setToolTip(
            "Resume from an earlier run: steps before 'Start at step' are read from the "
            "previous analysis folder (set on the Paths tab) instead of being recomputed. "
            "Results are written to this run's own output folder — the previous run is "
            "only ever read."
        )

        self.optional_steps = QListWidget()
        self.optional_steps.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.optional_steps.setMaximumHeight(60)
        for s in OPTIONAL_STEPS:
            self.optional_steps.addItem(QListWidgetItem(s))

        form.addRow("Start at step", self.start_step)
        form.addRow("Stop at step", self.stop_step)
        form.addRow("Use prior analysis", self.prior_analysis)
        form.addRow("Continue previous run", self.continue_interrupted)
        form.addRow("   …and drop removed recordings' figures", self.prune_removed)
        form.addRow("Optional steps", self.optional_steps)

        # ── Step overview ─────────────────────────────────────────────────────
        overview_box = QGroupBox("Step overview")
        ov_layout = QVBoxLayout(overview_box)
        for num, name in PIPELINE_STEPS:
            ov_layout.addWidget(QLabel(f"  {num}. {name}"))

        # ── Output settings ───────────────────────────────────────────────────
        out_box = QGroupBox("Output")
        form2 = QFormLayout(out_box)

        self.verbose_level = QComboBox()
        self.verbose_level.addItems(VERBOSE_LEVELS)

        self.time_processes = QCheckBox()

        # Steps 3 and 4 are stochastic (surrogate thresholding, modularity, null
        # models, NMF). Off = a fresh seed per run, matching MATLAB; on = the
        # same inputs give the same numbers every time.
        self.use_random_seed = QCheckBox()
        self.use_random_seed.setToolTip(
            "Make the stochastic steps reproducible. Off: edge thresholding, modularity, "
            "small-worldness and NMF differ slightly between runs on the same data."
        )
        self.random_seed = QSpinBox()
        self.random_seed.setRange(0, 2_147_483_647)
        self.random_seed.setValue(1)
        self.random_seed.setEnabled(False)
        self.use_random_seed.toggled.connect(self.random_seed.setEnabled)

        seed_row = QWidget()
        seed_layout = QHBoxLayout(seed_row)
        seed_layout.setContentsMargins(0, 0, 0, 0)
        seed_layout.addWidget(self.use_random_seed)
        seed_layout.addWidget(self.random_seed)
        seed_layout.addStretch()

        # Express mode skips every figure that can be rebuilt from the run's
        # own data and writes one shareable .meanap bundle instead. The numbers
        # are identical either way — only the drawing is deferred.
        self.express_mode = QCheckBox()
        self.express_mode.setToolTip(
            "Skip figures that can be redrawn later and write a single small "
            ".meanap bundle instead. On the example dataset that turns 483 "
            "figures and 56 MB into 6 figures and 2.2 MB, and saves about a "
            "fifth of the run time. The numbers are identical either way — "
            "open the bundle with 'meanap-viewer' to draw any figure on demand, "
            "in PNG or editable SVG."
        )

        form2.addRow("Verbose level", self.verbose_level)
        form2.addRow("Time each step", self.time_processes)
        form2.addRow("Fixed random seed", seed_row)
        form2.addRow("Express mode", self.express_mode)

        # ── Run controls ──────────────────────────────────────────────────────
        run_box = QGroupBox("Run")
        run_layout = QHBoxLayout(run_box)

        self.test_btn = QPushButton("🧪  Test pipeline")
        self.test_btn.setFixedHeight(40)
        self.test_btn.setToolTip(
            "Download the example dataset and run the pipeline on it, "
            "to check your setup is working"
        )

        self.run_btn = QPushButton("▶  Run pipeline")
        self.run_btn.setFixedHeight(40)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)

        self.view_report_btn = QPushButton("🌐  View report")
        self.view_report_btn.setFixedHeight(40)
        self.view_report_btn.setToolTip(
            "Open the last run's results in your browser. A normal run gets an "
            "HTML report of the figures in the output folder; an express run "
            "opens its .meanap bundle in the viewer instead, which draws any "
            "figure on demand in PNG or editable SVG."
        )

        run_layout.addWidget(self.test_btn)
        run_layout.addWidget(self.run_btn)
        run_layout.addWidget(self.stop_btn)
        run_layout.addWidget(self.view_report_btn)

        # ── Progress ──────────────────────────────────────────────────────────
        # Hidden until a run starts: an empty bar sitting at 0% before anything
        # has been asked for reads as "stuck", not as "idle".
        self.progress_box = QGroupBox("Progress")
        progress_layout = QVBoxLayout(self.progress_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)  # per-mille, so the bar creeps
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(18)

        self.progress_label = QLabel("Waiting to start…")
        self.progress_label.setWordWrap(True)

        self.progress_eta = QLabel("")
        self.progress_eta.setStyleSheet("font-size: 11px; color: gray;")

        # Transfers get their own bar: during the first recording of a remote
        # run it is the only thing moving, and the estimate depends on it.
        # Deliberately slimmer than the run bar — two bars of equal weight
        # invite the reader to compare percentages that measure different things.
        self.transfer_bar = QProgressBar()
        self.transfer_bar.setRange(0, 1000)
        self.transfer_bar.setValue(0)
        self.transfer_bar.setTextVisible(False)
        self.transfer_bar.setFixedHeight(8)
        self.transfer_label = QLabel("")
        self.transfer_label.setStyleSheet("font-size: 11px; color: gray;")

        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_eta)
        progress_layout.addWidget(self.transfer_bar)
        progress_layout.addWidget(self.transfer_label)
        self.progress_box.setVisible(False)
        self._set_transfer_visible(False)

        # ── Status log ────────────────────────────────────────────────────────
        log_box = QGroupBox("Status log")
        log_layout = QVBoxLayout(log_box)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        log_layout.addWidget(self.log)

        layout.addWidget(step_box)
        layout.addWidget(overview_box)
        layout.addWidget(out_box)
        layout.addWidget(run_box)
        layout.addWidget(self.progress_box)
        layout.addWidget(log_box)
        layout.addStretch()

    def append_log(self, text: str) -> None:
        self.log.append(text)

    # ── Progress display ──────────────────────────────────────────────────────

    def _set_transfer_visible(self, visible: bool) -> None:
        self.transfer_bar.setVisible(visible)
        self.transfer_label.setVisible(visible)

    def start_progress(self) -> None:
        """Show an empty bar as a run begins."""
        self.progress_box.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting…")
        self.progress_eta.setText("")
        self.transfer_bar.setValue(0)
        self.transfer_label.setText("")
        self._set_transfer_visible(False)

    def show_progress(self, snapshot: Progress) -> None:
        """Render one snapshot from the running pipeline."""
        self.progress_box.setVisible(True)
        self.progress_bar.setValue(int(round(snapshot.fraction * 1000)))
        self._last_elapsed = snapshot.elapsed_s

        headline = f"{snapshot.percent}%  ·  {snapshot.phase}"
        if snapshot.detail:
            headline += f"  ·  {snapshot.detail}"
        self.progress_label.setText(headline)

        elapsed = format_duration(snapshot.elapsed_s)
        if snapshot.eta_s is None:
            # Saying "estimating" beats showing a number derived from a
            # benchmark machine before this one has finished anything.
            self.progress_eta.setText(f"{elapsed} elapsed  ·  estimating time left…")
        else:
            self.progress_eta.setText(
                f"{elapsed} elapsed  ·  about {format_duration(snapshot.eta_s)} left")

        self._set_transfer_visible(snapshot.transferring)
        if snapshot.transferring:
            share = min(1.0, snapshot.bytes_done / snapshot.bytes_total)
            self.transfer_bar.setValue(int(round(share * 1000)))
            text = (f"Downloaded {format_bytes(snapshot.bytes_done)} of "
                    f"{format_bytes(snapshot.bytes_total)}")
            if snapshot.transfer_detail:
                text += f"  ·  {snapshot.transfer_detail}"
            self.transfer_label.setText(text)

    def finish_progress(self, message: str) -> None:
        """Leave the bar showing how the run ended rather than blanking it."""
        self.progress_label.setText(message)
        self.progress_eta.setText(
            f"{format_duration(self._last_elapsed)} total"
            if self._last_elapsed else "")
        self._set_transfer_visible(False)

    def load(self, params: Params) -> None:
        self.start_step.setValue(params.start_analysis_step)
        self.stop_step.setValue(params.stop_analysis_step)
        self.prior_analysis.setChecked(params.prior_analysis)
        self.continue_interrupted.setChecked(params.continue_interrupted)
        self.prune_removed.setChecked(params.prune_removed_recordings)
        self.prune_removed.setEnabled(params.continue_interrupted)
        idx = self.verbose_level.findText(params.verbose_level)
        if idx >= 0:
            self.verbose_level.setCurrentIndex(idx)
        self.time_processes.setChecked(params.time_processes)
        self.express_mode.setChecked(params.express_mode)
        self.use_random_seed.setChecked(params.random_seed is not None)
        if params.random_seed is not None:
            self.random_seed.setValue(int(params.random_seed))
        for i in range(self.optional_steps.count()):
            item = self.optional_steps.item(i)
            item.setSelected(item.text() in params.optional_steps_to_run)

    def save(self, params: Params) -> None:
        params.start_analysis_step = self.start_step.value()
        params.stop_analysis_step = self.stop_step.value()
        params.prior_analysis = self.prior_analysis.isChecked()
        params.continue_interrupted = self.continue_interrupted.isChecked()
        # Only meaningful while continuing, and a stored True that silently
        # applied to a fresh run would delete figures nobody asked about.
        params.prune_removed_recordings = (
            self.prune_removed.isChecked() and self.continue_interrupted.isChecked())
        params.verbose_level = self.verbose_level.currentText()
        params.time_processes = self.time_processes.isChecked()
        params.express_mode = self.express_mode.isChecked()
        params.random_seed = (
            self.random_seed.value() if self.use_random_seed.isChecked() else None
        )
        params.optional_steps_to_run = [
            self.optional_steps.item(i).text()
            for i in range(self.optional_steps.count())
            if self.optional_steps.item(i).isSelected()
        ]
