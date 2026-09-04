"""The Stats & ML tab: analysing a finished run.

This step differs from every other tab in what it acts on. The pipeline tabs
configure a run over *raw recordings*; this one reads a run that already
finished — a folder or a ``.meanap`` bundle, this session's or one from last
year — so the first thing the panel does is name what it would analyse and
describe the design it found there.

That description is the point of the top box. Whether a comparison is worth
believing turns on how many *cultures* the recordings came from, not how many
recordings there are, and the culture count is derived from the recording names
by a heuristic (:func:`meanap.stats.dataset.derive_culture_ids`) that can be
wrong. Printing "378 recordings from 121 cultures" before anything runs lets
that be checked rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

__all__ = ["StatsPanel"]

#: Preset effort levels. The step's cost is dominated by the permutation null
#: and the Shapley orderings, and both are accuracy-for-time trades, so they
#: are offered as one choice rather than as four spin boxes.
PRESETS = {
    "Quick look": dict(n_repeats=1, n_permutations=0, n_orderings=40,
                       importance_repeats=3, per_age_decoding=False,
                       shapley_orderings=20, shapley_max_features=10,
                       sweep_subsamples=5),
    "Standard": dict(n_repeats=5, n_permutations=200, n_orderings=200,
                     importance_repeats=10, per_age_decoding=True,
                     shapley_orderings=100, shapley_max_features=15,
                     sweep_subsamples=20),
    "Thorough": dict(n_repeats=10, n_permutations=1000, n_orderings=500,
                     importance_repeats=20, per_age_decoding=True,
                     shapley_orderings=300, shapley_max_features=20,
                     sweep_subsamples=40),
}


def has_adjacency(source: Path) -> bool:
    """Whether *source* carries the per-recording matrices the sweep needs.

    Every other analysis reads the metric CSVs, which any finished run has.
    The sweep reads ``ExperimentMatFiles``, which an older run — or one whose
    output folder was pruned — may not, and finding that out after twenty
    minutes of other analyses would be a poor way to learn it.
    """
    from meanap.pipeline.resume import ADJM_SUFFIX, CATNAP_SUFFIX

    source = Path(source)
    if source.is_dir():
        folder = source / "ExperimentMatFiles"
        return folder.is_dir() and any(
            folder.glob(f"*{suffix}") for suffix in (CATNAP_SUFFIX, ADJM_SUFFIX))
    try:
        import zipfile

        with zipfile.ZipFile(source) as archive:
            return any(name.startswith("ExperimentMatFiles/")
                       and name.endswith((CATNAP_SUFFIX, ADJM_SUFFIX))
                       for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


class StatsPanel(QWidget):
    """Configure and run the statistics and machine-learning step."""

    run_requested = pyqtSignal()
    open_folder_requested = pyqtSignal()
    choose_source_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: Path | None = None
        self._dest: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self._build_source_box())
        layout.addWidget(self._build_analyses_box())
        layout.addWidget(self._build_run_box())
        layout.addWidget(self._build_log_box(), stretch=1)

        self.set_source(None)

    # ── construction ─────────────────────────────────────────────────────────

    def _build_source_box(self) -> QWidget:
        box = QGroupBox("Run to analyse")
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        self.choose_btn = QPushButton("📂  Choose run…")
        self.choose_btn.setFixedHeight(36)
        self.choose_btn.setObjectName("secondary")
        self.choose_btn.setToolTip(
            "Pick a finished run's output folder, or a .meanap bundle. "
            "Defaults to this session's run when there is one.")
        self.choose_btn.clicked.connect(self.choose_source_requested)
        row.addWidget(self.choose_btn)
        row.addStretch(1)
        outer.addLayout(row)

        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_label.setStyleSheet("font-size: 11px; color: gray;")
        outer.addWidget(self.source_label)

        # The design summary: what the loader found, before anything is run.
        self.design_label = QLabel()
        self.design_label.setWordWrap(True)
        self.design_label.setStyleSheet("font-size: 11px;")
        outer.addWidget(self.design_label)
        return box

    def _build_analyses_box(self) -> QWidget:
        box = QGroupBox("Analyses")
        outer = QVBoxLayout(box)

        self.comparisons_cb = QCheckBox(
            "Compare groups and ages  (mixed models, per-age contrasts)")
        self.comparisons_cb.setChecked(True)
        self.comparisons_cb.setToolTip(
            "Per metric: an age slope and genotype contrasts from a mixed model "
            "with a random intercept per culture, group contrasts within each "
            "age, and paired age-to-age contrasts. All p-values FDR-corrected.")
        outer.addWidget(self.comparisons_cb)

        self.correlation_cb = QCheckBox(
            "Feature correlation structure  (clustered matrices, dimensionality)")
        self.correlation_cb.setChecked(True)
        self.correlation_cb.setToolTip(
            "How much of the metric set is measuring one thing: correlation "
            "matrices overall and per group × age, the redundant pairs, and the "
            "effective dimensionality of the feature space.")
        outer.addWidget(self.correlation_cb)

        self.decoding_cb = QCheckBox(
            "Decoding  (classify genotype or age from the features)")
        self.decoding_cb.setChecked(True)
        self.decoding_cb.setToolTip(
            "Cross-validated classification with whole cultures held out, so a "
            "culture never appears in both training and test. Includes a "
            "label-permutation null and held-out feature importance.")
        outer.addWidget(self.decoding_cb)

        # Nested under decoding, because that is what they attribute. Both
        # used to run unconditionally with no way to see or stop them, which
        # made a slow step slow for reasons the panel never mentioned.
        #
        # The nesting is done with a layout margin rather than by putting box
        # characters in the labels: at this font size a leading "└" renders as
        # an ambiguous mark that reads as a stray letter, and text should not
        # be doing layout's job in any case.
        nested = QVBoxLayout()
        nested.setContentsMargins(24, 0, 0, 0)
        nested.setSpacing(2)

        self.shapley_cb = QCheckBox(
            "per-age attribution  (which metrics carry the signal, and when)")
        self.shapley_cb.setChecked(True)
        self.shapley_cb.setToolTip(
            "Splits the decoding accuracy across features, separately within "
            "each age, and shows how those shares move with age. Adds a couple "
            "of minutes.")
        nested.addWidget(self.shapley_cb)

        self.families_cb = QCheckBox(
            "activity vs correlation strength vs network topology")
        self.families_cb.setChecked(True)
        self.families_cb.setToolTip(
            "The same split with whole families of features as the players, "
            "which answers whether an apparent difference in network "
            "organisation is more than a difference in firing and correlation. "
            "Exact and fast.")
        nested.addWidget(self.families_cb)
        outer.addLayout(nested)

        self.regression_cb = QCheckBox(
            "Variance attribution  (what explains age, and how much)")
        self.regression_cb.setChecked(True)
        self.regression_cb.setToolTip(
            "Predicts a continuous target from the features and partitions its "
            "R² across them, so each feature gets a share of explained variance "
            "rather than only a rank.")
        outer.addWidget(self.regression_cb)

        self.sweep_cb = QCheckBox(
            "Density sweep  (topology at matched density and network size)")
        self.sweep_cb.setChecked(False)
        self.sweep_cb.setToolTip(
            "Re-measures topology on networks thresholded to a common "
            "proportion of edges and subsampled to a common node count, so "
            "organisation can be compared without the connection density and "
            "network size that otherwise confound it.\n\n"
            "Needs the run's per-recording adjacency matrices, and is much "
            "slower than everything else here — tens of minutes on a few "
            "hundred recordings.")
        self.sweep_cb.toggled.connect(self._on_sweep_toggled)
        outer.addWidget(self.sweep_cb)

        self.measures_cb = QCheckBox(
            "Compare measures of activity  (does the measure change the answer?)")
        self.measures_cb.setChecked(True)
        self.measures_cb.setToolTip(
            "For a CAT-NAP run that analysed several measures of activity "
            "(calcium events, deconvolved trace, raw fluorescence, suite2p "
            "spikes): how far each metric moves when the measure changes, "
            "whether the recordings still rank the same way, and — the part "
            "that matters — whether the group and age effects survive the "
            "change.\n\n"
            "Free: it reads the per-measure results the analyses above already "
            "produced. A run with one measure has nothing to compare and skips "
            "it.")
        outer.addWidget(self.measures_cb)

        self.sweep_note = QLabel()
        self.sweep_note.setWordWrap(True)
        self.sweep_note.setStyleSheet(
            "font-size: 11px; color: gray; margin-left: 24px;")
        outer.addWidget(self.sweep_note)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)

        self.decode_target = QComboBox()
        self.decode_target.setEditable(False)
        self.decode_target.setToolTip(
            "What the classifier predicts. 'Automatic' uses genotype, or age "
            "when the run has only one genotype.")
        form.addRow("Classify:", self.decode_target)

        self.regress_target = QComboBox()
        self.regress_target.setEditable(False)
        self.regress_target.setToolTip(
            "What the regression predicts and partitions the variance of. "
            "Age by default; choosing a metric instead asks what explains "
            "that metric.")
        form.addRow("Explain:", self.regress_target)

        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS))
        self.preset.setCurrentText("Standard")
        self.preset.setToolTip(
            "How much cross-validation and how many permutations. Quick look "
            "skips the permutation null entirely; Thorough is worth it when a "
            "p-value near 0.005 has to be resolved.")
        form.addRow("Effort:", self.preset)

        self.sweep_size = QComboBox()
        self.sweep_size.addItem("Automatic  (recommended)", "auto")
        self.sweep_size.addItem("Off — control density only", None)
        self.sweep_size.setToolTip(
            "Whether the sweep also reduces every network to a common node "
            "count. Automatic picks a low percentile of this run's own counts. "
            "Leaving it off controls density but not size, and size is often "
            "the larger confound — recordings whose networks differ in node "
            "count are still not comparable.")
        form.addRow("Match size:", self.sweep_size)

        self.splits = QSpinBox()
        self.splits.setRange(2, 20)
        self.splits.setValue(5)
        self.splits.setToolTip(
            "Cross-validation folds. Capped automatically at the number of "
            "cultures in the smallest class.")
        form.addRow("CV folds:", self.splits)

        outer.addLayout(form)
        return box

    def _build_run_box(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)

        self.run_btn = QPushButton("📊  Run statistics")
        self.run_btn.setFixedHeight(40)
        self.run_btn.clicked.connect(self.run_requested)
        row.addWidget(self.run_btn)

        self.open_btn = QPushButton("📁  Open results folder")
        self.open_btn.setFixedHeight(40)
        self.open_btn.setObjectName("secondary")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_folder_requested)
        row.addWidget(self.open_btn)
        row.addStretch(1)
        return box

    def _build_log_box(self) -> QWidget:
        box = QGroupBox("Progress")
        outer = QVBoxLayout(box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: monospace; font-size: 11px;")
        outer.addWidget(self.log)
        return box

    # ── state ────────────────────────────────────────────────────────────────

    def set_source(self, source: Path | None) -> None:
        """Point the panel at a run, and describe what it found there.

        Loading the tables to describe them is cheap next to analysing them
        (they are CSVs of a few hundred rows), and it is the only way to fill
        the target lists with the metrics this particular run actually has.
        """
        self._source = Path(source) if source else None
        self.run_btn.setEnabled(self._source is not None)

        if self._source is None:
            self.source_label.setText(
                "No run chosen. Finish a run, or pick an output folder or "
                ".meanap bundle above.")
            self.design_label.setText("")
            self.sweep_cb.setEnabled(False)
            self.sweep_cb.setChecked(False)
            self.sweep_size.setEnabled(False)
            # Say why rather than leaving a greyed box with no explanation:
            # a disabled control with no reason beside it reads as broken.
            self.sweep_note.setText(
                "Unavailable until a run is chosen — it reads the "
                "per-recording adjacency matrices, not the metric tables.")
            self._fill_targets(None)
            return

        self.source_label.setText(f"Analysing: {self._source}")
        available = has_adjacency(self._source)
        self.sweep_cb.setEnabled(available)
        if not available:
            self.sweep_cb.setChecked(False)
        self.sweep_size.setEnabled(available and self.sweep_cb.isChecked())
        self._refresh_sweep_note()
        try:
            from meanap.stats.dataset import load_dataset

            ds = load_dataset(self._source)
        except Exception as exc:
            self.design_label.setText(f"⚠  Cannot read this run: {exc}")
            self.run_btn.setEnabled(False)
            self._fill_targets(None)
            return

        design = ds.describe()
        repeated = design["n_cultures"] < design["n_recordings"]
        note = (
            f"{design['n_recordings']} recordings from {design['n_cultures']} "
            f"cultures (median {design['recordings_per_culture_median']:.0f} "
            f"per culture) · {design['n_metrics']} metrics · "
            f"groups: {', '.join(design['groups'])} · "
            f"ages: {', '.join(f'{a:g}' for a in design['ages'])}"
        )
        if not repeated:
            note += ("\n⚠  Every recording maps to its own culture. Either this "
                     "run is cross-sectional, or the recording names do not "
                     "encode the culture in a form this can read — in which "
                     "case repeated measurements will be treated as independent.")
        self.design_label.setText(note)
        self._fill_targets(ds)

    def _on_sweep_toggled(self, checked: bool) -> None:
        # Also gated on the checkbox itself being available: a run with no
        # adjacency matrices must not offer to configure a sweep it cannot run.
        self.sweep_size.setEnabled(checked and self.sweep_cb.isEnabled())
        self._refresh_sweep_note()

    def _refresh_sweep_note(self) -> None:
        if not self.sweep_cb.isEnabled():
            self.sweep_note.setText(
                "Unavailable: this run has no ExperimentMatFiles, so the "
                "per-recording adjacency matrices the sweep needs are not "
                "there.")
        elif self.sweep_cb.isChecked():
            self.sweep_note.setText(
                "Slow — tens of minutes on a few hundred recordings, "
                "multiplied by the density grid and the number of node draws. "
                "Lower the effort preset to shorten it.")
        else:
            self.sweep_note.setText("")

    def _fill_targets(self, ds) -> None:
        """Repopulate the target lists from the run's own columns."""
        for combo, automatic in ((self.decode_target, "Automatic (genotype, or age)"),
                                 (self.regress_target, "Age (DIV)")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(automatic, None)
            combo.blockSignals(False)
        if ds is None:
            return
        if len(ds.groups) > 1:
            self.decode_target.addItem("Genotype / group", ds.group_col)
        if len(ds.ages) > 1:
            self.decode_target.addItem("Age (DIV)", ds.age_col)
        for metric in ds.metrics:
            self.regress_target.addItem(ds.label(metric), metric)

    def set_result(self, dest: Path | None) -> None:
        self._dest = Path(dest) if dest else None
        self.open_btn.setEnabled(self._dest is not None and self._dest.exists())

    def source(self) -> Path | None:
        return self._source

    def result_folder(self) -> Path | None:
        return self._dest

    def set_running(self, running: bool) -> None:
        self.run_btn.setEnabled(not running and self._source is not None)
        self.run_btn.setText("⏳  Running…" if running else "📊  Run statistics")
        self.choose_btn.setEnabled(not running)

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def clear_log(self) -> None:
        self.log.clear()

    # ── settings ─────────────────────────────────────────────────────────────

    def settings(self):
        """A :class:`~meanap.stats.run.StatsSettings` from the current widgets."""
        from meanap.stats.run import StatsSettings

        settings = StatsSettings(
            comparisons=self.comparisons_cb.isChecked(),
            correlation=self.correlation_cb.isChecked(),
            decoding=self.decoding_cb.isChecked(),
            regression=self.regression_cb.isChecked(),
            shapley_by_age=self.shapley_cb.isChecked(),
            feature_families=self.families_cb.isChecked(),
            density_sweep=self.sweep_cb.isChecked() and self.sweep_cb.isEnabled(),
            measure_comparison=self.measures_cb.isChecked(),
            sweep_n_nodes=self.sweep_size.currentData(),
            decoding_target=self.decode_target.currentData(),
            regression_target=self.regress_target.currentData(),
            n_splits=self.splits.value(),
        )
        for field, value in PRESETS[self.preset.currentText()].items():
            setattr(settings, field, value)
        return settings

    def choose_source_dialog(self) -> Path | None:
        """Ask for a folder or a bundle.

        Two dialogs rather than one, because Qt's file dialog cannot offer
        folders and files together: the folder chooser comes first since it is
        the common case, and cancelling it falls through to the file chooser.
        """
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a run output folder (cancel to pick a .meanap bundle)")
        if folder:
            return Path(folder)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a .meanap bundle", "", "MEA-NAP bundle (*.meanap)")
        return Path(path) if path else None
