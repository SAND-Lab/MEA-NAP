"""MEA-Sim's window: simulate a culture, then see what each metric makes of it.

Four tabs, in the order a demonstration runs:

1. **Explore** — one simulated culture: its raster, the planted graph, and
   the network each edge method recovers, with the metrics side by side.
2. **Line search** — move one dial over a range, everything else held, and
   plot every metric along it.
3. **Scorecard** — the line searches for every nuisance and two planted
   properties at once, as a metric × dial table of how far each moved.
4. **Pair tests** — Cutts & Eglen's necessary properties (N1–N6) on
   pairwise correlation measures.

The culture on the left is shared: it is what Explore simulates and the
starting point every line search holds fixed. Long runs happen on a worker
thread (line searches fan out to processes), with progress and a Stop.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from meanap.gui.figure_canvas import FigureCanvas
from meanap.native.output import NativeFigure
from meanap.sim import DISPLAY_NAME
from meanap.sim.measure import (
    DEFAULT_METHODS, DEFAULT_METRICS, EDGE_METHODS, METRICS, VIEW_METHODS, VIEWS, EdgeSettings,
    metric_label,
)
from meanap.sim.model import GRAPHS, SimSpec
from meanap.sim.pairs import PAIR_MEASURES, PROPERTIES, PairTestSettings
from meanap.sim.sweep import DIALS, SCORECARD_DIALS

__all__ = ["SimWindow", "PRESETS", "main"]

#: Starting cultures for a demonstration: each changes a few dials from the default.
PRESETS: dict[str, dict] = {
    "Quiet culture (independent Poisson + coupling)": {},
    "Bursty culture (network bursts)": {"burst_rate_hz": 0.15, "burst_spikes": 5.0},
    "Slow up/down states": {"state_amplitude": 0.8, "state_period_s": 30.0},
    "Stimulated culture": {"stim_interval_s": 2.0, "stim_response_frac": 0.5,
                           "stim_spikes": 2.0},
    "Excitation and inhibition": {"inhibitory_frac": 0.5, "inhibition": 0.8},
    "Regional bursts (co-activation with structure)": {
        "burst_rate_hz": 0.25, "burst_spikes": 5.0, "burst_scope": "regions",
        "burst_leak": 0.1, "coupling": 0.08},
    "Bursts that spread along connections": {
        "burst_rate_hz": 0.25, "burst_spikes": 4.0, "burst_scope": "propagate",
        "burst_participation": 0.4, "burst_leak": 0.1, "coupling": 0.03},
    "Inhibition hidden by bursts": {"inhibitory_frac": 0.5, "inhibition": 0.8,
                                    "burst_rate_hz": 0.15, "burst_spikes": 5.0},
    "No connections at all (null)": {"graph": "none", "burst_rate_hz": 0.1},
}

_INTRO = {
    "explore": (
        "<b>One simulated culture.</b> The planted graph is the answer; every other matrix is "
        "what one of MEA-NAP's edge methods recovers from the spikes. Bursts, slow states and "
        "stimulation are not connections — an edge method should not report them as edges."),
    "explore_coactivation": (
        "<b>One simulated culture.</b> Here correlation means being active together, so the "
        "answer is the true co-activation: how often each pair is active together, in "
        "network bursts and through their connections. Every other matrix is what one of MEA-NAP's edge methods recovers from "
        "the spikes; a good one shows the same blocks."),
    "sweep": (
        "<b>Line search.</b> Move one dial, hold everything else at the culture on the left "
        "(same planted graphs, same random seeds at every point), and plot each metric. "
        "A <i>nuisance</i> dial is not connectivity, so a good metric stays flat; a "
        "<i>signal</i> dial changes the planted network, so a good metric moves."),
    "score": (
        "<b>Scorecard.</b> Every line search at once: how many replicate SDs each dial moved "
        "each metric. Red on the left means the metric follows something that is not "
        "connectivity — a group difference in that metric could come from firing rate, "
        "recording length, bursts or slow states alone."),
    "match": (
        "<b>Match my data.</b> Pick a step-1 spike file; the simulator's dials are fitted so its "
        "firing rates, network bursts, slow states and mean STTC look like the recording. "
        "Check the comparison below — then every other tab runs on a culture like yours, "
        "with a known answer. Spikes cannot show <i>where</i> the connections are, so the "
        "graph shape, density and inhibition stay as set on the left. The recording is read "
        "on this computer only."),
    "pairs": (
        "<b>Cutts &amp; Eglen (2014), <i>J Neurosci</i> 34:14288.</b> Before comparing "
        "correlations across recordings, a pairwise measure must be symmetric (N1), robust "
        "to firing rate (N2) and to recording length (N3), bounded (N4), robust to small "
        "changes of Δt (N5), and tell anti-correlation from none (N6). Each is tested by "
        "line search on their Poisson spiking and bursting models."),
}


_ABOUT = [
    """<h2>MEA-Sim</h2>
<p>A network metric is only worth comparing between groups if it measures what it is named
after, not something that merely travels with it. Firing rate, recording length, network
bursts and slow shared activity all differ between cultures and ages, and each can move a
connectivity estimate on its own. Real recordings cannot pull those apart; a simulation can,
because it sets them one at a time and knows the answer.</p>
<p>Every number here comes from MEA-NAP's own code — the same STTC, nulls and step-4 network
metrics a run uses — applied to simulated spikes.</p>""",
    """<h3>The simulated culture</h3>
<ul>
<li><b>Background firing</b> — each electrode a Poisson process; rates spread log-normally,
so some electrodes are much busier than others.</li>
<li><b>Connections</b> (the planted graph) — a spike on one electrode makes a connected one
fire with a set probability a few ms later. Some connections can inhibit instead.</li>
<li><b>Network bursts</b> — moments when many electrodes fire together. They can come from
outside the recorded electrodes (the whole array, or one region at a time), or start at a
leader and spread along the connections.</li>
<li><b>Slow shared state</b> — the whole culture's rate drifting up and down over seconds.</li>
<li><b>Stimulation</b> — optional responses a fixed latency after each stimulus.</li>
</ul>""",
    """<h3>What counts as correlation?</h3>
<p>Two questions are asked of MEA data, and they have different right answers:</p>
<ul>
<li><b>Co-activation, including bursts</b> — are A and B active together, for whatever
reason? Network bursts are part of what is measured.</li>
<li><b>Beyond bursts</b> — is there correlation between A and B over and above the bursts
they share: the interval-jitter null (Amarasingham et al. 2012), or correlation within bursts
(Schroeter et al. 2015)? Bursts are a nuisance here.</li>
</ul>
<p>The difference is the <b>common input problem</b>. An MEA records a few hundred neurons of
tens of thousands, and a burst travels mostly through the ones no electrode sees. Two
electrodes can therefore fire together in every burst without any connection between them —
both are driven by the same unrecorded neurons. In a real culture the bursts themselves need
connections; what is missing is a connection <i>between the recorded electrodes</i>.</p>""",
    """<h3>Edge methods</h3>
