"""MEA-Sim's figures, as native charts (:mod:`meanap.native.chart`).

Plain data in, a :class:`~meanap.native.chart.Chart` out: the window shows
them in a :class:`~meanap.gui.figure_canvas.FigureCanvas` and
:func:`~meanap.native.chart_paint.save_chart` writes the same thing to a file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from meanap.native.chart import (
    Band, Cells, Chart, ColourBar, Legend, LegendItem, Line, Panel, Points, Rule, rgba,
)
from meanap.sim.measure import EDGE_METHODS, VIEWS, metric_label
from meanap.sim.pairs import PAIR_MEASURES, PROPERTIES
from meanap.sim.sweep import DIALS, VERDICT_COLOURS

__all__ = [
    "METHOD_COLOURS", "explore_chart", "sweep_chart", "scorecard_chart", "pairs_chart",
    "VERDICTS",
]

METHOD_COLOURS = {"raw": "#7f7f7f", "circular": "#d1495b", "top": "#e09f3e",
                  "jitter": "#2e86ab", "excess": "#3a7d44", "outside": "#7b2cbf",
                  "within": "#00a6a6", "pearson": "#4d4d4d", "schreiber": "#b5838d",
                  "cch": "#8d6e63", "partial": "#1b998b", "popreg": "#6a4c93",
                  "xcov_within": "#2a9d8f", "te": "#e76f51", "planted": "#222222"}
PAIR_COLOURS = {"sttc": "#2e86ab", "sttc_stored": "#8fbcd4", "corr_index": "#d1495b",
                "count_corr": "#e09f3e", "schreiber": "#b5838d", "cch": "#8d6e63"}

#: Metrics computed from the unthresholded STTC, identical for every edge method.
SHARED_METRICS = ("meanSTTC", "inhibAUC", "inhibSTTC", "fracNegative")

#: Verdicts in colour order, for the scorecard's colormap.
VERDICTS = ("robust", "moves", "follows", "responds", "weak", "blind", "n/a")
_VERDICT_CMAP = "measim_verdicts"


def _register_verdict_cmap() -> None:
    import matplotlib
    from matplotlib.colors import ListedColormap

    if _VERDICT_CMAP not in matplotlib.colormaps:
        matplotlib.colormaps.register(
            ListedColormap([VERDICT_COLOURS[v] for v in VERDICTS], name=_VERDICT_CMAP))


def _order(sim) -> np.ndarray:
    """Nodes grouped by planted module, hubs first: blocks show on the matrix."""
    return np.lexsort((~sim.hubs, sim.modules))


# ── one simulation ────────────────────────────────────────────────────────────


def explore_chart(sim, measured: dict, window_s: float = 30.0, view: str = "coupling") -> Chart:
    """Raster, population rate, the planted graph and each method's network."""
    order = _order(sim)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    n = sim.n
    T = sim.duration_s
    shown = min(window_s, T)

    xs, ys = [], []
    for i, t in enumerate(sim.trains):
        xs.append(t)
        ys.append(np.full(t.size, rank[i], float))
    x = np.concatenate(xs) if xs else np.empty(0)
    y = np.concatenate(ys) if ys else np.empty(0)
    raster = [Points(x, y, fill=rgba("#222222"), size=4.0, marker="|", key=None)]
    for b in sim.burst_times:
        raster.append(Rule(float(b), axis="x", colour=rgba("#e09f3e", 0.5), width=1.0, z=0.4))
    for s in sim.stim_times:
        raster.append(Rule(float(s), axis="x", colour=rgba("#7b2cbf", 0.45), width=1.0, z=0.4))

    bins = np.arange(0.0, T + 0.1, 0.1)
    pop = np.histogram(x, bins)[0] / 0.1 / max(n, 1)

    methods = list(measured)
    cols = 2 + len(methods)
    panels = [
        Panel(cell=(0, 0), span=(1, cols), marks=raster, title=(
            f"Raster ({n} nodes, mean {sim.rates_hz().mean():.2f} Hz; orange = network burst, "
            f"purple = stimulus)"),
            ylabel="Node (by planted module)", xlim=(0, shown), ylim=(-0.5, n - 0.5),
            y_down=True, grid="", zoom=(True, False), sharex="t", xlabels=False),
        Panel(cell=(1, 0), span=(1, cols),
              marks=[Line(bins[:-1] + 0.05, pop, colour=rgba("#222222"), width=0.8)],
              xlabel="Time (s)", ylabel="Rate / node (Hz)", xlim=(0, shown),
              sharex="t", zoom=(True, False)),
    ]

    names = [str(i + 1) for i in order]
    sg = sim.signs[np.ix_(order, order)]

    def hover_for(mat, what):
        def hover(i, j):
            if i == j:
                return ""
            v = mat[i, j]
            kind = {1: "planted excitatory edge", -1: "planted inhibitory edge"}.get(
                int(sg[i, j]), "no planted edge")
            val = f"{what} {v:+.3f}" if np.isfinite(v) else f"{what}: undefined"
            return f"node {names[i]} ↔ {names[j]}\n{val}\n{kind}"
        return hover

    planted = sg.astype(float)
    first = next(iter(measured.values()), None)
    signed = (first.signed[np.ix_(order, order)] if first is not None and first.signed is not None
              else np.full((n, n), np.nan))
    vmax = max([float(np.nanmax(measured[m].adjacency)) for m in methods] + [1e-6])
    slim = float(np.nanmax(np.abs(signed))) if signed is not None and np.isfinite(signed).any() \
        else 1.0
    slim = max(min(slim, 1.0), 1e-3)
    if view == "coactivation":
        from meanap.sim.measure import coactivation_truth

        co = coactivation_truth(sim)[np.ix_(order, order)]
        clim = max(float(np.max(np.abs(co))), 1e-6)
        truth_panel = ("True co-activation\n(in bursts and through connections)", co, "co-activation",
                       "RdBu_r", -clim, clim, None)
    else:
        truth_panel = ("Planted graph\n(red excitatory, blue inhibitory)", planted, "sign",
                       "RdBu_r", -1.0, 1.0, None)
    mats = [truth_panel,
            ("Signed STTC\n(MEA-NAP sets < 0 to 0)", signed, "STTC", "RdBu_r", -slim, slim,
             None)]
    for m in methods:
        meas = measured[m].metrics
        inh = meas.get("inhibKept", np.nan)
        if view == "coactivation":
            cap = (f"{EDGE_METHODS.get(m, m)}\nco-activation rank r "
                   f"{meas.get('coactRho', np.nan):+.2f}")
        elif np.isfinite(meas.get("recall", np.nan)):
            cap = (f"{EDGE_METHODS.get(m, m)}\nfound {meas.get('recall', np.nan):.0%}, "
                   f"{meas.get('falsePosRate', np.nan):.0%} false"
                   + (f"\ninhibitory kept: {inh:.0%}" if np.isfinite(inh) else ""))
        else:
            cap = (f"{EDGE_METHODS.get(m, m)}\nplanted edges AUC "
                   f"{meas.get('edgeAUC', np.nan):.2f}")
        mats.append((cap, measured[m].adjacency[np.ix_(order, order)], "STTC", "viridis",
                     0.0, vmax, m))
    for k, (title, mat, what, cmap, lo, hi, _m) in enumerate(mats):
        panels.append(Panel(
            cell=(2, k), marks=[Cells(mat, cmap=cmap, low=lo, high=hi,
                                      hover=hover_for(mat, what))],
            title=title, title_size=8.0, y_down=True, equal=True, grid="",
            xticks=[], yticks=[], zoom=(False, False),
            colour_bar=ColourBar(cmap, lo, hi, what, shrink=0.8) if k == 1 else None))
    return Chart(panels=panels, grid=(3, cols), size=(2.6 * cols + 1, 7.6),
                 heights=[1.6, 0.6, 1.6],
                 colour_bar=ColourBar("viridis", 0.0, vmax, "STTC (kept edges)"))


