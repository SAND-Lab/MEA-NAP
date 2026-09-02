"""Functional connectivity & thresholding settings panel."""

from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QRadioButton, QSpinBox, QVBoxLayout,
    QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.modes import DEFAULT_MODE, MODES
from meanap.gui.tooltip import set_tooltip
from meanap.params import Params


def _lag_text(lags) -> str:
    return ", ".join(str(int(v)) for v in lags)


class ConnectivityPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── STTC / lag ────────────────────────────────────────────────────────
        # Just the lags. Truncation was folded away here too, but it says how
        # much of each recording to read — a fact about the input, not about
        # the STTC — so it sits with the input folder on the Data tab.
        sttc_box = QGroupBox("Spike time tiling coefficient (STTC)")
        form = QFormLayout(sttc_box)

        self.lag_vals = QLineEdit(_lag_text(MODES[DEFAULT_MODE].default_lags))
        # Label, placeholder and tooltip are all set by set_timescale(), which
        # the window calls whenever the mode or the 2P activity type changes.
        self._sttc_box = sttc_box
        self._lag_label = QLabel()
        form.addRow(self._lag_label, self.lag_vals)

        # ── Adjacency matrix ──────────────────────────────────────────────────
        adj_box = QGroupBox("Adjacency matrix")
        adj_layout = QHBoxLayout(adj_box)

        self._adj_group = QButtonGroup(self)
        self.weighted_btn = QRadioButton("Weighted")
        self.binary_btn = QRadioButton("Binary")
        self.weighted_btn.setChecked(True)
        self._adj_group.addButton(self.weighted_btn)
        self._adj_group.addButton(self.binary_btn)

        adj_layout.addWidget(self.weighted_btn)
        adj_layout.addWidget(self.binary_btn)
        adj_layout.addStretch()

        # ── Probabilistic thresholding ────────────────────────────────────────
        thr_box = QGroupBox("Probabilistic thresholding")
        form2 = QFormLayout(thr_box)

        self.prob_thresh_rep_num = QSpinBox()
        self.prob_thresh_rep_num.setRange(10, 10000)
        self.prob_thresh_rep_num.setValue(200)

        self.prob_thresh_tail = QDoubleSpinBox()
        self.prob_thresh_tail.setRange(0.001, 0.5)
        self.prob_thresh_tail.setDecimals(3)
        self.prob_thresh_tail.setSingleStep(0.005)
        self.prob_thresh_tail.setValue(0.05)

        self.prob_thresh_plot_checks = QCheckBox()
        self.prob_thresh_plot_checks_n = QSpinBox()
        self.prob_thresh_plot_checks_n.setRange(1, 100)
        self.prob_thresh_plot_checks_n.setValue(5)

        # Iterations stays in the open: it is the one here that visibly costs
        # time, so it is worth seeing before starting a run.
        form2.addRow("Iterations", self.prob_thresh_rep_num)

        self.threshold_advanced = AdvancedSection()
        adv = self.threshold_advanced.form()
        adv.addRow("Tail percentile", self.prob_thresh_tail)
        adv.addRow("Plot random checks", self.prob_thresh_plot_checks)
        adv.addRow("Number of checks to plot", self.prob_thresh_plot_checks_n)
        form2.addRow(self.threshold_advanced)

        # ── Node and edge inclusion ───────────────────────────────────────────
        # What counts as a node, and what counts as an edge, before any metric
        # is computed. Its own box rather than a corner of "Network metrics"
        # because — unlike the two dimensionality switches below — both of
        # these are read by every pipeline and every activity type, CAT-NAP
        # included (``catnap/pipeline.py`` passes them straight through), so
        # the box must stay live in modes where that one goes quiet.
        inclusion_box = QGroupBox("Node and edge inclusion")
        form4 = QFormLayout(inclusion_box)

        self.min_activity_level = QDoubleSpinBox()
        self.min_activity_level.setRange(0.0, 1000.0)
        self.min_activity_level.setDecimals(4)
        self.min_activity_level.setSingleStep(0.005)
        self.min_activity_level.setValue(0.0)
        # Label text is set by set_pipeline(), which names the event the
        # running pipeline actually counts.
        self._min_activity_label = QLabel()

        self.exclude_edges_below_threshold = QCheckBox()
        self.exclude_edges_below_threshold.setChecked(True)
        set_tooltip(self.exclude_edges_below_threshold,
                    "Treat an edge that thresholding drove to zero as absent "
                    "rather than as a real edge of weight zero.\n\n"
                    "It changes the denominator of every mean taken over "
                    "edges — density, mean node degree and mean node strength "
                    "most visibly. On for MEA-NAP's whole history; switch it "
                    "off only to compare against something that counted "
                    "zero-weight edges.")

        form4.addRow(self._min_activity_label, self.min_activity_level)

        inclusion_advanced = AdvancedSection()
        inclusion_advanced.form().addRow("Exclude edges below threshold",
                                         self.exclude_edges_below_threshold)
        form4.addRow(inclusion_advanced)

        # ── Network metrics ───────────────────────────────────────────────────
        # Only the two dimensionality metrics live here, because they are the
        # only step-4 fields whose cost is worth a decision: together they are
        # roughly nine tenths of what step 4 computes, while every network
        # metric beside them is seconds. Everything else step 4 calculates is
        # cheap enough that choosing is not worth the risk of a missing column.
        metrics_box = QGroupBox("Network metrics")
        form3 = QFormLayout(metrics_box)

        self.compute_nmf = QCheckBox()
        self.compute_nmf.setChecked(True)
        set_tooltip(self.compute_nmf,
                    "NMF dimensionality metrics (num_nnmf_components, "
                    "nComponentsRelNS and the variance-explained curve).\n\n"
                    "By far the most expensive thing step 4 does — on a "
                    "64-channel 10-minute recording it is around 30s, against "
                    "3s for every network metric beside it — because it "
                    "factorises the activity matrix once per rank. Switch it "
                    "off and those columns are simply absent; nothing else "
                    "in the run changes.")

        self.compute_eff_rank = QCheckBox()
        self.compute_eff_rank.setChecked(True)
        set_tooltip(self.compute_eff_rank,
                    "Effective rank of the downsampled activity matrix "
                    "(effRank). A few seconds per recording — cheap next to "
                    "NMF, but the same kind of measure, so it can be left out "
                    "the same way.")

        form3.addRow("NMF dimensionality", self.compute_nmf)
        form3.addRow("Effective rank", self.compute_eff_rank)

        self._thr_box = thr_box
        self._metrics_box = metrics_box
        layout.addWidget(sttc_box)
        layout.addWidget(adj_box)
        layout.addWidget(thr_box)
        layout.addWidget(inclusion_box)
        layout.addWidget(metrics_box)
        layout.addStretch()

        self.set_timescale("lag")
        self.set_pipeline("meanap")

    def set_timescale(self, kind: str) -> None:
        """Name the timescale field for the measure that will actually run.

        ``"lag"`` is the STTC coincidence window; ``"bin"`` is the length of the
        bins a CAT-NAP correlation run averages traces into before correlating
        them. Same field, same units, genuinely different quantity — so the
        label says which, rather than leaving "Lag" over a box that sets bins.
        """
        binning = kind == "bin"
        if binning:
            self._sttc_box.setTitle("Correlation binning")
            self._lag_label.setText("Bin length (ms)")
            self.lag_vals.setPlaceholderText("Comma-separated bin lengths in ms")
            set_tooltip(self.lag_vals,
                        "Traces are averaged into bins this long, then "
                        "correlated between bins — one adjacency matrix (and "
                        "one set of network metrics) per bin length. Bins are "
                        "built from whole frames, so the run log reports what "
                        "each one rounded to.")
        else:
            self._sttc_box.setTitle("Spike time tiling coefficient (STTC)")
            self._lag_label.setText("Lag values (ms)")
            self.lag_vals.setPlaceholderText("Comma-separated lag values in ms")
            set_tooltip(self.lag_vals,
                        "STTC coincidence windows, one adjacency matrix (and "
                        "one set of network metrics) per lag. The right scale "
                        "depends on how fast the signal is: ~10-25 ms for "
                        "spikes, ~1-5 s for calcium, so these follow the mode "
                        "unless you set them yourself.")

        # Probabilistic thresholding is an STTC-only step: the correlation paths
        # return the raw correlation matrix, with no surrogates and no cutoff.
        # Leaving the settings live would let someone set an iteration count
        # that their run never reads.
        self._thr_box.setEnabled(not binning)
        self._thr_box.setTitle(
            "Probabilistic thresholding  ·  not used for correlation" if binning
            else "Probabilistic thresholding")
        set_tooltip(self._thr_box,
                    "Circular-shift surrogate thresholding applies to STTC "
                    "only. A correlation run keeps every edge of the "
                    "correlation matrix, so nothing here is read."
                    if binning else "")

    def set_pipeline(self, mode_key: str) -> None:
        """Say whether these settings belong to the pipeline about to run.

        The tab is shared, but the dimensionality switches are read only by
        the electrophysiology step 4: CAT-NAP keeps its own NMF checkbox on
        its tab (``Params.twop_nmf``, off by default) and always computes
        effective rank. Rather than show two controls for one metric, the box
        goes quiet in CAT-NAP mode and says where the switch actually is.

        The inclusion box beside it stays live in every mode — both of its
        settings are read on the CAT-NAP path too — but the threshold is a
        rate of *something*, and the something differs: spikes off an
        electrode, calcium events out of a cell. So the field is named for
        whichever the run will count.
        """
        catnap = mode_key == "catnap"
        unit = "events/s" if catnap else "spikes/s"
        self._min_activity_label.setText(f"Min activity level ({unit})")
        set_tooltip(self.min_activity_level,
                    f"Cells whose activity rate falls below this are left out "
                    f"of the network entirely: they are dropped from the "
                    f"adjacency matrix before any metric is computed, and "
                    f"their FRactive is NaN.\n\n"
                    f"Measured in {unit} over the whole recording. 0 keeps "
                    f"every cell that has at least one edge, which is the "
                    f"default; MEApipeline.m's own example runs use 0.01."
                    if catnap else
                    "Electrodes whose firing rate falls below this are left "
                    "out of the network entirely: they are dropped from the "
                    "adjacency matrix before any metric is computed, and "
                    "their FRactive is NaN.\n\n"
                    "Measured in spikes/s over the whole recording. 0 keeps "
                    "every electrode that has at least one edge, which is the "
                    "default; MEApipeline.m's own example runs use 0.01.")
        self._metrics_box.setEnabled(not catnap)
        self._metrics_box.setTitle(
            "Network metrics  ·  set on the CAT-NAP tab" if catnap
            else "Network metrics")
        set_tooltip(self._metrics_box,
                    "A CAT-NAP run takes its NMF setting from the CAT-NAP "
                    "tab, and always computes effective rank, so nothing here "
                    "is read." if catnap else "")

    def retune_lags_for_mode(self, from_mode: str, to_mode: str) -> tuple[int, ...] | None:
        """Move the lags onto *to_mode*'s defaults, unless they were edited.

        This tab is shared between the pipelines, but the lags that suit them
        are two orders of magnitude apart (see ``Mode.default_lags``), so
        carrying the ephys lags into CAT-NAP silently produces a run that
        finds almost no coincidences. The lags are also the field people most
        often set by hand, though, so only untouched defaults are swapped:
        anything typed survives the switch. Returns the new lags if it
        changed them, else None.
        """
        old = tuple(MODES[from_mode].default_lags)
        new = tuple(MODES[to_mode].default_lags)
        if old == new:
            return None
        try:
            current = tuple(self._parse_lags())
        except ValueError:
            return None  # mid-edit or malformed: not ours to overwrite
        if current != old:
            return None
        self.lag_vals.setText(_lag_text(new))
        return new

    def _parse_lags(self) -> list[int]:
        raw = self.lag_vals.text().strip()
        return [int(x) for x in raw.split(",") if x.strip()]

    def load(self, params: Params) -> None:
        self.lag_vals.setText(_lag_text(params.func_con_lag_val))
        if params.adj_m_type == "binary":
            self.binary_btn.setChecked(True)
        else:
            self.weighted_btn.setChecked(True)
        self.prob_thresh_rep_num.setValue(params.prob_thresh_rep_num)
        self.prob_thresh_tail.setValue(params.prob_thresh_tail)
        self.prob_thresh_plot_checks.setChecked(params.prob_thresh_plot_checks)
        self.prob_thresh_plot_checks_n.setValue(params.prob_thresh_plot_checks_n)
        self.min_activity_level.setValue(params.min_activity_level)
        self.exclude_edges_below_threshold.setChecked(
            params.exclude_edges_below_threshold)
        self.compute_nmf.setChecked(params.compute_nmf)
        self.compute_eff_rank.setChecked(params.compute_eff_rank)

    def save(self, params: Params) -> None:
        params.func_con_lag_val = self._parse_lags()
        params.adj_m_type = "binary" if self.binary_btn.isChecked() else "weighted"
        params.prob_thresh_rep_num = self.prob_thresh_rep_num.value()
        params.prob_thresh_tail = self.prob_thresh_tail.value()
        params.prob_thresh_plot_checks = self.prob_thresh_plot_checks.isChecked()
        params.prob_thresh_plot_checks_n = self.prob_thresh_plot_checks_n.value()
        params.min_activity_level = self.min_activity_level.value()
        params.exclude_edges_below_threshold = (
            self.exclude_edges_below_threshold.isChecked())
        params.compute_nmf = self.compute_nmf.isChecked()
        params.compute_eff_rank = self.compute_eff_rank.isChecked()
