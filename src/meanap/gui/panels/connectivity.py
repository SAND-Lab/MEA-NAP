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

        self._thr_box = thr_box
        layout.addWidget(sttc_box)
        layout.addWidget(adj_box)
        layout.addWidget(thr_box)
        layout.addStretch()

        self.set_timescale("lag")

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

    def save(self, params: Params) -> None:
        params.func_con_lag_val = self._parse_lags()
        params.adj_m_type = "binary" if self.binary_btn.isChecked() else "weighted"
        params.prob_thresh_rep_num = self.prob_thresh_rep_num.value()
        params.prob_thresh_tail = self.prob_thresh_tail.value()
        params.prob_thresh_plot_checks = self.prob_thresh_plot_checks.isChecked()
        params.prob_thresh_plot_checks_n = self.prob_thresh_plot_checks_n.value()