# ── line search ───────────────────────────────────────────────────────────────


def sweep_chart(summary: pd.DataFrame, dial: str, metrics: list[str], methods: list[str],
                ncols: int = 4, scores: pd.DataFrame | None = None,
                view: str = "coupling") -> Chart:
    """One panel per metric: mean ± SD across replicates, a line per edge method."""
    d = DIALS.get(dial)
    sub = summary[summary["dial"] == dial]
    metrics = [m for m in metrics if m in set(sub["metric"])]
    rate = sub[sub["metric"] == "meanRate"].groupby("value")["mean"].mean()
    nrows = max(1, int(np.ceil(len(metrics) / ncols)))
    xlog = bool(d and d.log and (sub["value"] > 0).all())
    xticks = None
    if xlog and not sub.empty:
        lo, hi = np.log10(sub["value"].min()), np.log10(sub["value"].max())
        xticks = [(np.log10(v), f"{v:g}") for e in range(int(np.floor(lo)), int(np.ceil(hi)) + 1)
                  for v in (10.0 ** e, 2 * 10.0 ** e, 5 * 10.0 ** e)
                  if lo - 1e-9 <= np.log10(v) <= hi + 1e-9]
    panels = []
    for k, metric in enumerate(metrics):
        marks = []
        verdicts = []
        # Mean STTC and AUC come from the raw STTC matrix: the same for every method.
        shared = metric in SHARED_METRICS
        for m in (methods[:1] if shared else methods):
            s = sub[(sub["metric"] == metric) & (sub["method"] == m)].sort_values("value")
            if s.empty:
                continue
            xv_ = s["value"].to_numpy(float)
            x = np.log10(xv_) if xlog else xv_
            mu = s["mean"].to_numpy(float)
            sd = np.nan_to_num(s["sd"].to_numpy(float))
            col = "#444444" if shared else METHOD_COLOURS.get(m, "#444444")
            key = None if shared else m
            marks.append(Band(x, mu - sd, mu + sd, colour=rgba(col, 0.15), key=key))
            hover = [f"{'every edge method' if shared else EDGE_METHODS.get(m, m)}\n"
                     f"{d.label if d else dial} = {xv:g}"
                     f"\n{metric_label(metric)} = {v:.3g} ± {e:.2g}"
                     + (f"\nmean rate {rate.get(xv, np.nan):.2f} Hz" if len(rate) else "")
                     for xv, v, e in zip(xv_, mu, sd)]
            marks.append(Line(x, mu, colour=rgba(col), width=1.6, marker="o", marker_size=4.5,
                              key=key, hover=hover, label=EDGE_METHODS.get(m, m)))
            if scores is not None:
                v = scores[(scores["dial"] == dial) & (scores["method"] == m)
                           & (scores["metric"] == metric)]
                if not v.empty:
                    verdicts.append(v.iloc[0]["verdict"])
        title = metric_label(metric) + (" (any method)" if shared else "")
        panels.append(Panel(
            cell=divmod(k, ncols), marks=marks, title=title, title_size=9.0, xticks=xticks,
            xlabel=(f"{d.label}" + (f" ({d.unit})" if d and d.unit else "")) if d else dial,
            label_size=8.0, grid="y"))
    items = [LegendItem(EDGE_METHODS.get(m, m), rgba(METHOD_COLOURS.get(m, "#444444")),
                        marker=True, key=m) for m in methods]
    kind = d.kind_for(view) if d else "nuisance"
    note = ("Mean ± SD over replicates; every point uses the same planted graphs and seeds. "
            + ("A metric of connectivity should stay flat along this dial — it is not connectivity."
               if kind == "nuisance" else
               "This dial changes what is being measured, so a useful metric should move."))
    return Chart(panels=panels, grid=(nrows, ncols), size=(3.0 * ncols, 2.5 * nrows + 0.9),
                 legend=Legend(items, loc="lower center", columns=min(len(items), 4)),
                 note=note, gap=(22.0, 26.0))


