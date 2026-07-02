"""Pipeline control panel — step selection, run/stop, status log."""

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt

from meanap.params import Params

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

        self.prior_analysis = QCheckBox()
        self.prior_analysis.setToolTip("Load results from a previous run instead of re-computing")

        self.optional_steps = QListWidget()
        self.optional_steps.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.optional_steps.setMaximumHeight(60)
        for s in OPTIONAL_STEPS:
            self.optional_steps.addItem(QListWidgetItem(s))

        form.addRow("Start at step", self.start_step)
        form.addRow("Stop at step", self.stop_step)
        form.addRow("Use prior analysis", self.prior_analysis)
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

        form2.addRow("Verbose level", self.verbose_level)
        form2.addRow("Time each step", self.time_processes)

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
            "Generate (or refresh) an HTML report of the output folder's "
            "plots and open it in your browser"
        )

        run_layout.addWidget(self.test_btn)
        run_layout.addWidget(self.run_btn)
        run_layout.addWidget(self.stop_btn)
        run_layout.addWidget(self.view_report_btn)

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
        layout.addWidget(log_box)
        layout.addStretch()

    def append_log(self, text: str) -> None:
        self.log.append(text)

    def load(self, params: Params) -> None:
        self.start_step.setValue(params.start_analysis_step)
        self.stop_step.setValue(params.stop_analysis_step)
        self.prior_analysis.setChecked(params.prior_analysis)
        idx = self.verbose_level.findText(params.verbose_level)
        if idx >= 0:
            self.verbose_level.setCurrentIndex(idx)
        self.time_processes.setChecked(params.time_processes)
        for i in range(self.optional_steps.count()):
            item = self.optional_steps.item(i)
            item.setSelected(item.text() in params.optional_steps_to_run)

    def save(self, params: Params) -> None:
        params.start_analysis_step = self.start_step.value()
        params.stop_analysis_step = self.stop_step.value()
        params.prior_analysis = self.prior_analysis.isChecked()
        params.verbose_level = self.verbose_level.currentText()
        params.time_processes = self.time_processes.isChecked()
        params.optional_steps_to_run = [
            self.optional_steps.item(i).text()
            for i in range(self.optional_steps.count())
            if self.optional_steps.item(i).isSelected()
        ]
