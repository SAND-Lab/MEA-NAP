"""Figures for :mod:`meanap.stim.consistency`: drift over trials, split-half networks.

Evoked is drawn in blue and baseline (the window before each stimulus) in grey
throughout: baseline is the reference, there to show what the recording does
on its own.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

EVOKED = "#2a62c9"
BASELINE = "#8a8f98"
ALPHA_BAND = 0.18

_SPLIT_LABELS = {"odd_even": ("odd trials", "even trials"),
                 "first_second": ("first half", "second half")}


def _fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "p = n/a"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _running_mean(y: np.ndarray, width: int) -> np.ndarray:
    out = np.full(len(y), np.nan)
    h = width // 2
    for i in range(len(y)):
        seg = y[max(0, i - h):i + h + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size:
            out[i] = seg.mean()
    return out


#: matplotlib's text sizes at its defaults, with the small panel titles these had.
_TEXT = dict(title_size=10, label_size=10, tick_size=9)


def _names(channels, n: int) -> list[str]:
    return [str(c) for c in channels] if channels is not None and len(channels) == n \
        else [str(k + 1) for k in range(n)]


def plot_trial_consistency(tc, channels: np.ndarray, path: Path, title: str) -> None:
    """Six panels: per-node responses, population response, latency, pattern
    similarity matrix, similarity vs trial separation, per-node drift."""
    from meanap.native.chart import (
        Band, Bars, Cells, Chart, ColourBar, Legend, LegendItem, Line, Panel, Points,
        Rule, rgba,
    )
    from meanap.native.chart_paint import save_chart

    evoked, baseline = rgba(EVOKED), rgba(BASELINE)
    resp = tc.response
    n_trials, n = resp.shape
    trial = np.arange(1, n_trials + 1)
    s = tc.summary
    names = _names(channels, n)
    trials_box = (0.5, n_trials + 0.5)
    panels = []

    # A — each node's response on every trial
    order = np.argsort(-resp.mean(axis=0), kind="stable")
    lim = max(float(np.nanpercentile(np.abs(resp), 99)) if resp.size else 1.0, 1.0)
    shown = resp[:, order].T

    def node_hover(i, j):
        return (f"node {i + 1}: electrode {names[order[i]]}, trial {j + 1}\n"
                f"evoked − baseline {shown[i, j]:+g} spikes")

    panels.append(Panel(
        cell=(0, 0), title="Evoked − baseline spike count per trial", xlabel="Trial",
        ylabel="Node (sorted by mean response)", grid="", y_down=True,
        marks=[Cells(shown, cmap="RdBu_r", low=-lim, high=lim, x=trials_box,
                     y=(0.5, n + 0.5), hover=node_hover)],
        colour_bar=ColourBar("RdBu_r", -lim, lim, label="Spikes", fraction=0.046,
                             tick_size=9), **_TEXT))

    # B — population response over trials
    ev, bl = tc.evoked.sum(axis=1), tc.baseline.sum(axis=1)
    marks = []
    for y, colour, label in ((ev, evoked, "Evoked"), (bl, baseline, "Baseline")):
        running = _running_mean(y, 7)
        marks.append(Points(trial, y, fill=rgba(colour, 0.45), size=4, key=label,
                            hover=[f"trial {t}: {label.lower()} {v:g} spikes"
                                   for t, v in zip(trial, y)]))
        marks.append(Line(trial, running, colour=colour, width=2, key=label,
                          hover=[f"trial {t}: {label.lower()} running mean {v:.2f}"
                                 for t, v in zip(trial, running)]))
    panels.append(Panel(
        cell=(0, 1), marks=marks, xlabel="Trial", ylabel="Spikes, all nodes", grid="",
        title=f"Population response (7-trial running mean)\nevoked − baseline vs "
              f"trial: ρ = {s['popResponseRho']:.2f}, {_fmt_p(s['popResponseP'])}",
        legend=Legend([LegendItem("Evoked", evoked, key="Evoked"),
                       LegendItem("Baseline", baseline, key="Baseline")], loc="best", size=8),
        **_TEXT))

    # C — first-spike latency over trials
    lat = tc.latency_s * 1000
    with warnings.catch_warnings():   # a trial on which no node fired: all-NaN row
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(lat, axis=1)
        q1, q3 = np.nanpercentile(lat, 25, axis=1), np.nanpercentile(lat, 75, axis=1)
    band = rgba(EVOKED, ALPHA_BAND)
    panels.append(Panel(
        cell=(0, 2), xlabel="Trial", ylabel="First-spike latency (ms)", grid="",
        marks=[Band(trial, q1, q3, colour=band),
               Line(trial, med, colour=evoked, width=1.5, marker="o", marker_size=4,
                    hover=[f"trial {t}: median {m:.1f} ms (IQR {a:.1f}–{b:.1f})"
                           for t, m, a, b in zip(trial, med, q1, q3)])],
        title=f"First-spike latency in {tc.window_s[0] * 1000:g}–"
              f"{tc.window_s[1] * 1000:g} ms\nmedian vs trial: ρ = "
              f"{s['latencyRho']:.2f}, {_fmt_p(s['latencyP'])}",
        legend=Legend([LegendItem("Interquartile range over nodes", band, kind="box"),
                       LegendItem("Median over nodes", evoked, marker=True)],
                      loc="best", size=8),
        **_TEXT))

    # D — how alike every pair of trials' response patterns is
    sim = np.asarray(tc.evoked_drift.similarity, float)
    panels.append(Panel(
        cell=(1, 0), title="Similarity of evoked patterns (r over nodes)", xlabel="Trial",
        ylabel="Trial", grid="", y_down=True,
        marks=[Cells(sim, cmap="RdBu_r", low=-1, high=1, x=trials_box, y=trials_box,
                     hover=lambda i, j: f"trials {i + 1} and {j + 1}: r = {sim[i, j]:.2f}")],
        colour_bar=ColourBar("RdBu_r", -1, 1, label="r", fraction=0.046, tick_size=9),
        **_TEXT))

    # E — similarity against trial separation, with the shuffled-order band
    max_lag = max(n_trials // 2, 1)
    lags = np.arange(1, max_lag + 1)
    marks, items = [], []
    for drift, colour, label, p in (
            (tc.evoked_drift, evoked, "Evoked", s["similarityLagSlopeP"]),
            (tc.baseline_drift, baseline, "Baseline", s["baselineSimilarityLagSlopeP"])):
        null = drift.lag_null[:, :max_lag]
        if null.size:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                lo, hi = np.nanpercentile(null, [2.5, 97.5], axis=0)
            marks.append(Band(lags, lo, hi, colour=rgba(colour, ALPHA_BAND), key=label))
        sim_lag = np.asarray(drift.lag_similarity[:max_lag], float)
        marks.append(Line(lags, sim_lag, colour=colour, width=2, key=label,
                          hover=[f"{label.lower()}, {k} trials apart: r = {v:.2f}"
                                 for k, v in zip(lags, sim_lag)]))
        items.append(LegendItem(f"{label} (slope {_fmt_p(p)})", colour, key=label))
    panels.append(Panel(
        cell=(1, 1), marks=marks, xlabel="Trials apart", ylabel="Mean pattern similarity (r)",
        title="Do trials far apart differ more? (band: shuffled order, 95%)", grid="",
        legend=Legend(items, loc="lower left", size=8), **_TEXT))

    # F — per-node trend
    rho, p = tc.node_rho, tc.node_p
    ok = np.isfinite(rho)
    bins = np.linspace(-1, 1, 21)
    sig = ok & (p < 0.05)
    plain, _ = np.histogram(rho[ok & ~sig], bins)
    signif, _ = np.histogram(rho[sig], bins)
    centres, width = (bins[:-1] + bins[1:]) / 2, 0.9 * (bins[1] - bins[0])

    def bin_text(k, what, count):
        who = [names[i] for i in np.flatnonzero(what)
               if bins[k] <= rho[i] < bins[k + 1] or (k == len(centres) - 1 and rho[i] == 1)]
        return (f"ρ {bins[k]:+.1f} to {bins[k + 1]:+.1f}: {count} node(s)"
                + (f"\nelectrodes {', '.join(who)}" if who else ""))

    marks = [Bars(centres, plain, width=width, colour=baseline, key="p ≥ 0.05",
                  hover=[bin_text(k, ok & ~sig, c) + "\np ≥ 0.05" for k, c in enumerate(plain)]),
             Bars(centres, signif, width=width, base=plain, colour=evoked, key="p < 0.05",
                  hover=[bin_text(k, sig, c) + "\np < 0.05" for k, c in enumerate(signif)]),
             Rule(0, axis="x", colour=rgba("black"), width=0.8)]
    top = int((plain + signif).max()) if len(centres) else 1
    panels.append(Panel(
        cell=(1, 2), marks=marks, xlabel="Spearman ρ, node response vs trial", ylabel="Nodes",
        xlim=(-1.1, 1.1), grid="",
        yticks=[(v, str(v)) for v in range(top + 1)] if top <= 10 else None,
        title=f"Which nodes drift\n{int(sig.sum())} of {int(ok.sum())} at p < 0.05 "
              f"(~{0.05 * ok.sum():.1f} expected by chance)",
        legend=Legend([LegendItem("p ≥ 0.05", baseline, kind="box", key="p ≥ 0.05"),
                       LegendItem("p < 0.05", evoked, kind="box", key="p < 0.05")],
                      loc="best", size=8),
        **_TEXT))

    chart = Chart(panels, size=(16, 9.5), grid=(2, 3), title_size=12,
                  title=f"{title}\n{n_trials} trials, {n} nodes")
    save_chart(chart, path)


def _active_both(a, b) -> np.ndarray:
    return (a.spike_counts > 0) & (b.spike_counts > 0)


def _halves_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Half A above the diagonal, half B below it."""
    out = np.triu(a, 1) + np.tril(b, -1)
    np.fill_diagonal(out, np.nan)
    return out