# ── scorecard ─────────────────────────────────────────────────────────────────


def scorecard_chart(scores: pd.DataFrame, method: str, metrics: list[str],
                    view: str = "coupling") -> Chart:
    """Metric × dial, coloured by verdict, with how far the dial moved the metric."""
    _register_verdict_cmap()
    sub = scores[scores["method"] == method]
    dials = [d for d in DIALS if d in set(sub["dial"])]
    dials.sort(key=lambda d: (DIALS[d].kind_for(view) != "nuisance", list(DIALS).index(d)))
    metrics = [m for m in metrics if m in set(sub["metric"])]
    vals = np.full((len(metrics), len(dials)), float(VERDICTS.index("n/a")))
    text = [["" for _ in dials] for _ in metrics]
    tips = [["" for _ in dials] for _ in metrics]
    for i, metric in enumerate(metrics):
        for j, dial in enumerate(dials):
            r = sub[(sub["metric"] == metric) & (sub["dial"] == dial)]
            if r.empty:
                continue
            r = r.iloc[0]
            vals[i, j] = VERDICTS.index(r["verdict"])
            s = r["shift_sd"]
            rel = r["relative"]
            if np.isfinite(s) or np.isinf(s):
                text[i][j] = ("∞" if np.isinf(s) else f"{s:.1f}") + (
                    f"  ·  {rel:.0%}" if np.isfinite(rel) else "")
            else:
                text[i][j] = "–"
            tips[i][j] = (f"{metric_label(metric)} vs {DIALS[dial].label.lower()}\n"
                          f"{r['verdict']}: moves {s:.2g} replicate SDs "
                          f"({r['relative']:.0%} of its size), Spearman ρ = {r['rho']:+.2f}")
    n_nuis = sum(DIALS[d].kind_for(view) == "nuisance" for d in dials)
    xt = [(j, DIALS[d].label + ("" if DIALS[d].kind_for(view) == "nuisance" else " ★")) for j, d in
          enumerate(dials)]
    marks = [Cells(vals, cmap=_VERDICT_CMAP, low=-0.5, high=len(VERDICTS) - 0.5, text=text,
                   text_colour=[["#ffffff"] * len(dials) for _ in metrics], text_size=8.0,
                   text_bold=True, hover=tips)]
    if 0 < n_nuis < len(dials):
        marks.append(Rule(n_nuis - 0.5, axis="x", colour=rgba("#222222"), width=2.0, z=5))
    panel = Panel(marks=marks, xticks=xt, yticks=[(i, metric_label(m)) for i, m in
                                                  enumerate(metrics)],
                  y_down=True, grid="", xtick_rotation=30, tick_size=8.0, zoom=(False, False),
                  title=f"{EDGE_METHODS.get(method, method)}: how far each dial moves each "
                        f"metric (in replicate SDs) — {VIEWS.get(view, view)}", title_size=10)
    legend = Legend([LegendItem(v, rgba(VERDICT_COLOURS[v]), kind="box") for v in VERDICTS
                     if v != "n/a" and (vals == VERDICTS.index(v)).any()],
                    loc="lower center", columns=6)
    note = ("Each cell: how far the dial moved the metric, in replicate SDs, and as % of its "
            "size. Left of the line: nuisances, not what is being measured — green 'robust' (< 1 "
            "SD), amber 'moves' (1–3), red 'follows' (≥ 3). Right (★): "
            + ("co-activation (bursts and connections)" if view == "coactivation"
               else "planted connectivity") + " — green "
            "'responds' (≥ 3 SD), amber 'weak', red 'blind' (< 1). Replicates differ only in "
            "random draws, so real cultures vary more than this SD: a red cell is a confound "
            "for any comparison where that nuisance differs between groups.")
    return Chart(panels=[panel], size=(1.25 * len(dials) + 3.2, 0.36 * len(metrics) + 2.3),
                 legend=legend, note=note)


