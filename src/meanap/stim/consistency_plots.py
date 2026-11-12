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


def _note(ax, text: str) -> None:
    ax.text(0.02, 0.97, text, transform=ax.transAxes, va="top", ha="left", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none", alpha=0.85))


def _tidy(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)


def plot_trial_consistency(tc, channels: np.ndarray, path: Path, title: str) -> None:
    """Six panels: per-node responses, population response, latency, pattern
    similarity matrix, similarity vs trial separation, per-node drift."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from meanap.pipeline.figure_output import savefig

    resp = tc.response
    n_trials, n = resp.shape
    trial = np.arange(1, n_trials + 1)
    s = tc.summary
    fig, axes = plt.subplots(2, 3, figsize=(16, 9.5))

    # A — each node's response on every trial
    ax = axes[0, 0]
    order = np.argsort(-resp.mean(axis=0), kind="stable")
    lim = max(float(np.nanpercentile(np.abs(resp), 99)) if resp.size else 1.0, 1.0)
    im = ax.imshow(resp[:, order].T, aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim,
                   interpolation="nearest", extent=(0.5, n_trials + 0.5, n + 0.5, 0.5))
    ax.set_xlabel("Trial")
    ax.set_ylabel("Node (sorted by mean response)")
    ax.set_title("Evoked − baseline spike count per trial", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Spikes")

    # B — population response over trials
    ax = axes[0, 1]
    ev, bl = tc.evoked.sum(axis=1), tc.baseline.sum(axis=1)
    for y, colour, label in ((ev, EVOKED, "Evoked"), (bl, BASELINE, "Baseline")):
        ax.plot(trial, y, "o", ms=4, color=colour, alpha=0.45, mec="none")
        ax.plot(trial, _running_mean(y, 7), "-", lw=2, color=colour, label=label)
    ax.set_xlabel("Trial")
    ax.set_ylabel("Spikes, all nodes")
    ax.set_title(f"Population response (7-trial running mean)\nevoked − baseline vs "
                 f"trial: ρ = {s['popResponseRho']:.2f}, {_fmt_p(s['popResponseP'])}",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="best")
    _tidy(ax)

    # C — first-spike latency over trials
    ax = axes[0, 2]
    lat = tc.latency_s * 1000
    with warnings.catch_warnings():   # a trial on which no node fired: all-NaN row
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(lat, axis=1)
        q1, q3 = np.nanpercentile(lat, 25, axis=1), np.nanpercentile(lat, 75, axis=1)
    ax.fill_between(trial, q1, q3, color=EVOKED, alpha=ALPHA_BAND, lw=0,
                    label="Interquartile range over nodes")
    ax.plot(trial, med, "o-", ms=4, lw=1.5, color=EVOKED, label="Median over nodes")
    ax.set_xlabel("Trial")
    ax.set_ylabel("First-spike latency (ms)")
    ax.set_title(f"First-spike latency in {tc.window_s[0] * 1000:g}–"
                 f"{tc.window_s[1] * 1000:g} ms\nmedian vs trial: ρ = "
                 f"{s['latencyRho']:.2f}, {_fmt_p(s['latencyP'])}", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="best")
    _tidy(ax)

    # D — how alike every pair of trials' response patterns is
    ax = axes[1, 0]
    im = ax.imshow(tc.evoked_drift.similarity, cmap="RdBu_r", vmin=-1, vmax=1,
                   interpolation="nearest", extent=(0.5, n_trials + 0.5, n_trials + 0.5, 0.5))
    ax.set_xlabel("Trial")
    ax.set_ylabel("Trial")
    ax.set_title("Similarity of evoked patterns (r over nodes)", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="r")

    # E — similarity against trial separation, with the shuffled-order band
    ax = axes[1, 1]
    max_lag = max(n_trials // 2, 1)
    lags = np.arange(1, max_lag + 1)
    for drift, colour, label, p in (
            (tc.evoked_drift, EVOKED, "Evoked", s["similarityLagSlopeP"]),
            (tc.baseline_drift, BASELINE, "Baseline", s["baselineSimilarityLagSlopeP"])):
        null = drift.lag_null[:, :max_lag]
        if null.size:
            lo, hi = np.nanpercentile(null, [2.5, 97.5], axis=0)
            ax.fill_between(lags, lo, hi, color=colour, alpha=ALPHA_BAND, lw=0)
        ax.plot(lags, drift.lag_similarity[:max_lag], "-", lw=2, color=colour,
                label=f"{label} (slope {_fmt_p(p)})")
    ax.set_xlabel("Trials apart")
    ax.set_ylabel("Mean pattern similarity (r)")
    ax.set_title("Do trials far apart differ more? (band: shuffled order, 95%)", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    _tidy(ax)

    # F — per-node trend
    ax = axes[1, 2]
    rho, p = tc.node_rho, tc.node_p
    ok = np.isfinite(rho)
    bins = np.linspace(-1, 1, 21)
    sig = ok & (p < 0.05)
    ax.hist([rho[ok & ~sig], rho[sig]], bins=bins, stacked=True, rwidth=0.9,
            color=[BASELINE, EVOKED], label=["p ≥ 0.05", "p < 0.05"])
    ax.axvline(0, color="black", lw=0.8)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.set_xlabel("Spearman ρ, node response vs trial")
    ax.set_ylabel("Nodes")
    ax.set_title(f"Which nodes drift\n{int(sig.sum())} of {int(ok.sum())} at p < 0.05 "
                 f"(~{0.05 * ok.sum():.1f} expected by chance)", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="best")
    _tidy(ax)

    fig.suptitle(f"{title}\n{n_trials} trials, {n} nodes")
    fig.tight_layout()
    savefig(fig, path, default_dpi=150)
    plt.close(fig)


def _active_both(a, b) -> np.ndarray:
    return (a.spike_counts > 0) & (b.spike_counts > 0)


def _halves_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Half A above the diagonal, half B below it."""
    out = np.triu(a, 1) + np.tril(b, -1)
    np.fill_diagonal(out, np.nan)
    return out


def plot_split_half(halves: dict, rows: list[dict], path: Path, title: str) -> None:
    """One row per split: the two halves' evoked networks, and edge weights of
    one half against the other (raw STTC and STTC above the trial-shuffle null)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from meanap.pipeline.figure_output import savefig

    splits = [sp for sp in _SPLIT_LABELS if (sp, "evoked", "A") in halves]
    if not splits:
        return
    stats = {(r["split"], r["epoch"]): r for r in rows}
    fig, axes = plt.subplots(len(splits), 3, figsize=(15, 4.8 * len(splits)), squeeze=False)
    for row, split in zip(axes, splits):
        la, lb = _SPLIT_LABELS[split]
        a, b = halves[(split, "evoked", "A")], halves[(split, "evoked", "B")]

        ax = row[0]
        mat = _halves_matrix(a.sttc, b.sttc)
        vmax = max(float(np.nanpercentile(mat, 99)) if np.isfinite(mat).any() else 0.0, 1e-6)
        im = ax.imshow(mat, cmap="viridis", vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_title(f"Evoked STTC — upper: {la}, lower: {lb}", fontsize=10)
        ax.set_xlabel("Node")
        ax.set_ylabel("Node")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="STTC")

        for ax, kind, label in ((row[1], "sttc", "STTC"),
                                (row[2], "excess", "STTC above trial-shuffle null")):
            lo, hi = np.inf, -np.inf
            notes = []
            for epoch, colour in (("baseline", BASELINE), ("evoked", EVOKED)):
                na, nb = halves[(split, epoch, "A")], halves[(split, epoch, "B")]
                on = _active_both(na, nb)
                xa = na.sttc if kind == "sttc" else na.sttc - na.null_mean
                xb = nb.sttc if kind == "sttc" else nb.sttc - nb.null_mean
                iu = np.triu_indices(int(on.sum()), k=1)
                x, y = xa[np.ix_(on, on)][iu], xb[np.ix_(on, on)][iu]
                ok = np.isfinite(x) & np.isfinite(y)   # trial_mean leaves some undefined
                x, y = x[ok], y[ok]
                st = stats.get((split, epoch), {})
                r, p = st.get(f"r_{kind}", np.nan), st.get(f"mantel_p_{kind}", np.nan)
                ax.plot(x, y, "o", ms=3, color=colour, alpha=0.5, mec="none",
                        label=f"{epoch.capitalize()}: r = {r:.2f}, Mantel {_fmt_p(p)}")
                if x.size:
                    lo, hi = min(lo, x.min(), y.min()), max(hi, x.max(), y.max())
                if kind == "sttc" and epoch == "evoked" and st:
                    notes.append(f"significant-edge overlap (Jaccard) "
                                 f"{st['jaccardSigEdges']:.2f}, chance {st['jaccardChance']:.2f}")
            if np.isfinite(lo):
                ax.plot([lo, hi], [lo, hi], "-", color="black", lw=0.8)
            ax.set_xlabel(f"{label}, {la}")
            ax.set_ylabel(f"{label}, {lb}")
            ax.set_title(f"Edge weights, {la} vs {lb}", fontsize=10)
            ax.legend(frameon=False, fontsize=8, loc="lower right")
            if notes:
                _note(ax, notes[0])
            _tidy(ax)
    fig.suptitle(f"{title}\nSplit-half networks — odd vs even: reliability; "
                 f"first vs second half: change over the recording")
    fig.tight_layout()
    savefig(fig, path, default_dpi=150)
    plt.close(fig)
