"""Match the simulator to a recording: "a culture like mine, with a known answer".

A line search is only informative in the regime the data live in: whether a
metric follows bursts matters a great deal for a culture that bursts every
few seconds and not at all for one that never does. So this module reads a
step-1 spike file and sets the simulator's dials to reproduce what can be
measured from spikes alone:

=====================  ==========================================  ===============
statistic (measured)   how                                          dial it sets
=====================  ==========================================  ===============
mean firing rate       spikes / s per active electrode              ``rate_hz``
rate spread            SD of log rate across electrodes             ``rate_spread``
network bursts         time bins where far more electrodes fire     ``burst_*``
                       than independent firing would make
slow shared state      count variance beyond Poisson in 5 s         ``state_amplitude``,
                       windows away from bursts; correlation time   ``state_period_s``
mean STTC              mean over pairs, at the run's lag            ``coupling``
=====================  ==========================================  ===============

The dials and the statistics are not one-to-one (coupling adds spikes, bursts
raise STTC), so the fit is moment matching by iteration: simulate, measure the
simulation with the same code as the data, scale each dial by how far its
statistic is off, repeat. The same seed is used every round, so the updates
see the dials' effect rather than new random draws.

What spikes alone cannot say is *where* the connections are: one coupling
strength spread over many edges and a stronger one over few give similar mean
STTC. The graph shape and density stay as set; only coupling is fitted. The
fit says so, and the comparison of the two summaries shows how good the
match is — it should be checked before trusting a line search run from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np

from meanap.sim.model import SimSpec, simulate

__all__ = [
    "ActivityStats", "FitResult", "describe", "detect_bursts", "load_trains", "fit_to_trains",
    "fit_to_file", "STAT_LABELS",
]

#: Rows of the data-vs-simulation table: field → (label, format).
STAT_LABELS = {
    "n_nodes": ("Active electrodes / units", "{:.0f}"),
    "duration_s": ("Length used (s)", "{:.0f}"),
    "mean_rate": ("Mean firing rate (Hz)", "{:.2f}"),
    "rate_spread": ("Rate spread (SD of log rate)", "{:.2f}"),
    "burst_rate": ("Network bursts (/min)", "{:.1f}"),
    "burst_participation": ("Electrodes joining a burst", "{:.0%}"),
    "burst_spikes": ("Spikes per electrode per burst", "{:.1f}"),
    "burst_width_ms": ("Burst width (ms)", "{:.0f}"),
    "burst_ibi_cv": ("Burst interval CV (1 = random)", "{:.2f}"),
    "frac_in_bursts": ("Spikes inside bursts", "{:.0%}"),
    "state_amplitude": ("Slow-state depth (CV, 5 s windows)", "{:.2f}"),
    "state_period_s": ("Slow-state timescale (s)", "{:.0f}"),
    "fano_100ms": ("Fano factor of the population, 100 ms", "{:.1f}"),
    "mean_sttc": ("Mean STTC", "{:.3f}"),
    "frac_negative": ("Pairs with negative STTC", "{:.0%}"),
    "sttc_p05": ("5th percentile of signed STTC", "{:+.3f}"),
}


@dataclass
class ActivityStats:
    n_nodes: int = 0
    duration_s: float = 0.0
    mean_rate: float = np.nan
    rate_spread: float = np.nan
    burst_rate: float = 0.0          # per minute
    burst_participation: float = np.nan
    burst_spikes: float = np.nan
    burst_width_ms: float = np.nan
    burst_ibi_cv: float = np.nan
    burst_short_ibi_s: float = np.nan   # median interval within clusters (for the fit)
    frac_in_bursts: float = 0.0
    state_amplitude: float = 0.0
    state_period_s: float = np.nan
    fano_100ms: float = np.nan
    mean_sttc: float = np.nan
    frac_negative: float = np.nan
    sttc_p05: float = np.nan
    # for the figures
    rates: np.ndarray = field(default_factory=lambda: np.empty(0))
    pop_rate: np.ndarray = field(default_factory=lambda: np.empty(0))   # Hz/node, 100 ms bins
    sttc: np.ndarray = field(default_factory=lambda: np.empty(0))       # signed, upper triangle

    def scalars(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)
                if f.name in STAT_LABELS}


@dataclass
class FitResult:
    spec: SimSpec
    data: ActivityStats
    sim: ActivityStats
    source: str
    history: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── measuring ────────────────────────────────────────────────────────────────


def detect_bursts(trains: list[np.ndarray], T: float, bin_s: float = 0.05,
                  min_frac: float = 0.3, z: float = 5.0) -> np.ndarray:
    """Network bursts as ``(start, end)`` rows: runs of bins where many more
    electrodes fire than independent firing at their own rates would give.

    The threshold is the larger of ``min_frac`` of the electrodes and ``z``
    SDs above the count expected by chance (a sum of Bernoullis), so a busy
    culture is not read as bursting merely for being busy.
    """
    n = len(trains)
    if n < 3 or T <= 0:
        return np.empty((0, 2))
    edges = np.arange(0.0, T + bin_s, bin_s)
    active = np.zeros(edges.size - 1)
    for t in trains:
        active += np.histogram(t, edges)[0] > 0
    rates = np.array([len(t) / T for t in trains])
    p = 1.0 - np.exp(-rates * bin_s)
    thr = max(3.0, min_frac * n, p.sum() + z * np.sqrt(np.sum(p * (1 - p))))
    on = active >= thr
    if not on.any():
        return np.empty((0, 2))
    d = np.diff(np.concatenate([[0], on.astype(int), [0]]))
    starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    # Merge runs one bin apart: one burst that dipped for a bin.
    out = []
    for s, e in zip(starts, ends):
        if out and s - out[-1][1] <= 1:
            out[-1][1] = e
        else:
            out.append([s, e])
    return np.array([[edges[s], edges[e]] for s, e in out])


def _slow_state(trains, T, bursts, margin_s: float = 0.5) -> tuple[float, float]:
    """(depth, timescale): CV of the rate in 5 s windows beyond Poisson, and the
    lag at which its autocorrelation (1 s bins) falls below 1/e — both counted
    away from bursts (each widened by *margin_s*, so burst tails stay out)."""
    win = 5.0
    if T < 4 * win:
        return 0.0, np.nan
    if bursts.size:
        bursts = np.column_stack([bursts[:, 0] - margin_s, bursts[:, 1] + margin_s])
    keep = [t if bursts.size == 0 else t[~_inside(t, bursts)] for t in trains]
    pooled = np.concatenate(keep) if keep else np.empty(0)
    edges = np.arange(0.0, T - win + 1e-9, win)
    counts = np.histogram(pooled, np.append(edges, edges[-1] + win))[0].astype(float)
    if bursts.size:   # scale bins that lost time to bursts back up
        lost = np.array([_overlap(bursts, a, a + win) for a in edges])
        frac = np.clip(1.0 - lost / win, 0.2, 1.0)
        counts = counts / frac
    m = counts.mean()
    if m <= 0:
        return 0.0, np.nan
    excess = max(counts.var() - m, 0.0)
    depth = float(np.sqrt(2.0 * excess) / m)        # a sine of amplitude A has SD A/√2
    one_edges = np.arange(0.0, T + 1.0, 1.0)
    one = np.histogram(pooled, one_edges)[0].astype(float)
    if bursts.size:
        lost = np.array([_overlap(bursts, a, a + 1.0) for a in one_edges[:-1]])
        ok = lost < 0.5
        one = np.where(ok, one / np.clip(1.0 - lost, 0.5, 1.0), np.nan)
    one = one - np.nanmean(one)
    var = np.nanmean(one * one)
    if not np.isfinite(var) or var <= 0:
        return depth, np.nan
    timescale = np.nan
    for lag in range(1, max(2, int(T // 4))):
        a, b = one[:-lag], one[lag:]
        both = np.isfinite(a) & np.isfinite(b)
        if both.sum() < 10:
            break
        if np.mean(a[both] * b[both]) / var < np.exp(-1.0):
            timescale = float(lag)
            break
    return depth, timescale


def _inside(t: np.ndarray, bursts: np.ndarray) -> np.ndarray:
    if bursts.size == 0 or t.size == 0:
        return np.zeros(t.size, bool)
    k = np.searchsorted(bursts[:, 0], t, "right") - 1
    ok = k >= 0
    out = np.zeros(t.size, bool)
    out[ok] = t[ok] < bursts[k[ok], 1]
    return out


def _overlap(bursts: np.ndarray, a: float, b: float) -> float:
    return float(np.clip(np.minimum(bursts[:, 1], b) - np.maximum(bursts[:, 0], a), 0, None).sum())


def describe(trains: list[np.ndarray], T: float, lag_ms: float = 10.0) -> ActivityStats:
    """Everything :func:`fit_to_trains` matches, measured the same way on any trains."""
    from meanap.pipeline.sttc import get_sttc

    n = len(trains)
    st = ActivityStats(n_nodes=n, duration_s=float(T))
    if n == 0 or T <= 0:
        return st
    rates = np.array([len(t) / T for t in trains])
    st.rates = np.sort(rates)[::-1]
    st.mean_rate = float(rates.mean())
    pos = rates[rates > 0]
    st.rate_spread = float(np.std(np.log(pos))) if pos.size > 1 else 0.0

    bursts = detect_bursts(trains, T)
    total = sum(len(t) for t in trains)
    if bursts.size:
        st.burst_rate = float(len(bursts) / T * 60.0)
        st.burst_width_ms = float(np.mean(bursts[:, 1] - bursts[:, 0]) * 1000.0)
        part, spk = [], []
        n_in = 0
        for a, b in bursts:
            c = np.array([np.searchsorted(t, b) - np.searchsorted(t, a) for t in trains])
            n_in += int(c.sum())
            joined = c > 0
            part.append(joined.mean())
            if joined.any():
                spk.append(float(np.mean(c[joined] - rates[joined] * (b - a))))
        st.burst_participation = float(np.mean(part))
        if len(bursts) >= 4:
            ibi = np.diff(bursts[:, 0])
            st.burst_ibi_cv = float(ibi.std() / ibi.mean()) if ibi.mean() > 0 else np.nan
            short = ibi[ibi < ibi.mean() / 2]
            st.burst_short_ibi_s = float(np.median(short)) if short.size else np.nan
        st.burst_spikes = float(max(np.mean(spk), 0.0)) if spk else np.nan
        st.frac_in_bursts = n_in / total if total else 0.0
    st.state_amplitude, st.state_period_s = _slow_state(trains, T, bursts)

    pooled = np.concatenate(trains) if trains else np.empty(0)
    c100 = np.histogram(pooled, np.arange(0.0, T + 0.1, 0.1))[0].astype(float)
    st.fano_100ms = float(c100.var() / c100.mean()) if c100.mean() > 0 else np.nan
    st.pop_rate = c100 / 0.1 / n

    s = get_sttc({i: t for i, t in enumerate(trains)}, n, lag_ms, T, clip=False)
    iu = np.triu_indices(n, 1)
    vals = s[iu]
    vals = vals[np.isfinite(vals)]
    st.sttc = vals
    if vals.size:
        st.mean_sttc = float(np.mean(np.clip(vals, 0, None)))   # as the pipeline sees it
        st.frac_negative = float(np.mean(vals < 0))
        st.sttc_p05 = float(np.percentile(vals, 5))
    return st


# ── loading ──────────────────────────────────────────────────────────────────


def load_trains(path: str | Path, method: str | None = None, *, min_rate_hz: float = 0.1,
                max_nodes: int = 60, max_duration_s: float = 600.0
                ) -> tuple[list[np.ndarray], float, str, list[str]]:
    """Active trains from a step-1 spike file: ``(trains, duration_s, label, notes)``."""
    from meanap.pipeline.io import load_spike_file

    f = load_spike_file(path)
    methods = f.methods
    if not methods:
        raise ValueError(f"{Path(path).name} holds no spike times.")
    if method is None:
        method = "bior1p5" if "bior1p5" in methods else methods[0]
    elif method not in methods:
        raise ValueError(f"{Path(path).name} has no '{method}' spikes; it has {', '.join(methods)}")
    trains = [np.sort(np.asarray(f.spike_times[c].get(method, np.empty(0)), float).ravel())
              for c in sorted(f.spike_times)]
    T = f.duration_s or max((t[-1] for t in trains if t.size), default=0.0)
    notes = []
    if T > max_duration_s:
        notes.append(f"Used the first {max_duration_s:g} s of {T:.0f} s.")
        T = float(max_duration_s)
        trains = [t[t < T] for t in trains]
    rates = np.array([len(t) / T for t in trains]) if T > 0 else np.zeros(len(trains))
    active = np.nonzero(rates >= min_rate_hz)[0]
    notes.append(f"{active.size} of {len(trains)} {'units' if f.sorted else 'electrodes'} "
                 f"fire at ≥ {min_rate_hz:g} Hz.")
    if active.size > max_nodes:
        order = active[np.argsort(rates[active])]
        pick = order[np.round(np.linspace(0, order.size - 1, max_nodes)).astype(int)]
        active = np.sort(pick)
        notes.append(f"Kept {max_nodes} of them, evenly across the rate range.")
    label = f"{Path(path).name} ({method})"
    return [trains[i] for i in active], float(T), label, notes


# ── fitting ──────────────────────────────────────────────────────────────────


def _initial(data: ActivityStats, base: SimSpec) -> SimSpec:
    burst = data.burst_rate > 0
    background = data.mean_rate * (1.0 - data.frac_in_bursts)
    return base.with_(
        n_nodes=int(data.n_nodes), duration_s=float(round(data.duration_s)),
        rate_hz=float(max(background, 0.01)),
        rate_spread=float(np.clip(data.rate_spread, 0.0, 2.0)),
        burst_rate_hz=float(data.burst_rate / 60.0) if burst else 0.0,
        burst_participation=float(np.clip(data.burst_participation, 0.05, 1.0)) if burst
        else base.burst_participation,
        burst_spikes=float(max(data.burst_spikes, 0.5)) if burst else base.burst_spikes,
        burst_width_ms=float(np.clip(data.burst_width_ms * 1.5, 20, 2000)) if burst
        else base.burst_width_ms,
        # A clustered process has CV² ≈ 1 + (bursts per episode − 1).
        burst_cluster_size=float(np.clip(data.burst_ibi_cv ** 2, 1.0, 30.0))
        if burst and np.isfinite(data.burst_ibi_cv) else 1.0,
        burst_cluster_s=float(np.clip(max(data.burst_ibi_cv ** 2, 1.0)
                                      * data.burst_short_ibi_s, 0.5, 120.0))
        if burst and np.isfinite(data.burst_short_ibi_s) and np.isfinite(data.burst_ibi_cv)
        else base.burst_cluster_s,
        state_amplitude=float(np.sqrt(np.log1p(min(data.state_amplitude, 4.0) ** 2))),
        state_period_s=float(np.clip(data.state_period_s, 2.0, 600.0))
        if np.isfinite(data.state_period_s) else base.state_period_s,
        stim_interval_s=0.0,
    )


#: Statistics the fit matches, scored as squared log-ratios (sim / data).
_MATCHED = ("mean_rate", "rate_spread", "burst_rate", "burst_participation", "burst_spikes",
            "burst_width_ms", "burst_ibi_cv", "state_amplitude", "mean_sttc")


def _loss(data: ActivityStats, sim: ActivityStats) -> float:
    total = 0.0
    for k in _MATCHED:
        d, s = getattr(data, k), getattr(sim, k)
        if np.isfinite(d) and d > 0.02:
            total += np.log(max(s, 1e-3) / d) ** 2 if np.isfinite(s) else 4.0
    return float(total)


def _ratio(target: float, got: float, power: float = 0.6) -> float:
    if not (np.isfinite(target) and np.isfinite(got)) or got <= 0 or target <= 0:
        return 1.0
    return float(np.clip((target / got) ** power, 0.33, 3.0))


def fit_to_trains(trains: list[np.ndarray], T: float, base: SimSpec | None = None, *,
                  lag_ms: float = 10.0, rounds: int = 15, source: str = "recording",
                  notes: list[str] | None = None, progress=None, cancelled=None) -> FitResult:
    """Fit the simulator's dials to *trains* (see the module docstring)."""
    base = base or SimSpec()
    data = describe(trains, T, lag_ms)
    spec = _initial(data, base)
    history = []
    sim_stats = None
    best = None          # (loss, spec, stats): rounds can overshoot, so keep the best
    for r in range(int(rounds)):
        if cancelled is not None and cancelled():
            break
        sim_stats = describe(simulate(spec).trains, spec.duration_s, lag_ms)
        loss = _loss(data, sim_stats)
        if best is None or loss < best[0]:
            best = (loss, spec, sim_stats)
        history.append({"round": r, "loss": loss, **{k: getattr(spec, k) for k in (
            "rate_hz", "rate_spread", "burst_rate_hz", "burst_participation", "burst_spikes",
            "burst_width_ms", "burst_cluster_size", "burst_cluster_s", "state_amplitude",
            "coupling")},
            "sim_rate": sim_stats.mean_rate, "sim_sttc": sim_stats.mean_sttc})
        if progress is not None:
            progress(r + 1, rounds)
        if r == rounds - 1:
            break
        upd = {
            "rate_hz": max(spec.rate_hz * _ratio(data.mean_rate, sim_stats.mean_rate), 0.01),
            "rate_spread": float(np.clip(spec.rate_spread
                                         + 0.8 * (data.rate_spread - sim_stats.rate_spread),
                                         0.0, 2.0)),
            "coupling": float(np.clip(max(spec.coupling, 0.01)
                                      * _ratio(data.mean_sttc, sim_stats.mean_sttc), 0.0, 0.9)),
        }
        if data.burst_rate > 0:
            upd["burst_rate_hz"] = spec.burst_rate_hz * _ratio(data.burst_rate,
                                                               sim_stats.burst_rate)
            upd["burst_participation"] = float(np.clip(
                spec.burst_participation * _ratio(data.burst_participation,
                                                  sim_stats.burst_participation), 0.05, 1.0))
            upd["burst_spikes"] = spec.burst_spikes * _ratio(data.burst_spikes,
                                                             sim_stats.burst_spikes)
            upd["burst_width_ms"] = float(np.clip(
                spec.burst_width_ms * _ratio(data.burst_width_ms, sim_stats.burst_width_ms),
                10.0, 3000.0))
            if np.isfinite(data.burst_ibi_cv) and data.burst_ibi_cv > 1.1:
                # Clustering shows as CV above 1; match the excess.
                upd["burst_cluster_size"] = float(np.clip(
                    max(spec.burst_cluster_size, 1.2)
                    * _ratio(data.burst_ibi_cv - 0.9, max(sim_stats.burst_ibi_cv - 0.9, 0.05),
                             1.0), 1.0, 30.0))
                upd["burst_cluster_s"] = float(np.clip(
                    spec.burst_cluster_s * _ratio(data.burst_short_ibi_s,
                                                  sim_stats.burst_short_ibi_s), 0.5, 120.0))
            else:
                upd["burst_cluster_size"] = 1.0
        if data.state_amplitude > 0.02:
            if sim_stats.state_amplitude > 0.01:
                upd["state_amplitude"] = float(np.clip(
                    spec.state_amplitude * _ratio(data.state_amplitude,
                                                  sim_stats.state_amplitude), 0.0, 2.0))
            if np.isfinite(data.state_period_s) and np.isfinite(sim_stats.state_period_s):
                upd["state_period_s"] = float(np.clip(
                    spec.state_period_s * _ratio(data.state_period_s,
                                                 sim_stats.state_period_s), 2.0, 600.0))
        else:
            upd["state_amplitude"] = 0.0
        spec = spec.with_(**upd)
    if best is not None:
        _, spec, sim_stats = best
    out_notes = list(notes or [])
    out_notes.append(
        "Spikes cannot say where connections are: the graph shape "
        f"({spec.graph}) and density ({spec.density:g}) are as set, and only the coupling "
        "strength was fitted, to the mean STTC. Change them to see how much that matters.")
    if data.burst_rate == 0:
        out_notes.append("No network bursts were found, so the simulation has none.")
    # A dial pinned at its limit means the model cannot reach the recording
    # there, however well the rest matches: say which.
    limits = [("rate_spread", 1.99, "rate spread across electrodes"),
              ("state_amplitude", 1.99, "slow-state depth"),
              ("coupling", 0.89, "coupling (mean STTC)")]
    pinned = [what for k, lim, what in limits if getattr(spec, k) >= lim]
    if data.burst_rate > 0 and spec.burst_participation >= 0.99:
        pinned.append("burst participation")
    if pinned:
        out_notes.append("At the model's limit, so not fully matched: " + ", ".join(pinned)
                         + ". Compare the two traces: a recording whose bursts come in "
                         "long clusters (up-states) has structure this model does not make.")
    return FitResult(spec=spec, data=data, sim=sim_stats or ActivityStats(), source=source,
                     history=history, notes=out_notes)


def fit_to_file(path: str | Path, base: SimSpec | None = None, *, method: str | None = None,
                lag_ms: float = 10.0, min_rate_hz: float = 0.1, max_nodes: int = 60,
                max_duration_s: float = 600.0, rounds: int = 15, progress=None,
                cancelled=None) -> FitResult:
    trains, T, label, notes = load_trains(path, method, min_rate_hz=min_rate_hz,
                                          max_nodes=max_nodes, max_duration_s=max_duration_s)
    if len(trains) < 3:
        raise ValueError(f"{label}: only {len(trains)} active trains — too few to fit a network.")
    return fit_to_trains(trains, T, base, lag_ms=lag_ms, rounds=rounds, source=label,
                         notes=notes, progress=progress, cancelled=cancelled)