# ── Cutts & Eglen ─────────────────────────────────────────────────────────────


def pairs_chart(results) -> Chart:
    """Pass/fail table for N1–N6, and the line searches behind N2, N3 and N5."""
    _register_verdict_cmap()
    props = [p for p in PROPERTIES if any(r.prop == p for r in results)]
    measures = [m for m in PAIR_MEASURES if any(r.measure == m for r in results)]
    vals = np.full((len(measures), len(props)), float(VERDICTS.index("n/a")))
    text = [["" for _ in props] for _ in measures]
    tips = [["" for _ in props] for _ in measures]
    by = {(r.prop, r.measure): r for r in results}
    for i, m in enumerate(measures):
        for j, p in enumerate(props):
            r = by.get((p, m))
            if r is None or r.passed is None:
                continue
            vals[i, j] = VERDICTS.index("robust" if r.passed else "follows")
            text[i][j] = "pass" if r.passed else "fail"
            tips[i][j] = f"{p} {PROPERTIES[p]}\n{PAIR_MEASURES[m]}\n{r.detail}"
    table = Panel(
        cell=(0, 0), span=(1, 3),
        marks=[Cells(vals, cmap=_VERDICT_CMAP, low=-0.5, high=len(VERDICTS) - 0.5, text=text,
                     text_colour=[["#ffffff"] * len(props) for _ in measures], text_size=8.5,
                     text_bold=True, hover=tips)],
        xticks=[(j, f"{p}  {PROPERTIES[p]}") for j, p in enumerate(props)],
        yticks=[(i, PAIR_MEASURES[m]) for i, m in enumerate(measures)],
        y_down=True, grid="", xtick_rotation=20, tick_size=8.0, zoom=(False, False),
        title="Cutts & Eglen (2014) necessary properties", title_size=10)
    panels = [table]
    for k, prop in enumerate(("N2", "N3", "N5")):
        marks = []
        xlabel, xlog = "", False
        for m in measures:
            r = by.get((prop, m))
            if r is None or not r.curves:
                continue
            x, mu, sd = next(iter(r.curves.values()))
            ref = np.nanmean(np.abs(mu))
            if not np.isfinite(ref) or ref == 0:
                continue
            xlabel, xlog = r.xlabel, r.xlog
            col = PAIR_COLOURS.get(m, "#444444")
            xv = np.log10(x) if xlog else x
            marks.append(Line(xv, mu / ref, colour=rgba(col), width=1.6, marker="o",
                              marker_size=4, key=m, label=PAIR_MEASURES[m],
                              hover=[f"{PAIR_MEASURES[m]}\n{xx:g}: {v:.3g}"
                                     for xx, v in zip(x, mu)]))
        marks.append(Rule(1.0, colour=rgba("#999999"), dash="--"))
        ticks = None
        if xlog and marks:
            lo = int(np.floor(min(np.nanmin(mk.x) for mk in marks if isinstance(mk, Line))))
            hi = int(np.ceil(max(np.nanmax(mk.x) for mk in marks if isinstance(mk, Line))))
            ticks = [(np.log10(m * 10.0 ** e), f"{m * 10.0 ** e:g}")
                     for e in range(lo, hi + 1) for m in (1, 2, 5)]
        panels.append(Panel(cell=(1, k), marks=marks, xticks=ticks,
                            title=f"{prop} {PROPERTIES[prop]}", title_size=9,
                            xlabel=xlabel, ylabel="Value / its mean" if k == 0 else "",
                            grid="y"))
    items = [LegendItem(PAIR_MEASURES[m], rgba(PAIR_COLOURS.get(m, "#444444")), marker=True,
                        key=m) for m in measures]
    note = ("Line searches on Cutts & Eglen's Poisson spiking model (share of synchronous "
            "spikes held fixed). Each measure is divided by its own mean so robustness reads "
            "the same for all: a flat line at 1 is robust.")
    return Chart(panels=panels, grid=(2, 3), size=(11.5, 7.2), heights=[1.0, 1.25],
                 legend=Legend(items, loc="lower center", columns=4), note=note,
                 gap=(26.0, 30.0))