def plot_split_half(halves: dict, rows: list[dict], path: Path, title: str,
                    names=None) -> None:
    """One row per split: the two halves' evoked networks, and edge weights of
    one half against the other (raw STTC and STTC above the trial-shuffle null).

    *names* labels the nodes (electrode or unit) for a view to name the pair
    under the pointer; without it they are numbered from 0, as on the axes.
    """
    from meanap.native.chart import (
        Cells, Chart, ColourBar, Legend, LegendItem, Line, Panel, Points, Text, rgba,
    )
    from meanap.native.chart_paint import save_chart

    splits = [sp for sp in _SPLIT_LABELS if (sp, "evoked", "A") in halves]
    if not splits:
        return
    stats = {(r["split"], r["epoch"]): r for r in rows}
    panels = []
    for r_i, split in enumerate(splits):
        la, lb = _SPLIT_LABELS[split]
        a, b = halves[(split, "evoked", "A")], halves[(split, "evoked", "B")]

        mat = _halves_matrix(a.sttc, b.sttc)
        n = len(mat)
        node = [str(x) for x in names] if names is not None and len(names) == n else \
            [str(k) for k in range(n)]
        vmax = max(float(np.nanpercentile(mat, 99)) if np.isfinite(mat).any() else 0.0, 1e-6)

        def cell_hover(i, j, mat=mat, la=la, lb=lb, node=node):
            if i == j:
                return ""
            v = mat[i, j]
            return (f"{node[i]} ↔ {node[j]} ({la if j > i else lb})\n"
                    + (f"STTC {v:.3f}" if np.isfinite(v) else "STTC: no value"))

        panels.append(Panel(
            cell=(r_i, 0), title=f"Evoked STTC — upper: {la}, lower: {lb}", xlabel="Node",
            ylabel="Node", grid="", y_down=True, equal=True,
            marks=[Cells(mat, cmap="viridis", low=0, high=vmax, hover=cell_hover)],
            colour_bar=ColourBar("viridis", 0, vmax, label="STTC", fraction=0.046,
                                 tick_size=9), **_TEXT))

        for c_i, kind, label in ((1, "sttc", "STTC"),
                                 (2, "excess", "STTC above trial-shuffle null")):
            lo, hi = np.inf, -np.inf
            marks, items, notes = [], [], []
            for epoch, colour in (("baseline", BASELINE), ("evoked", EVOKED)):
                na, nb = halves[(split, epoch, "A")], halves[(split, epoch, "B")]
                on = _active_both(na, nb)
                xa = na.sttc if kind == "sttc" else na.sttc - na.null_mean
                xb = nb.sttc if kind == "sttc" else nb.sttc - nb.null_mean
                idx = np.flatnonzero(on)
                iu = np.triu_indices(idx.size, k=1)
                x, y = xa[np.ix_(on, on)][iu], xb[np.ix_(on, on)][iu]
                pairs = [f"{node[idx[i]]} ↔ {node[idx[j]]}" for i, j in zip(*iu)]
                ok = np.isfinite(x) & np.isfinite(y)   # trial_mean leaves some undefined
                x, y = x[ok], y[ok]
                pairs = [w for w, k in zip(pairs, ok) if k]
                st = stats.get((split, epoch), {})
                r, p = st.get(f"r_{kind}", np.nan), st.get(f"mantel_p_{kind}", np.nan)
                name = epoch.capitalize()
                marks.append(Points(x, y, fill=rgba(colour, 0.5), size=3, key=name,
                                    hover=[f"{w} ({epoch})\n{la} {u:.3f}, {lb} {v:.3f}"
                                           for w, u, v in zip(pairs, x, y)]))
                items.append(LegendItem(f"{name}: r = {r:.2f}, Mantel {_fmt_p(p)}",
                                        rgba(colour, 0.5), kind="point", key=name))
                if x.size:
                    lo, hi = min(lo, x.min(), y.min()), max(hi, x.max(), y.max())
                if kind == "sttc" and epoch == "evoked" and st:
                    notes.append(f"significant-edge overlap (Jaccard) "
                                 f"{st['jaccardSigEdges']:.2f}, chance {st['jaccardChance']:.2f}")
            if np.isfinite(lo):
                marks.insert(0, Line([lo, hi], [lo, hi], colour=rgba("black"), width=0.8, z=1))
            if notes:
                marks.append(Text(0.02, 0.97, notes[0], size=8, ha="left", va="top",
                                  coords="axes"))
            panels.append(Panel(
                cell=(r_i, c_i), marks=marks, xlabel=f"{label}, {la}", ylabel=f"{label}, {lb}",
                title=f"Edge weights, {la} vs {lb}", grid="",
                legend=Legend(items, loc="lower right", size=8), **_TEXT))
    chart = Chart(panels, size=(15, 4.8 * len(splits)), grid=(len(splits), 3), title_size=12,
                  title=f"{title}\nSplit-half networks — odd vs even: reliability; "
                        f"first vs second half: change over the recording")
    save_chart(chart, path)