<table cellspacing="0" cellpadding="4">
<tr><td><b>STTC, no threshold</b></td><td>every pair, weighted — co-activation</td></tr>
<tr><td><b>STTC + circular-shift null</b></td><td>MEA-NAP's default; shifting whole trains
breaks bursts apart, so shared bursts pass as edges — co-activation</td></tr>
<tr><td><b>STTC, strongest pairs only</b></td><td>a fixed share of pairs, so density cannot
change — co-activation</td></tr>
<tr><td><b>STTC + jitter null</b></td><td>spikes moved only within short windows, so bursts
stay in the null — beyond bursts</td></tr>
<tr><td><b>STTC above jitter expectation</b></td><td>STTC minus its average under the jitter
null, no threshold — beyond bursts</td></tr>
<tr><td><b>STTC outside bursts</b></td><td>burst periods (found from the spikes) cut out —
beyond bursts</td></tr>
<tr><td><b>STTC within bursts</b></td><td>burst periods only, end to end — in practice
mostly co-activation</td></tr>
<tr><td colspan="2"><br><i>From other papers — weighted networks, no threshold:</i></td></tr>
<tr><td><b>Pearson correlation of counts</b></td><td>spike counts in bins one lag wide (Cohen
&amp; Kohn 2011) — co-activation</td></tr>
<tr><td><b>Schreiber similarity</b></td><td>cosine between Gaussian-smoothed trains (Schreiber
et al. 2003); never 0 for independent trains, so it rises with rate — co-activation</td></tr>
<tr><td><b>Cross-correlation peak</b></td><td>cross-correlogram peak / √(N<sub>A</sub>N<sub>B</sub>),
as on MEAs by Pasquale et al. (2008); depends on rate and recording length —
co-activation</td></tr>
<tr><td><b>Partial correlation</b></td><td>each pair with every other recorded electrode held
fixed (Eichler et al. 2003; Poli et al. 2016) — beyond bursts, when the bursts reach the
recorded electrodes</td></tr>
<tr><td><b>Correlation beyond population rate</b></td><td>each pair with the summed activity
of all other electrodes held fixed (after Okun et al. 2015) — beyond bursts</td></tr>
<tr><td><b>Within-burst cross-covariance</b></td><td>1 ms bins inside each burst, peak over
±1–15 ms, after Schroeter et al. (2015) — beyond bursts</td></tr>
<tr><td><b>Transfer entropy</b></td><td>delayed, 1 ms binary bins, larger direction kept (Ito
et al. 2011; Nigam et al. 2016) — beyond bursts; the slowest</td></tr>
</table>""",
    """<h3>Reading the results</h3>
<p><b>Explore</b> shows one culture: the truth and what each method recovers.
<b>Line search</b> moves one setting with everything else fixed (same planted graphs and seeds
at every point). A <i>nuisance</i> setting is not what is being measured, so a good metric
stays flat; a <i>signal</i> setting changes it, so a good metric moves. Which is which
follows the choice of correlation on the left. <b>Scorecard</b> does every line search at
once and gives how far each setting moved each metric, in replicate standard deviations.
Replicates differ only in random draws, so real cultures vary more: a red cell is a possible
confound, not an effect size. <b>Pair tests</b> run Cutts &amp; Eglen's necessary properties
for a pairwise correlation measure. <b>Match my data</b> fits the settings to a recording so
the rest runs in its regime.</p>""",
    """<h3>What the model leaves out</h3>