# ── match my data ─────────────────────────────────────────────────────────────

DATA_COLOUR, SIM_COLOUR = "#222222", "#2e86ab"


def match_chart(fit, window_s: float = 60.0) -> Chart:
    """The recording beside the simulation fitted to it."""
    d, s = fit.data, fit.sim
    items = [LegendItem("Recording", rgba(DATA_COLOUR), marker=True, key="data"),
             LegendItem("Fitted simulation", rgba(SIM_COLOUR), marker=True, key="sim")]
    panels = []

    marks = []
    for st, col, key in ((d, DATA_COLOUR, "data"), (s, SIM_COLOUR, "sim")):
        r = st.rates[st.rates > 0]
        if r.size:
            x = np.arange(1, r.size + 1)
            marks.append(Line(x, np.log10(r), colour=rgba(col), width=1.6, marker="o",
                              marker_size=3.5, key=key,
                              hover=[f"rank {k}: {v:.2f} Hz" for k, v in zip(x, r)]))
    lo = min((float(np.min(np.log10(st.rates[st.rates > 0]))) for st in (d, s)
              if (st.rates > 0).any()), default=-1.0)
    hi = max((float(np.max(np.log10(st.rates[st.rates > 0]))) for st in (d, s)
              if (st.rates > 0).any()), default=1.0)
    yt = [(np.log10(v), f"{v:g}") for e in range(int(np.floor(lo)), int(np.ceil(hi)) + 1)
          for v in (10.0 ** e, 3 * 10.0 ** e) if lo - 0.2 <= np.log10(v) <= hi + 0.2]
    panels.append(Panel(cell=(0, 0), marks=marks, yticks=yt, title="Firing rates, busiest first",
                        xlabel="Electrode rank", ylabel="Rate (Hz)"))

    marks = []
    allv = np.concatenate([d.sttc, s.sttc]) if d.sttc.size + s.sttc.size else np.zeros(1)
    lo, hi = float(min(np.min(allv), -0.05)), float(max(np.max(allv), 0.05))
    edges = np.linspace(lo, hi, 41)
    for st, col, key in ((d, DATA_COLOUR, "data"), (s, SIM_COLOUR, "sim")):
        if st.sttc.size:
            h = np.histogram(st.sttc, edges)[0] / st.sttc.size
            x = np.repeat(edges, 2)[1:-1]
            marks.append(Line(x, np.repeat(h, 2), colour=rgba(col), width=1.5, key=key))
    marks.append(Rule(0.0, axis="x", colour=rgba("#999999"), dash="--"))
    panels.append(Panel(cell=(0, 1), marks=marks, title="Signed STTC of every pair",
                        xlabel="STTC (MEA-NAP keeps only > 0)", ylabel="Share of pairs"))

    marks = []
    for st, col, key in ((d, DATA_COLOUR, "data"), (s, SIM_COLOUR, "sim")):
        if st.pop_rate.size > 2:
            c = st.pop_rate
            lags = np.arange(0, min(60, c.size // 4))
            cc = c - c.mean()
            v = np.mean(cc * cc)
            ac = [1.0] + [float(np.mean(cc[:-k] * cc[k:]) / v) if v > 0 else 0.0
                          for k in lags[1:]]
            marks.append(Line(lags * 0.1, np.array(ac), colour=rgba(col), width=1.5, key=key))
    panels.append(Panel(cell=(0, 2), marks=marks, title="Population rate autocorrelation",
                        xlabel="Lag (s)", ylabel="r"))

    for row, (st, col, name) in enumerate(((d, DATA_COLOUR, "Recording"),
                                           (s, SIM_COLOUR, "Fitted simulation")), start=1):
        n = min(st.pop_rate.size, int(window_s / 0.1))
        t = np.arange(n) * 0.1
        panels.append(Panel(cell=(row, 0), span=(1, 3),
                            marks=[Line(t, st.pop_rate[:n], colour=rgba(col), width=0.8)],
                            title=f"{name}: population rate, first {window_s:g} s",
                            title_size=8.5, ylabel="Hz / node", xlabel="Time (s)" if row == 2
                            else "", xlabels=row == 2, sharex="pop", sharey="popy",
                            zoom=(True, False)))
    return Chart(panels=panels, grid=(3, 3), size=(11.5, 7.6), heights=[1.5, 0.75, 0.75],
                 legend=Legend(items, loc="lower center", columns=2), gap=(22.0, 30.0),
                 title=f"Matched to {fit.source}", title_size=10)


# ── schematics for the About tab ──────────────────────────────────────────────

_A, _B, _L, _HIDDEN = "#2e86ab", "#d1495b", "#e09f3e", "#b8b8b8"


def _arrow(x0, y0, x1, y1, colour, *, shrink=0.75, dash="-", width=1.8, head=0.38):
    from meanap.native.chart import Polygon, Segments

    d = np.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    xa, ya = x0 + ux * shrink, y0 + uy * shrink
    xb, yb = x1 - ux * shrink, y1 - uy * shrink
    px, py = -uy, ux
    tip = (xb, yb)
    base = (xb - ux * head, yb - uy * head)
    poly = Polygon(np.array([tip[0], base[0] + px * head * 0.5, base[0] - px * head * 0.5]),
                   np.array([tip[1], base[1] + py * head * 0.5, base[1] - py * head * 0.5]),
                   fill=rgba(colour), z=3)
    seg = Segments(np.array([[xa, ya, base[0], base[1]]]), colour=rgba(colour), width=width,
                   dash=dash, z=2)
    return [seg, poly]


def _node(x, y, label, colour, size=26.0):
    from meanap.native.chart import Text

    return [Points(np.array([x]), np.array([y]), fill=rgba(colour), size=size, z=4),
            Text(x, y, label, colour=rgba("#ffffff"), size=10, bold=True, z=5)]


def _hidden(cx, cy, rx, ry, n, seed):
    rng = np.random.default_rng(seed)
    a = rng.uniform(0, 2 * np.pi, n)
    r = np.sqrt(rng.uniform(0, 1, n))
    return Points(cx + rx * r * np.cos(a), cy + ry * r * np.sin(a), fill=rgba(_HIDDEN),
                  size=6.0, z=2)


def _ticks(rows: list[tuple[np.ndarray, str]]):
    marks = []
    for k, (t, colour) in enumerate(rows):
        marks.append(Points(np.asarray(t, float), np.full(len(t), float(k)), fill=rgba(colour),
                            size=12.0, marker="|"))
    return marks


def common_input_chart() -> Chart:
    """Three ways two electrodes, A and B, come to fire together."""
    from meanap.native.chart import Span, Text

    rng = np.random.default_rng(4)
    T = 3.0
    panels = []
    box = dict(bare=True, equal=True, xlim=(0, 10), ylim=(0, 10), zoom=(False, False),
               title_size=9.5)

    # 1 — a direct connection
    marks = _arrow(2.5, 4.5, 7.5, 4.5, "#222222") + _node(2.5, 4.5, "A", _A) + \
        _node(7.5, 4.5, "B", _B)
    marks.append(Text(5.0, 5.5, "connection", size=8.5, colour=rgba("#444444")))
    panels.append(Panel(cell=(0, 0), marks=marks, **box,
                        title="1 · Connected\nB fires a few ms after A"))
    a = np.sort(rng.uniform(0, T, 9))
    b = np.sort(np.concatenate([a[rng.random(a.size) < 0.6] + 0.006, rng.uniform(0, T, 4)]))
    panels.append(Panel(cell=(1, 0), marks=_ticks([(a, _A), (b, _B)]), xlim=(0, T),
                        ylim=(-0.6, 1.6), yticks=[(0, "A"), (1, "B")], y_down=True, grid="",
                        xlabel="Time (s)", zoom=(False, False)))

    # 2 — common input, no connection
    marks = [_hidden(5.0, 8.0, 2.4, 1.1, 34, 1),
             Text(5.0, 9.65, "neurons no electrode records", size=8, colour=rgba("#666666"))]
    marks += _arrow(4.0, 7.2, 2.5, 3.6, _HIDDEN, shrink=0.6) + \
        _arrow(6.0, 7.2, 7.5, 3.6, _HIDDEN, shrink=0.6)
    from meanap.native.chart import Segments
    marks.append(Segments(np.array([[3.4, 3.0, 6.6, 3.0]]), colour=rgba("#999999"), dash="--"))
    marks.append(Text(5.0, 2.2, "no connection", size=8.5, colour=rgba("#999999")))
    marks += _node(2.5, 3.0, "A", _A) + _node(7.5, 3.0, "B", _B)
    panels.append(Panel(cell=(0, 1), marks=marks, **box,
                        title="2 · Common input\nA and B share every burst, never affect "
                              "each other"))
    bursts = np.array([0.55, 1.7, 2.55])
    rows = []
    for colour in (_A, _B):
        t = np.concatenate([np.repeat(bursts, 5) + rng.normal(0, 0.03, 15),
                            rng.uniform(0, T, 3)])
        rows.append((np.sort(t), colour))
    spans = [Span(x - 0.08, x + 0.08, axis="x", colour=(0.6, 0.6, 0.6, 0.18)) for x in bursts]
    panels.append(Panel(cell=(1, 1), marks=spans + _ticks(rows), xlim=(0, T), ylim=(-0.6, 1.6),
                        yticks=[(0, "A"), (1, "B")], y_down=True, grid="",
                        xlabel="Time (s) — grey: network bursts", zoom=(False, False)))

    # 3 — a burst spreading along connections
    marks = [_hidden(5.0, 8.6, 1.8, 0.7, 18, 2)]
    marks += _arrow(1.5, 4.5, 5.0, 4.5, "#222222") + _arrow(5.0, 4.5, 8.5, 4.5, "#222222")
    marks += _arrow(5.8, 8.0, 8.5, 5.2, _HIDDEN, shrink=0.6, dash="--", width=1.2)
    marks += _node(1.5, 4.5, "L", _L) + _node(5.0, 4.5, "A", _A) + _node(8.5, 4.5, "B", _B)
    marks += [Text(3.25, 5.4, "~10 ms", size=8, colour=rgba("#444444")),
              Text(6.75, 5.4, "~10 ms", size=8, colour=rgba("#444444")),
              Text(1.5, 3.2, "leader", size=8, colour=rgba("#444444"))]
    panels.append(Panel(cell=(0, 2), marks=marks, **box,
                        title="3 · Burst spreading along connections\nL → A → B, "
                              "the order set by the wiring"))
    rows = [(np.sort(rng.uniform(0, 12, 4)), _L), (np.sort(10 + rng.uniform(0, 12, 4)), _A),
            (np.sort(20 + rng.uniform(0, 12, 4)), _B)]
    panels.append(Panel(cell=(1, 2), marks=_ticks(rows), xlim=(-2, 40), ylim=(-0.6, 2.6),
                        yticks=[(0, "L"), (1, "A"), (2, "B")], y_down=True, grid="",
                        xlabel="ms after the burst starts", zoom=(False, False)))
    note = ("Co-activation counts all three: A and B are active together. Beyond bursts, "
            "only 1 is a connection between A and B; 2 is common input, which the circular-"
            "shift null calls an edge and the jitter null, outside-burst and excess STTC do "
            "not. 3 is in between: the order inside each burst is fine timing that follows "
            "the wiring, so part of it survives the jitter null — whether it counts as a "
            "connection is a judgement, not a test result.")
    return Chart(panels=panels, grid=(2, 3), size=(11.5, 6.0), heights=[1.45, 0.75], note=note,
                 note_size=9.0,
                 gap=(24.0, 18.0))
