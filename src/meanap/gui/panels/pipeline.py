"""What one run of the pipeline does: which steps, and what it writes.

Only the settings. The Run button, the progress bar and the log live one level
up in :mod:`meanap.gui.panels.run`, which shares them with the queue — see that
module for why.
"""

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.panels.prior import PriorAnalysisPanel
from meanap.params import GENERATE_CSV_STEP, STATS_STEP, Params

PIPELINE_STEPS = [
    (1, "Spike detection"),
    (2, "Neuronal activity"),
    (3, "Functional connectivity"),
    (4, "Network analysis"),
]

#: The optional steps, as (key stored in ``Params.optional_steps_to_run``,
#: label, tooltip). A checkbox each rather than a multi-select list: the list
#: gave no hint that its rows were togglable, showed a selection that looked
#: like a highlight, and could not say what either row does.
OPTIONAL_STEPS = [
    (GENERATE_CSV_STEP, "Generate the spreadsheet from the raw data",
     "Before step 1, write the recording spreadsheet from the files in the "
     "raw data folder, so every name matches the data exactly. DIV is filled "
     "in wherever a name states it; the genotype/group column is yours.\n\n"
     "Whatever the spreadsheet already had is kept: DIVs and genotypes are "
     "carried across by name, so leaving this ticked never costs you the "
     "column you filled in by hand.\n\n"
     "The Data tab's Edit… button does the same thing interactively, and "
     "shows you the table before it is written."),
    (STATS_STEP, "Statistics and machine learning",
     "When the run finishes, carry straight on into step 5 against its "
     "output — the same analyses the Stats && ML tab runs, with whatever "
     "that tab is set to, logged here as they go.\n\n"
     "Applies to a single run started from this tab. A queued run does not "
     "pick it up."),
]
VERBOSE_LEVELS = ["Normal", "Verbose", "Debug"]


class PipelinePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Step overview ─────────────────────────────────────────────────────
        # First, because it is the legend for everything below it: the numbers
        # in "Pipeline steps" mean nothing until you know what step 3 is.
        overview_box = QGroupBox("Step overview")
        ov_layout = QVBoxLayout(overview_box)
        for num, name in PIPELINE_STEPS:
            ov_layout.addWidget(QLabel(f"  {num}. {name}"))

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
            "previous analysis folder instead of being recomputed. Results are written "
            "to this run's own output folder — the previous run is only ever read."
        )

        # The folders sit with the switch that turns them on, and appear only
        # when it is on: they cannot then be filled in and quietly do nothing,
        # and the tab is not carrying 150px of greyed-out fields for the runs —
        # most of them — that never resume from anything.
        self.prior = PriorAnalysisPanel()
        self.prior.setVisible(False)
        self.prior_analysis.toggled.connect(self.prior.setVisible)

        #: One checkbox per optional step, keyed by what goes into the params.
        self.optional_steps: dict[str, QCheckBox] = {}
        for key, _label, tip in OPTIONAL_STEPS:
            box = QCheckBox()
            box.setToolTip(tip)
            self.optional_steps[key] = box

        form.addRow("Start at step", self.start_step)
        form.addRow("Stop at step", self.stop_step)
        form.addRow("Use prior analysis", self.prior_analysis)
        form.addRow(self.prior)
        form.addRow("Continue previous run", self.continue_interrupted)
        form.addRow("   …and drop removed recordings' figures", self.prune_removed)

        optional = AdvancedSection()
        for key, label, _tip in OPTIONAL_STEPS:
            optional.form().addRow(label, self.optional_steps[key])
        form.addRow(optional)

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

        # Express mode changes what a run produces; the other three change how
        # it is logged, timed and seeded.
        form2.addRow("Express mode", self.express_mode)

        out_advanced = AdvancedSection()
        out_advanced.form().addRow("Verbose level", self.verbose_level)
        out_advanced.form().addRow("Time each step", self.time_processes)
        out_advanced.form().addRow("Fixed random seed", seed_row)
        form2.addRow(out_advanced)

        layout.addWidget(overview_box)
        layout.addWidget(step_box)
        layout.addWidget(out_box)
        layout.addStretch()

    def load(self, params: Params) -> None:
        self.start_step.setValue(params.start_analysis_step)
        self.stop_step.setValue(params.stop_analysis_step)
        self.prior_analysis.setChecked(params.prior_analysis)
        self.prior.setVisible(params.prior_analysis)
        self.prior.load(params)
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
        for key, box in self.optional_steps.items():
            box.setChecked(key in params.optional_steps_to_run)

    def save(self, params: Params) -> None:
        params.start_analysis_step = self.start_step.value()
        params.stop_analysis_step = self.stop_step.value()
        params.prior_analysis = self.prior_analysis.isChecked()
        self.prior.save(params)
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
            key for key, box in self.optional_steps.items() if box.isChecked()
        ]