<ul>
<li>It is a statistical model, not a biophysical one: no membranes, synapse dynamics or
plasticity. A metric that passes here can still fail on real data.</li>
<li>A connection is a fixed chance per spike (Cutts &amp; Eglen's "same structure, more
spikes"). If real connections add a fixed amount of synchrony instead, STTC itself would fall
with rate.</li>
<li>Bursts from outside have no internal order; spreading bursts do, but only along the
planted graph.</li>
<li>Fitted to real cultures, the spread of rates across electrodes comes out 15–40% too
small, and the fit says when a setting hits its limit.</li>
</ul>
<h3>References</h3>
<p>Cohen MR, Kohn A (2011) Measuring and interpreting neuronal correlations. <i>Nat
Neurosci</i> 14:811–819.<br>
Eichler M, Dahlhaus R, Sandkühler J (2003) Partial correlation analysis for the
identification of synaptic connections. <i>Biol Cybern</i> 89:289–302,
doi:10.1007/s00422-003-0400-3.<br>
Ito S, Hansen ME, Heiland R, Lumsdaine A, Litke AM, Beggs JM (2011) Extending transfer entropy
improves identification of effective connectivity in a spiking cortical network model.
<i>PLoS ONE</i> 6:e27431.<br>
Nigam S, Shimono M, Ito S, Yeh FC, Timme N, Myroshnychenko M, et al. (2016) Rich-club
organization in effective connectivity among cortical neurons. <i>J Neurosci</i>
36:670–684.<br>
Okun M, Steinmetz NA, Cossell L, et al. (2015) Diverse coupling of neurons to populations in
sensory cortex. <i>Nature</i> 521:511–515.<br>
Pasquale V, Massobrio P, Bologna LL, Chiappalone M, Martinoia S (2008) Self-organization and
neuronal avalanches in networks of dissociated cortical neurons. <i>Neuroscience</i>
153:1354–1369.<br>
Poli D, et al. (2016) From functional to structural connectivity using partial correlation in
neuronal assemblies. <i>J Neural Eng</i> 13.<br>
Schreiber S, Fellous JM, Whitmer D, Tiesinga P, Sejnowski TJ (2003) A new correlation-based
measure of spike timing reliability. <i>Neurocomputing</i> 52–54:925–931.<br>
Cutts CS, Eglen SJ (2014) Detecting pairwise correlations in spike trains: an objective
comparison of methods and application to the study of retinal waves. <i>J Neurosci</i>
34:14288–14303.<br>
Schroeter MS, Charlesworth P, Kitzbichler MG, Paulsen O, Bullmore ET (2015) Emergence of
rich-club topology and coordinated dynamics in development of hippocampal functional networks
in vitro. <i>J Neurosci</i> 35:5459–5470, doi:10.1523/JNEUROSCI.4259-14.2015.<br>
Amarasingham A, Harrison MT, Hatsopoulos NG, Geman S (2012) Conditional modeling and the
jitter method of spike resampling. <i>J Neurophysiol</i> 107, doi:10.1152/jn.00633.2011.</p>""",
]
#: The common-input schematic goes after this section.
_ABOUT_FIGURE_AFTER = 2


def _figure(chart) -> NativeFigure:
    from meanap.native.chart_paint import ChartPainter

    return NativeFigure("chart", chart, ChartPainter(chart))


def _intro(key: str) -> QLabel:
    lab = QLabel(_INTRO[key])
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.TextFormat.RichText)
    lab.setStyleSheet("padding: 6px 8px; background: palette(alternate-base); border-radius: 4px;")
    return lab


class _Task(QThread):
    """Runs ``fn(progress, cancelled)`` off the GUI thread."""

    progressed = pyqtSignal(int, int)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            out = self._fn(lambda i, n: self.progressed.emit(int(i), int(n)),
                           lambda: self._cancel)
        except Exception as e:   # shown to the user, never silently lost
            import traceback

            self.failed.emit(f"{e}\n\n{traceback.format_exc(limit=6)}")
            return
        self.done.emit(out)


def _run_sweeps(jobs: list[dict], progress, cancelled) -> pd.DataFrame:
    from meanap.pipeline.parallel import map_recordings
    from meanap.sim.sweep import run_job

    n_done = [0]

    def on_result(_rows):
        n_done[0] += 1
        progress(n_done[0], len(jobs))

    progress(0, len(jobs))
    rows = map_recordings(run_job, jobs, mem_per_task_gb=0.25, on_result=on_result,
                          cancel_check=cancelled)
    return pd.DataFrame([r for rr in rows for r in rr])


# ── the shared culture form ──────────────────────────────────────────────────


class _SpecForm(QWidget):
    """The simulated culture and the edge settings, shared by every tab."""

    #: field → (label, kind, low, high, step, decimals, tooltip)
    FIELDS = {
        "Network": [
            ("graph", "Planted graph", "graph", None, None, None, None,
             "Where the connections are. The number of connections is set by density."),
            ("n_nodes", "Nodes (electrodes)", "int", 4, 120, 1, 0, ""),
            ("density", "Density", "float", 0.0, 1.0, 0.01, 2,
             "Fraction of node pairs that are connected."),
            ("n_modules", "Modules", "int", 1, 10, 1, 0, "For 'Modules'."),
            ("within_module", "Share of edges in modules", "float", 0.0, 1.0, 0.05, 2,
             "For 'Modules': 1 = every edge inside a module."),
            ("n_hubs", "Hubs", "int", 0, 20, 1, 0, "For 'Hubs'."),
            ("coupling", "Coupling strength", "float", 0.0, 1.0, 0.01, 2,
             "Probability that a spike makes a connected node fire."),
            ("coupling_delay_ms", "Coupling delay (ms)", "float", 0.0, 50.0, 0.5, 1, ""),
            ("inhibitory_frac", "Share of edges that inhibit", "float", 0.0, 1.0, 0.05, 2,
             "Inhibitory edges delete the partner's spikes just after each spike."),
            ("inhibition", "Inhibition strength", "float", 0.0, 1.0, 0.05, 2,
             "Probability a partner's spike inside the window is deleted."),
            ("inhibition_ms", "Inhibition window (ms)", "float", 1.0, 500.0, 5.0, 0, ""),
        ],
        "Activity": [
            ("duration_s", "Recording length (s)", "float", 5.0, 3600.0, 10.0, 0, ""),
            ("rate_hz", "Firing rate (Hz)", "float", 0.01, 50.0, 0.1, 2,
             "Mean background rate per node, before coupling adds driven spikes."),
            ("rate_spread", "Rate spread (SD of log rate)", "float", 0.0, 2.0, 0.1, 2, ""),
        ],
        "Shared activity (not connections)": [
            ("burst_rate_hz", "Network bursts (/s)", "float", 0.0, 2.0, 0.01, 2,
             "Whole-culture bursts, unrelated to the planted graph."),
            ("burst_participation", "Nodes joining a burst", "float", 0.0, 1.0, 0.05, 2,
             "Spreading bursts: the chance a burst crosses each connection."),
            ("burst_spikes", "Spikes per node per burst", "float", 0.0, 30.0, 0.5, 1, ""),
            ("burst_width_ms", "Burst width (ms)", "float", 5.0, 2000.0, 10.0, 0, ""),
            ("burst_scope", "Bursts recruit", "choice:global=The whole array,"
             "regions=One region at a time,propagate=Along the connections", None, None, None,
             None,
             "Whole array or one region: bursts come from outside the recorded electrodes "
             "(common input). Along the connections: each burst starts at a leader and "
             "spreads through the planted graph."),
            ("burst_leak", "…and spill over", "float",
             0.0, 1.0, 0.05, 2,
             "Joining outside the burst's region, or (spreading bursts) through neurons no "
             "electrode records, relative to the burst participation."),
            ("burst_hop_ms", "Spread delay per connection (ms)", "float", 0.5, 200.0, 1.0, 1,
             "Spreading bursts: time to cross one planted connection (±50%)."),
            ("burst_leaders", "Burst leaders", "int", 1, 60, 1, 0,
             "Spreading bursts: how many electrodes bursts can start at."),
            ("burst_cluster_size", "Bursts per episode (1 = none)", "float", 1.0, 30.0, 0.5, 1,
             "Bursts that come in clusters, as in up-states; the overall burst rate is kept."),
            ("burst_cluster_s", "Episode length (s)", "float", 0.5, 120.0, 0.5, 1, ""),
            ("state_amplitude", "Slow state depth (log-SD)", "float", 0.0, 2.0, 0.05, 2,
             "Shared slow modulation of every node's rate and of how often bursts come: "
             "0.5 means rates swing by about ±50%."),
            ("state_period_s", "Slow state timescale (s)", "float", 1.0, 600.0, 5.0, 0,
             "How long an up or down state lasts, roughly."),
        ],
        "Stimulation": [
            ("stim_interval_s", "Stimulus every (s, 0 = off)", "float", 0.0, 60.0, 0.5, 1, ""),
            ("stim_response_frac", "Nodes that respond", "float", 0.0, 1.0, 0.05, 2, ""),
            ("stim_spikes", "Spikes per response", "float", 0.0, 20.0, 0.5, 1, ""),
            ("stim_latency_ms", "Response latency (ms)", "float", 0.0, 500.0, 1.0, 0, ""),
            ("stim_jitter_ms", "Latency jitter (ms)", "float", 0.0, 200.0, 0.5, 1, ""),
        ],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS))
        self.preset.setToolTip("Load a starting culture; every setting stays editable.")
        self.preset.currentTextChanged.connect(self._load_preset)
        lay.addWidget(QLabel("<b>What counts as correlation?</b>"))
        self.view = QComboBox()
        for k, v in VIEWS.items():
            self.view.addItem(v, k)
        self.view.setToolTip(
            "Co-activation: being active together for any reason, network bursts included, so "
            "a method should follow them.\nBeyond bursts: only the planted connections count, "
            "as with the jitter null or within-burst correlation (Schroeter et al. 2015); "
            "bursts are a nuisance.")
        self.view.setCurrentIndex(self.view.findData("coupling"))
        self.view.currentIndexChanged.connect(self._view_changed)
        lay.addWidget(self.view)
        self.view_note = QLabel("")
        self.view_note.setWordWrap(True)
        self.view_note.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(self.view_note)
        lay.addSpacing(6)
        lay.addWidget(QLabel("<b>Start from</b>"))
        lay.addWidget(self.preset)
        self._w: dict[str, QWidget] = {}
        for group, rows in self.FIELDS.items():
            box = QGroupBox(group)
            form = QFormLayout(box)
            for name, label, kind, lo, hi, step, dec, tip in rows:
                if kind == "graph":
                    w = QComboBox()
                    for k, v in GRAPHS.items():
                        w.addItem(v, k)
                elif kind.startswith("choice:"):
                    w = QComboBox()
                    for pair in kind[len("choice:"):].split(","):
                        k, v = pair.split("=", 1)
                        w.addItem(v, k)
                elif kind == "int":
                    w = QSpinBox()
                    w.setRange(int(lo), int(hi))
                else:
                    w = QDoubleSpinBox()
                    w.setRange(lo, hi)
                    w.setSingleStep(step)
                    w.setDecimals(dec)
                if tip:
                    w.setToolTip(tip)
                self._w[name] = w
                form.addRow(label, w)
            lay.addWidget(box)

        box = QGroupBox("Edges (as on the Connectivity tab)")
        form = QFormLayout(box)
        self.lag = QDoubleSpinBox()
        self.lag.setRange(0.5, 1000)
        self.lag.setDecimals(1)
        self.reps = QSpinBox()
        self.reps.setRange(20, 2000)
        self.reps.setSingleStep(20)
        self.tail = QDoubleSpinBox()
        self.tail.setRange(0.001, 0.5)
        self.tail.setDecimals(3)
        self.tail.setSingleStep(0.01)
        self.jitter = QDoubleSpinBox()
        self.jitter.setRange(1, 100)
        self.jitter.setDecimals(1)
        self.jitter.setToolTip("Each spike moves within a window this many lags long, as the "
                               "Connectivity tab's jitter null.")
        self.keep = QDoubleSpinBox()
        self.keep.setRange(0.01, 1.0)
        self.keep.setSingleStep(0.05)
        self.keep.setDecimals(2)
        form.addRow("STTC lag (ms)", self.lag)
        form.addRow("Surrogates", self.reps)
        form.addRow("Significance (tail)", self.tail)
        form.addRow("Jitter window (× lag)", self.jitter)
        form.addRow("'Strongest pairs' keeps", self.keep)
        self.methods: dict[str, QCheckBox] = {}
        for view, keys in VIEW_METHODS.items():
            form.addRow(QLabel(f"<i>for {VIEWS[view].split(' — ')[0].lower()}</i>"))
            for k in keys:
                cb = QCheckBox(EDGE_METHODS[k])
                self.methods[k] = cb
                form.addRow(cb)
        self.pad = QDoubleSpinBox()
        self.pad.setRange(0, 2000)
        self.pad.setDecimals(0)
        self.pad.setToolTip("Margin cut around each detected burst ('outside') or added to "
                            "it ('within').")
        form.addRow("Burst margin (ms)", self.pad)
        lay.addWidget(box)
        self.seed = QSpinBox()
        self.seed.setRange(1, 10 ** 6)
        f = QFormLayout()
        f.addRow("Seed", self.seed)
        lay.addLayout(f)
        lay.addStretch(1)
        self.set_spec(SimSpec())
        self.set_edges(EdgeSettings())
        self._view_changed()

    def current_view(self) -> str:
        return self.view.currentData()

    def _view_changed(self) -> None:
        view = self.current_view()
        for k, cb in self.methods.items():
            cb.setChecked(k in DEFAULT_METHODS[view])
        self.view_note.setText(
            "Bursts are part of what is measured: the truth is how often each pair is active "
            "together. "
            "Use a longer STTC lag (≈ 50–100 ms) to measure it."
            if view == "coactivation" else
            "Bursts are a nuisance: the truth is the planted connections alone.")

    def _load_preset(self, name: str) -> None:
        seed = self.seed.value()
        self.set_spec(SimSpec(**PRESETS.get(name, {})).with_(seed=seed))

    def set_spec(self, spec: SimSpec) -> None:
        for name, w in self._w.items():
            v = getattr(spec, name)
            if isinstance(w, QComboBox):
                w.setCurrentIndex(max(w.findData(v), 0))
            elif isinstance(w, QSpinBox):
                w.setValue(int(v))
            else:
                w.setValue(float(v))
        self.seed.setValue(int(spec.seed))

    def spec(self) -> SimSpec:
        vals = {}
        for name, w in self._w.items():
            if isinstance(w, QComboBox):
                vals[name] = w.currentData()
            else:
                vals[name] = w.value()
        return SimSpec(**vals, seed=self.seed.value())

    def set_edges(self, e: EdgeSettings) -> None:
        self.lag.setValue(e.lag_ms)
        self.reps.setValue(e.rep_num)
        self.tail.setValue(e.tail)
        self.jitter.setValue(e.jitter_lags)
        self.keep.setValue(e.keep_frac)
        self.pad.setValue(e.burst_pad_ms)

    def edges(self) -> EdgeSettings:
        return EdgeSettings(self.lag.value(), self.reps.value(), self.tail.value(),
                            self.jitter.value(), self.keep.value(), self.pad.value())

    def chosen_methods(self) -> list[str]:
        return [k for k in EDGE_METHODS if self.methods[k].isChecked()] or ["circular"]


def _metric_menu(button: QToolButton, chosen: set[str], changed) -> None:
    menu = QMenu(button)
    for k, label in METRICS.items():
        act = menu.addAction(label)
        act.setCheckable(True)
        act.setChecked(k in chosen)

        def toggled(on, k=k):
            (chosen.add if on else chosen.discard)(k)
            changed()
        act.toggled.connect(toggled)
    button.setMenu(menu)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)


def _ordered(chosen: set[str]) -> list[str]:
    return [k for k in METRICS if k in chosen]


class _RunBar(QWidget):
    """Run / Stop / progress / export, the same on every tab."""

    def __init__(self, run_text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.run = QPushButton(run_text)
        self.run.setDefault(True)
        self.stop = QPushButton("Stop")
        self.stop.setEnabled(False)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setMaximumWidth(260)
        self.status = QLabel("")
        self.export = QToolButton()
        self.export.setText("Export…")
        self.export.setEnabled(False)
        lay.addWidget(self.run)
        lay.addWidget(self.stop)
        lay.addWidget(self.bar)
        lay.addWidget(self.status, 1)
        lay.addWidget(self.export)

    def busy(self, on: bool) -> None:
        self.run.setEnabled(not on)
        self.stop.setEnabled(on)
        if on:
            self.bar.setRange(0, 0)
            self.status.setText("Working…")

    def progress(self, i: int, n: int) -> None:
        self.bar.setRange(0, max(n, 1))
        self.bar.setValue(i)
        self.bar.setFormat(f"{i} / {n}")


# ── the window ───────────────────────────────────────────────────────────────


class SimWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        from meanap.version import pipeline_version

        self.setWindowTitle(f"{DISPLAY_NAME} {pipeline_version('measim')} — simulated networks "
                            "with a known answer")
        self.resize(1500, 950)
        self._tasks: list[_Task] = []
        self.sweep_data: pd.DataFrame | None = None
        self.score_data: pd.DataFrame | None = None
        self.pair_results = None
        self.explored = None

        split = QSplitter(Qt.Orientation.Horizontal)
        self.form = _SpecForm()
        scroll = QScrollArea()
        scroll.setWidget(self.form)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(330)
        scroll.setMaximumWidth(430)
        split.addWidget(scroll)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._explore_tab(), "1 · Explore")
        self.tabs.addTab(self._sweep_tab(), "2 · Line search")
        self.tabs.addTab(self._score_tab(), "3 · Scorecard")
        self.tabs.addTab(self._pairs_tab(), "4 · Pair tests (Cutts && Eglen)")
        self.tabs.addTab(self._match_tab(), "5 · Match my data")
        self.tabs.addTab(self._about_tab(), "ⓘ About")
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.form.view.currentIndexChanged.connect(self._rescore)
        self.statusBar().showMessage(
            "Nothing here changes a recording. Match my data reads a spike file on this "
            "computer; every other tab runs on simulated data only.")

    def _rescore(self) -> None:
        """A change of view changes which dials are signal: re-judge what has run."""
        from meanap.sim.sweep import score

        if self.score_data is not None and not self.score_data.empty:
            self.score_table = score(self.score_data, self.form.current_view())
            self._redraw_score()
            self._redraw_score_curves()
        self._redraw_sweep()
        if self.explored is not None:
            self._show_explore(self.explored)
        self._dial_changed()
        self.ex_intro.setText(_INTRO["explore_coactivation" if self.form.current_view()
                                     == "coactivation" else "explore"])

    # ── running things ──

    def _start(self, bar: _RunBar, fn, done) -> _Task:
        task = _Task(fn, self)
        self._tasks.append(task)
        bar.busy(True)
        task.progressed.connect(bar.progress)

        def finished(out):
            bar.busy(False)
            bar.bar.setRange(0, 1)
            bar.bar.setValue(1)
            bar.status.setText("Stopped early — showing what finished." if task._cancel
                               else "Done.")
            done(out)

        def failed(msg):
            bar.busy(False)
            bar.status.setText("Failed.")
            QMessageBox.warning(self, DISPLAY_NAME, msg)

        task.done.connect(finished)
        task.failed.connect(failed)
        task.finished.connect(lambda: self._tasks.remove(task) if task in self._tasks else None)
        try:
            bar.stop.clicked.disconnect()
        except TypeError:
            pass
        bar.stop.clicked.connect(task.cancel)
        task.start()
        return task

    def closeEvent(self, event) -> None:
        for t in list(self._tasks):
            t.cancel()
            t.wait(30000)
        super().closeEvent(event)

    def _export_menu(self, bar: _RunBar, canvas: FigureCanvas, table) -> None:
        menu = QMenu(bar.export)
        menu.addAction("Figure (PNG / SVG / PDF)…", lambda: self._save_figure(canvas))
        menu.addAction("Numbers (CSV)…", lambda: self._save_csv(table()))
        bar.export.setMenu(menu)
        bar.export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def _save_figure(self, canvas: FigureCanvas) -> None:
        if canvas.painter is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save figure", "measim.png",
                                              "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if path:
            try:
                canvas.export(path)
            except OSError as e:
                QMessageBox.warning(self, DISPLAY_NAME, f"Could not save {path}:\n{e}")

    def _save_csv(self, df: pd.DataFrame | None) -> None:
        if df is None or df.empty:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save numbers", "measim.csv", "CSV (*.csv)")
        if path:
            try:
                df.to_csv(path, index=False)
            except OSError as e:
                QMessageBox.warning(self, DISPLAY_NAME, f"Could not save {path}:\n{e}")

    # ── 1 · explore ──

    def _explore_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ex_intro = _intro("explore")
        lay.addWidget(self.ex_intro)
        self.ex_bar = _RunBar("Simulate")
        self.ex_bar.run.clicked.connect(self.run_explore)
        lay.addWidget(self.ex_bar)
        split = QSplitter(Qt.Orientation.Vertical)
        self.ex_canvas = FigureCanvas()
        split.addWidget(self.ex_canvas)
        self.ex_table = QTableWidget()
        self.ex_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ex_table.verticalHeader().setVisible(False)
        split.addWidget(self.ex_table)
        split.setSizes([640, 260])
        lay.addWidget(split, 1)
        self._export_menu(self.ex_bar, self.ex_canvas, self._explore_frame)
        return w

    def run_explore(self) -> None:
        spec, edges, methods = self.form.spec(), self.form.edges(), self.form.chosen_methods()

        def work(progress, cancelled):
            from meanap.sim.measure import measure, planted_metrics
            from meanap.sim.model import simulate

            progress(0, 3)
            sim = simulate(spec)
            progress(1, 3)
            res = measure(sim, methods, edges, seed=spec.seed)
            progress(2, 3)
            planted = planted_metrics(sim, seed=spec.seed)
            progress(3, 3)
            return sim, res, planted

        self._start(self.ex_bar, work, self._show_explore)

    def _show_explore(self, out) -> None:
        from meanap.sim.charts import explore_chart

        sim, res, planted = out
        self.explored = out
        self.ex_canvas.show_figure(_figure(explore_chart(sim, res, view=self.form.current_view())))
        cols = ["planted"] + list(res)
        keys = [k for k in METRICS]
        self.ex_table.setColumnCount(1 + len(cols))
        self.ex_table.setRowCount(len(keys))
        self.ex_table.setHorizontalHeaderLabels(
            ["Metric", "Planted graph"] + [EDGE_METHODS[m] for m in res])
        for i, k in enumerate(keys):
            self.ex_table.setItem(i, 0, QTableWidgetItem(metric_label(k)))
            for j, c in enumerate(cols):
                v = planted.get(k, np.nan) if c == "planted" else res[c].metrics.get(k, np.nan)
                item = QTableWidgetItem("–" if not np.isfinite(v) else f"{v:.3g}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.ex_table.setItem(i, j + 1, item)
        self.ex_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rates = sim.rates_hz()
        self.ex_bar.status.setText(
            f"{sim.n} nodes, {int(sim.adjacency.sum() // 2)} planted edges, "
            f"mean rate {rates.mean():.2f} Hz (background {sim.spec.rate_hz:g} Hz + driven, "
            "burst and stimulus spikes)")
        self.ex_bar.export.setEnabled(True)

    def _explore_frame(self) -> pd.DataFrame | None:
        if self.explored is None:
            return None
        sim, res, planted = self.explored
        rows = [{"metric": k, "planted": planted.get(k, np.nan),
                 **{m: r.metrics.get(k, np.nan) for m, r in res.items()}} for k in METRICS]
        return pd.DataFrame(rows)

    # ── 2 · line search ──

    def _sweep_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_intro("sweep"))
        row = QHBoxLayout()
        self.dial = QComboBox()
        for k, d in DIALS.items():
            self.dial.addItem(d.label, k)
        self.lo, self.hi = QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.lo, self.hi):
            s.setRange(0, 1e5)
            s.setDecimals(3)
        self.steps = QSpinBox()
        self.steps.setRange(2, 20)
        self.steps.setValue(6)
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 50)
        self.repeats.setValue(4)
        self.dial.currentIndexChanged.connect(self._dial_changed)
        self.sweep_metrics = set(DEFAULT_METRICS)
        mbtn = QToolButton()
        mbtn.setText("Metrics…")
        _metric_menu(mbtn, self.sweep_metrics, self._redraw_sweep)
        for label, wid in (("Dial", self.dial), ("from", self.lo), ("to", self.hi),
                           ("points", self.steps), ("replicates", self.repeats)):
            row.addWidget(QLabel(label))
            row.addWidget(wid)
        row.addWidget(mbtn)
        row.addStretch(1)
        lay.addLayout(row)
        self.dial_note = QLabel("")
        self.dial_note.setWordWrap(True)
        lay.addWidget(self.dial_note)
        self.sw_bar = _RunBar("Run line search")
        self.sw_bar.run.clicked.connect(self.run_sweep)
        lay.addWidget(self.sw_bar)
        self.sw_canvas = FigureCanvas()
        lay.addWidget(self.sw_canvas, 1)
        self._export_menu(self.sw_bar, self.sw_canvas, lambda: self.sweep_data)
        self._dial_changed()
        return w

    def _dial_changed(self) -> None:
        d = DIALS[self.dial.currentData()]
        self.lo.setValue(d.low)
        self.hi.setValue(d.high)
        what = ("a <b>nuisance</b>: not what is being measured, so a good metric stays flat"
                if d.kind_for(self.form.current_view()) == "nuisance" else
                "a <b>signal</b>: it changes what is being measured, so a useful metric should move")
        crit = f" Network version of Cutts &amp; Eglen's {d.criterion}." if d.criterion else ""
        self.dial_note.setText(f"{d.label} is {what}.{crit}")

    def run_sweep(self) -> None:
        from meanap.sim.sweep import jobs_for, sweep_values

        dial = self.dial.currentData()
        values = sweep_values(DIALS[dial], self.lo.value(), self.hi.value(), self.steps.value())
        jobs = jobs_for(self.form.spec(), dial, values, self.repeats.value(),
                        self.form.chosen_methods(), self.form.edges(), metrics=list(METRICS))
        self._sweep_dial = dial
        self._start(self.sw_bar, lambda p, c: _run_sweeps(jobs, p, c), self._show_sweep)

    def _show_sweep(self, df: pd.DataFrame) -> None:
        self.sweep_data = df
        self._redraw_sweep()
        self.sw_bar.export.setEnabled(not df.empty)

    def _redraw_sweep(self) -> None:
        from meanap.sim.charts import sweep_chart
        from meanap.sim.sweep import score, summarise

        df = self.sweep_data
        if df is None or df.empty:
            return
        methods = [m for m in EDGE_METHODS if m in set(df["method"])]
        view = self.form.current_view()
        chart = sweep_chart(summarise(df), self._sweep_dial, _ordered(self.sweep_metrics),
                            methods, scores=score(df, view), view=view)
        self.sw_canvas.show_figure(_figure(chart))

    # ── 3 · scorecard ──

    def _score_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_intro("score"))
        row = QHBoxLayout()
        self.score_dials: dict[str, QCheckBox] = {}
        row.addWidget(QLabel("Dials:"))
        for k, d in DIALS.items():
            cb = QCheckBox(d.label)
            cb.setChecked(k in SCORECARD_DIALS)
            self.score_dials[k] = cb
        grid = QWidget()
        g = QHBoxLayout(grid)
        g.setContentsMargins(0, 0, 0, 0)
        for cb in self.score_dials.values():
            g.addWidget(cb)
        dial_scroll = QScrollArea()
        dial_scroll.setWidget(grid)
        dial_scroll.setWidgetResizable(True)
        dial_scroll.setFixedHeight(44)
        row.addWidget(dial_scroll, 1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        self.sc_steps = QSpinBox()
        self.sc_steps.setRange(2, 12)
        self.sc_steps.setValue(5)
        self.sc_reps = QSpinBox()
        self.sc_reps.setRange(1, 30)
        self.sc_reps.setValue(3)
        self.sc_method = QComboBox()
        self.sc_method.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.sc_method.currentIndexChanged.connect(self._redraw_score)
        self.sc_curves = QComboBox()
        self.sc_curves.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.sc_curves.currentIndexChanged.connect(self._redraw_score_curves)
        self.score_metrics = set(DEFAULT_METRICS)
        mbtn = QToolButton()
        mbtn.setText("Metrics…")
        _metric_menu(mbtn, self.score_metrics, self._redraw_score)
        for label, wid in (("points per dial", self.sc_steps), ("replicates", self.sc_reps),
                           ("  Show edge method", self.sc_method),
                           ("  Curves for", self.sc_curves)):
            row2.addWidget(QLabel(label))
            row2.addWidget(wid)
        row2.addWidget(mbtn)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.sc_bar = _RunBar("Run scorecard")
        self.sc_bar.run.clicked.connect(self.run_score)
        lay.addWidget(self.sc_bar)
        split = QSplitter(Qt.Orientation.Vertical)
        self.sc_canvas = FigureCanvas()
        self.sc_curve_canvas = FigureCanvas()
        split.addWidget(self.sc_canvas)
        split.addWidget(self.sc_curve_canvas)
        split.setSizes([520, 420])
        lay.addWidget(split, 1)
        self._export_menu(self.sc_bar, self.sc_canvas, lambda: self.score_table)
        self.score_table = None
        return w

    def run_score(self) -> None:
        from meanap.sim.sweep import jobs_for, sweep_values

        dials = [k for k, cb in self.score_dials.items() if cb.isChecked()]
        if not dials:
            return
        base, edges, methods = self.form.spec(), self.form.edges(), self.form.chosen_methods()
        jobs = []
        for d in dials:
            jobs += jobs_for(base, d, sweep_values(DIALS[d], steps=self.sc_steps.value()),
                             self.sc_reps.value(), methods, edges, metrics=list(METRICS))
        self._start(self.sc_bar, lambda p, c: _run_sweeps(jobs, p, c), self._show_score)

    def _show_score(self, df: pd.DataFrame) -> None:
        from meanap.sim.sweep import score

        self.score_data = df
        self.score_table = score(df, self.form.current_view()) if not df.empty else None
        with _blocked(self.sc_method), _blocked(self.sc_curves):
            self.sc_method.clear()
            for m in EDGE_METHODS:
                if not df.empty and m in set(df["method"]):
                    self.sc_method.addItem(EDGE_METHODS[m], m)
            self.sc_curves.clear()
            for d in DIALS:
                if not df.empty and d in set(df["dial"]):
                    self.sc_curves.addItem(DIALS[d].label, d)
        self._redraw_score()
        self._redraw_score_curves()
        self.sc_bar.export.setEnabled(self.score_table is not None)

    def _redraw_score(self) -> None:
        from meanap.sim.charts import scorecard_chart

        if self.score_table is None or self.sc_method.currentData() is None:
            return
        chart = scorecard_chart(self.score_table, self.sc_method.currentData(),
                                _ordered(self.score_metrics), view=self.form.current_view())
        self.sc_canvas.show_figure(_figure(chart))

    def _redraw_score_curves(self) -> None:
        from meanap.sim.charts import sweep_chart
        from meanap.sim.sweep import summarise

        df, dial = self.score_data, self.sc_curves.currentData()
        if df is None or df.empty or dial is None:
            return
        methods = [m for m in EDGE_METHODS if m in set(df["method"])]
        chart = sweep_chart(summarise(df), dial, _ordered(self.score_metrics), methods, ncols=6,
                            scores=self.score_table, view=self.form.current_view())
        self.sc_curve_canvas.show_figure(_figure(chart))

    # ── 5 · match my data ──

    def _match_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QLineEdit

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_intro("match"))
        row = QHBoxLayout()
        self.m_path = QLineEdit()
        self.m_path.setPlaceholderText("A step-1 spike file: …_spikes.npz or …_spikes.mat")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_spike_file)
        self.m_method = QComboBox()
        self.m_method.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.m_method.setToolTip("Which detection method's spikes to fit to.")
        row.addWidget(QLabel("Recording"))
        row.addWidget(self.m_path, 1)
        row.addWidget(browse)
        row.addWidget(QLabel("spikes from"))
        row.addWidget(self.m_method)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        self.m_min_rate = QDoubleSpinBox()
        self.m_min_rate.setRange(0.0, 10.0)
        self.m_min_rate.setSingleStep(0.05)
        self.m_min_rate.setValue(0.1)
        self.m_max_nodes = QSpinBox()
        self.m_max_nodes.setRange(5, 300)
        self.m_max_nodes.setValue(60)
        self.m_max_T = QDoubleSpinBox()
        self.m_max_T.setRange(30, 7200)
        self.m_max_T.setDecimals(0)
        self.m_max_T.setValue(600)
        for label, wid in (("active from (Hz)", self.m_min_rate), ("at most nodes", self.m_max_nodes),
                           ("at most seconds", self.m_max_T)):
            row2.addWidget(QLabel(label))
            row2.addWidget(wid)
        row2.addStretch(1)
        self.m_explore = QPushButton("Explore this culture →")
        self.m_explore.setEnabled(False)
        self.m_explore.clicked.connect(self._explore_fitted)
        row2.addWidget(self.m_explore)
        lay.addLayout(row2)
        self.m_bar = _RunBar("Fit to recording")
        self.m_bar.run.clicked.connect(self.run_match)
        lay.addWidget(self.m_bar)
        self.m_notes = QLabel("")
        self.m_notes.setWordWrap(True)
        lay.addWidget(self.m_notes)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.m_canvas = FigureCanvas()
        split.addWidget(self.m_canvas)
        self.m_table = QTableWidget()
        self.m_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.m_table.verticalHeader().setVisible(False)
        split.addWidget(self.m_table)
        split.setSizes([900, 420])
        lay.addWidget(split, 1)
        self._export_menu(self.m_bar, self.m_canvas, self._match_frame)
        self.fit = None
        return w

    def _pick_spike_file(self) -> None:
        start = self.m_path.text() or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a spike file", start,
            "Spike files (*_spikes.npz *_spikes.mat *.npz *.mat);;All files (*)")
        if path:
            self.set_spike_file(path)

    def set_spike_file(self, path: str) -> None:
        from meanap.pipeline.io import load_spike_file

        self.m_path.setText(path)
        self.m_method.clear()
        try:
            methods = load_spike_file(path).methods
        except Exception as e:
            self.m_bar.status.setText(f"Could not read that file: {e}")
            return
        for m in methods:
            self.m_method.addItem(m)
        if "bior1p5" in methods:
            self.m_method.setCurrentText("bior1p5")

    def run_match(self) -> None:
        from meanap.sim.fit import fit_to_file

        path = self.m_path.text().strip()
        if not path:
            self._pick_spike_file()
            path = self.m_path.text().strip()
            if not path:
                return
        base, lag = self.form.spec(), self.form.edges().lag_ms
        method = self.m_method.currentText() or None
        kw = dict(method=method, lag_ms=lag, min_rate_hz=self.m_min_rate.value(),
                  max_nodes=self.m_max_nodes.value(), max_duration_s=self.m_max_T.value())
        self._start(self.m_bar, lambda p, c: fit_to_file(path, base, progress=p, cancelled=c,
                                                          **kw), self._show_match)

    def _show_match(self, fit) -> None:
        from meanap.sim.charts import match_chart
        from meanap.sim.fit import STAT_LABELS

        self.fit = fit
        self.m_canvas.show_figure(_figure(match_chart(fit)))
        rows = list(STAT_LABELS.items())
        self.m_table.setColumnCount(3)
        self.m_table.setRowCount(len(rows))
        self.m_table.setHorizontalHeaderLabels(["", "Recording", "Simulation"])
        for i, (k, (label, fmt)) in enumerate(rows):
            self.m_table.setItem(i, 0, QTableWidgetItem(label))
            for j, st in enumerate((fit.data, fit.sim)):
                v = getattr(st, k)
                item = QTableWidgetItem(fmt.format(v) if np.isfinite(v) else "–")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.m_table.setItem(i, j + 1, item)
        h = self.m_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for j in (1, 2):
            h.setSectionResizeMode(j, QHeaderView.ResizeMode.ResizeToContents)
        self.form.set_spec(fit.spec.with_(seed=self.form.seed.value()))
        sp = fit.spec
        fitted = (f"Fitted: {sp.n_nodes} nodes, {sp.duration_s:g} s, background "
                  f"{sp.rate_hz:.2f} Hz (spread {sp.rate_spread:.2f}), bursts "
                  f"{sp.burst_rate_hz * 60:.1f}/min, slow state {sp.state_amplitude:.2f} over "
                  f"~{sp.state_period_s:.0f} s, coupling {sp.coupling:.2f}. "
                  "The culture on the left now holds these.")
        self.m_notes.setText(" ".join([fitted] + fit.notes))
        self.m_explore.setEnabled(True)
        self.m_bar.export.setEnabled(True)

    def _explore_fitted(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.run_explore()

    def _match_frame(self) -> pd.DataFrame | None:
        from meanap.sim.fit import STAT_LABELS

        if self.fit is None:
            return None
        rows = [{"statistic": label, "recording": getattr(self.fit.data, k),
                 "simulation": getattr(self.fit.sim, k)} for k, (label, _) in STAT_LABELS.items()]
        rows += [{"statistic": f"fitted {k}", "recording": np.nan, "simulation": v}
                 for k, v in self.fit.spec.to_dict().items() if isinstance(v, (int, float))]
        return pd.DataFrame(rows)

    # ── about ──

    def _about_tab(self) -> QWidget:
        from meanap.sim.charts import common_input_chart

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(18, 12, 18, 18)
        for i, html in enumerate(_ABOUT):
            lab = QLabel(html)
            lab.setWordWrap(True)
            lab.setTextFormat(Qt.TextFormat.RichText)
            lab.setOpenExternalLinks(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            lay.addWidget(lab)
            if i == _ABOUT_FIGURE_AFTER:
                self.about_canvas = FigureCanvas()
                self.about_canvas.setMinimumHeight(560)
                self.about_canvas.show_figure(_figure(common_input_chart()))
                lay.addWidget(self.about_canvas)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        return scroll

    # ── 4 · pair tests ──

    def _pairs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_intro("pairs"))
        row = QHBoxLayout()
        d = PairTestSettings()
        self.p_dt = QDoubleSpinBox()
        self.p_dt.setRange(0.5, 1000)
        self.p_dt.setValue(d.dt_ms)
        self.p_T = QDoubleSpinBox()
        self.p_T.setRange(10, 6000)
        self.p_T.setDecimals(0)
        self.p_T.setValue(d.duration_s)
        self.p_reps = QSpinBox()
        self.p_reps.setRange(2, 200)
        self.p_reps.setValue(d.repeats)
        self.p_share = QDoubleSpinBox()
        self.p_share.setRange(0.0, 1.0)
        self.p_share.setSingleStep(0.05)
        self.p_share.setValue(d.share_sync)
        self.p_tol = QDoubleSpinBox()
        self.p_tol.setRange(0.01, 2.0)
        self.p_tol.setSingleStep(0.05)
        self.p_tol.setValue(d.tolerance)
        self.p_tol.setToolTip("Largest relative change along a line search that still passes. "
                              "Cutts & Eglen judged by eye; this makes the judgement explicit.")
        for label, wid in (("Δt (ms)", self.p_dt), ("length (s)", self.p_T),
                           ("repeats", self.p_reps), ("share synchronous", self.p_share),
                           ("tolerance", self.p_tol)):
            row.addWidget(QLabel(label))
            row.addWidget(wid)
        row.addStretch(1)
        lay.addLayout(row)
        self.p_bar = _RunBar("Run pair tests")
        self.p_bar.run.clicked.connect(self.run_pairs)
        lay.addWidget(self.p_bar)
        split = QSplitter(Qt.Orientation.Vertical)
        self.p_canvas = FigureCanvas()
        split.addWidget(self.p_canvas)
        self.p_table = QTableWidget()
        self.p_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.p_table.verticalHeader().setVisible(False)
        split.addWidget(self.p_table)
        split.setSizes([620, 260])
        lay.addWidget(split, 1)
        self._export_menu(self.p_bar, self.p_canvas, self._pairs_frame)
        return w

    def run_pairs(self) -> None:
        from meanap.sim.pairs import run_all

        s = PairTestSettings(dt_ms=self.p_dt.value(), duration_s=self.p_T.value(),
                             repeats=self.p_reps.value(), share_sync=self.p_share.value(),
                             tolerance=self.p_tol.value(), seed=self.form.seed.value())
        self._start(self.p_bar, lambda p, c: run_all(s, progress=p), self._show_pairs)

    def _show_pairs(self, results) -> None:
        from meanap.sim.charts import pairs_chart

        self.pair_results = results
        self.p_canvas.show_figure(_figure(pairs_chart(results)))
        self.p_table.setColumnCount(4)
        self.p_table.setRowCount(len(results))
        self.p_table.setHorizontalHeaderLabels(["Property", "Measure", "Result", "What it did"])
        for i, r in enumerate(results):
            res = "–" if r.passed is None else ("pass" if r.passed else "fail")
            for j, v in enumerate((f"{r.prop} {PROPERTIES[r.prop]}", PAIR_MEASURES[r.measure],
                                   res, r.detail)):
                self.p_table.setItem(i, j, QTableWidgetItem(v))
        h = self.p_table.horizontalHeader()
        for j in range(3):
            h.setSectionResizeMode(j, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.p_bar.export.setEnabled(True)

    def _pairs_frame(self) -> pd.DataFrame | None:
        if not self.pair_results:
            return None
        return pd.DataFrame([{"property": r.prop, "name": PROPERTIES[r.prop],
                              "measure": r.measure, "passed": r.passed, "detail": r.detail}
                             for r in self.pair_results])


class _blocked:
    def __init__(self, w):
        self.w = w

    def __enter__(self):
        self._was = self.w.blockSignals(True)

    def __exit__(self, *exc):
        self.w.blockSignals(self._was)


def main(argv=None) -> None:
    """``meanap-sim``: MEA-Sim on its own."""
    import sys

    from meanap.gui import theme

    theme.enable_hi_dpi()
    app = QApplication.instance() or QApplication(sys.argv[:1] if argv is None else argv[:1])
    app.setApplicationName(DISPLAY_NAME)
    theme.apply(app)
    win = SimWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
