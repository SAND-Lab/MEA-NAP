"""Pictures for the Data, Connectivity and Stats & ML settings cards.

Every picture is drawn from the pipeline's own functions — the layout table,
the STTC, the circular-shift surrogates, NMF, the SA fits and the stats step's
culture-grouped folds — on small synthetic data with fixed seeds, so it shows
what MEA-NAP actually computes.
"""

from __future__ import annotations

import numpy as np
from matplotlib.patches import Rectangle

try:
    from .style import ACCENT, ACCENT_2, ACCENT_3, INK, MUTED, PALETTE, SOFT, figure, save
except ImportError:  # run as a script from this folder
    from style import ACCENT, ACCENT_2, ACCENT_3, INK, MUTED, PALETTE, SOFT, figure, save


# ── Data tab ──────────────────────────────────────────────────────────────────


def channel_layouts():
    """Electrode positions of every built-in layout, small multiples."""
    from meanap.pipeline.channel_layout import get_coords_from_layout
    from meanap.pipeline.probes import DEFAULT_PITCH_UM

    names = ["MCS60", "MCS59", "Axion64", "Axion16"]
    fig, axes = figure((4.6, 1.75), ncols=len(names))
    for ax, name in zip(axes, names):
        channels, coords = get_coords_from_layout(name)
        ax.scatter(coords[:, 0], coords[:, 1], s=9 if len(channels) > 20 else 30,
                   color=ACCENT, edgecolor="none")
        if name == "MCS59":
            # The grounded electrode MCS59 drops, where it would sit.
            _, full = get_coords_from_layout("MCS60")
            chans60, _ = get_coords_from_layout("MCS60")
            xy = full[list(chans60).index(82)]
            ax.scatter([xy[0]], [xy[1]], s=14, facecolor="white",
                       edgecolor=ACCENT_2, linewidth=1)
        ax.set_title(name, fontsize=8.5, pad=3)
        ax.text(0.5, -0.08, f"{len(channels)} electrodes\n{DEFAULT_PITCH_UM[name]:.0f} µm pitch",
                transform=ax.transAxes, ha="center", va="top", fontsize=7, color=MUTED)
        ax.set_aspect("equal")
        ax.set_xlim(-0.8, 8.8)
        ax.set_ylim(-0.8, 8.8)
        ax.axis("off")
    fig.subplots_adjust(wspace=0.15)
    return save(fig, "channel_layouts")


# ── Connectivity tab ──────────────────────────────────────────────────────────


def _coupled_trains(rng, duration, rate_a, rate_b, share, jitter):
    """Two Poisson trains; a fraction *share* of B's spikes follow A's."""
    a = np.sort(rng.uniform(0, duration, rng.poisson(rate_a * duration)))
    n_follow = int(round(share * rate_b * duration))
    follow = rng.choice(a, size=min(n_follow, a.size), replace=False) + rng.normal(0, jitter, min(n_follow, a.size))
    own = rng.uniform(0, duration, rng.poisson((1 - share) * rate_b * duration))
    b = np.sort(np.clip(np.concatenate([follow, own]), 0, duration - 1e-6))
    return a, b


def sttc_tiles():
    """Two spike trains with their ±Δt tiles, and the STTC that results."""
    from meanap.pipeline.sttc import sttc_pair

    rng = np.random.default_rng(5)
    duration, dt = 2.0, 0.025
    a, b = _coupled_trains(rng, duration, rate_a=7, rate_b=7, share=0.5, jitter=0.012)
    value = sttc_pair(a, b, dt, 0.0, duration)

    fig, ax = figure((4.6, 1.75))
    rows = {"A": (a, 1.0), "B": (b, 0.0)}
    for label, (train, y) in rows.items():
        other = b if label == "A" else a
        for t in train:
            ax.add_patch(Rectangle((t - dt, y - 0.32), 2 * dt, 0.64,
                                   facecolor=SOFT, edgecolor="none", zorder=0))
        near = np.array([np.any(np.abs(other - t) <= dt) for t in train])
        ax.vlines(train[near], y - 0.25, y + 0.25, color=ACCENT, lw=1.4, zorder=2)
        ax.vlines(train[~near], y - 0.25, y + 0.25, color=MUTED, lw=1.4, zorder=2)
        ax.text(-0.04, y, f"train {label}", ha="right", va="center", fontsize=8)
    ax.set_xlim(0, duration)
    ax.set_ylim(-0.6, 1.6)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("time (s)")
    ax.set_title(f"Δt = {dt * 1000:.0f} ms   ·   STTC = {value:.2f}", fontsize=9)
    ax.text(0.5, -0.42, "shaded: the ±Δt tile round each spike;  blue: a spike within "
            "±Δt of the other train", transform=ax.transAxes,
            ha="center", va="top", fontsize=6.8, color=MUTED)
    return save(fig, "sttc")


def prob_threshold_null():
    """Surrogate STTC distributions for a kept and a removed edge."""
    from meanap.pipeline.probabilistic_threshold import circular_shift_spikes
    from meanap.pipeline.sttc import get_sttc

    rng = np.random.default_rng(11)
    duration, lag_ms, fs, reps, tail = 120.0, 25, 25000.0, 200, 0.05
    pairs = [("kept", 0.12), ("removed", 0.03)]
    fig, axes = figure((4.6, 2.0), ncols=2, sharey=True)
    for ax, (title, share) in zip(axes, pairs):
        a, b = _coupled_trains(rng, duration, rate_a=3, rate_b=3, share=share, jitter=0.006)
        trains = {0: a, 1: b}
        real = get_sttc(trains, 2, lag_ms, duration)[0, 1]
        null = np.empty(reps)
        for r in range(reps):
            shifted = circular_shift_spikes(trains, 2, fs, duration, rng)
            null[r] = get_sttc(shifted, 2, lag_ms, duration)[0, 1]
        # adjm_thr's cutoff: the ceil((1 - tail) * reps)-th smallest surrogate.
        cutoff = np.sort(null)[int(np.ceil((1 - tail) * reps)) - 1]
        ax.hist(null, bins=20, color=SOFT, edgecolor=ACCENT, linewidth=0.5)
        ax.axvline(cutoff, color=INK, ls="--", lw=1)
        colour = ACCENT_3 if real >= cutoff else ACCENT_2
        ax.axvline(real, color=colour, lw=2)
        ymax = ax.get_ylim()[1]
        ax.set_title(f"edge {title}", fontsize=8.5, color=colour)
        ax.text(cutoff, ymax * 0.98, " 95th pct", fontsize=6.5, va="top", ha="left", color=INK)
        right = real >= cutoff
        ax.text(real, ymax * 0.70, f" real\n {real:.2f}" if right else f"real \n{real:.2f} ",
                fontsize=6.5, va="top", ha="left" if right else "right", color=colour)
        ax.set_xlabel("STTC")
    lo = min(a.get_xlim()[0] for a in axes)
    hi = max(a.get_xlim()[1] for a in axes)
    for ax in axes:
        ax.set_xlim(lo, hi)
    axes[0].set_ylabel(f"surrogates (of {reps})")
    return save(fig, "prob_threshold")


def nmf_plateau():
    """NMF variance explained per rank, with and without the early stop."""
    from meanap.pipeline.nmf import cal_nmf

    rng = np.random.default_rng(5)
    n_ch, duration, n_assemblies = 60, 120.0, 4
    # Assemblies: groups of channels that fire together, over background firing.
    members = np.array_split(rng.permutation(n_ch), n_assemblies)
    trains = [list(rng.uniform(0, duration, rng.poisson(0.5 * duration))) for _ in range(n_ch)]
    for group in members:
        events = rng.uniform(0, duration, rng.poisson(0.3 * duration))
        for ch in group:
            for t in events:
                if rng.random() < 0.9:
                    trains[ch].extend(t + rng.normal(0, 0.02, rng.poisson(3)))
    trains = [np.sort(np.clip(np.asarray(t), 0, duration - 1e-6)) for t in trains]
    counts = np.array([len(t) for t in trains])

    full, stopped = (
        cal_nmf(trains, counts, duration, 10.0, 25000.0, rng=np.random.default_rng(0),
                plateau_gain=gain)["nnmf_var_explained"]
        for gain in (0.0, 0.005))
    ranks = np.arange(1, full.size + 1)
    fitted = np.isfinite(stopped)
    last = int(ranks[fitted][-1])

    fig, ax = figure((4.6, 2.2))
    ax.plot(ranks, full * 100, color=MUTED, lw=1, label="0: every rank fitted (as MATLAB)")
    ax.plot(ranks[fitted], stopped[fitted] * 100, color=ACCENT, lw=2.2,
            label="0.005 (default): the sweep stops")
    ax.axvline(last, color=ACCENT, ls=":", lw=1)
    ax.text(last - 0.8, 44, f"stops at rank {last} of {n_ch}:\npast 95%, so the\n"
            f"other {n_ch - last} ranks are skipped",
            color=ACCENT, fontsize=7, ha="right", va="bottom")
    ax.axhline(95, color=MUTED, ls="--", lw=0.8)
    ax.text(1, 96, "95%", ha="left", va="bottom", fontsize=7, color=MUTED)
    ax.set_xlabel("NMF rank")
    ax.set_ylabel("variance explained (%)")
    ax.set_ylim(0, 105)
    ax.set_xlim(0, ranks[-1] + 1)
    ax.legend(loc="lower right", frameon=False, fontsize=7, title="Stop NMF sweep below gain",
              title_fontsize=7)
    return save(fig, "nmf_plateau")


def sa_fit():
    """Unthresholded STTC against distance on an Axion64 grid, with both SA fits."""
    from meanap.pipeline.channel_layout import get_coords_from_layout, node_distances_in_pitches
    from meanap.pipeline.spatiotemporal import (
        _binned_correlation_profile, spatial_autocorrelation, spatial_autocorrelation_nugget,
        spatial_exponential_floor,
    )
    from meanap.pipeline.sttc import get_sttc

    rng = np.random.default_rng(8)
    channels, coords = get_coords_from_layout("Axion64")
    dist = node_distances_in_pitches("Axion64", channels)
    pitch_xy = coords / 8 * 7  # the 8x8 grid spans 0..8 drawing units = 0..7 pitches

    duration, lam_true = 120.0, 2.0
    n = len(channels)
    trains = [list(rng.uniform(0, duration, rng.poisson(0.8 * duration))) for _ in range(n)]
    # Local events: each starts somewhere on the array and recruits electrodes
    # with a probability that falls off with distance from its centre.
    for t in rng.uniform(0, duration, 400):
        centre = rng.uniform(0, 7, 2)
        d = np.linalg.norm(pitch_xy - centre, axis=1)
        p = 0.7 * np.exp(-d / lam_true)
        for ch in np.nonzero(rng.random(n) < p)[0]:
            trains[ch].append(t + rng.normal(0, 0.004))
    trains = {i: np.sort(np.clip(np.asarray(tr), 0, duration - 1e-6)) for i, tr in enumerate(trains)}
    sttc = get_sttc(trains, n, 25, duration)

    iu = np.triu_indices(n, 1)
    fig, ax = figure((4.6, 2.4))
    ax.scatter(dist[iu], sttc[iu], s=3, color=MUTED, alpha=0.25, edgecolor="none",
               label="electrode pairs")
    d_bin, c_bin = _binned_correlation_profile(sttc, dist, 20)
    ax.scatter(d_bin, c_bin, s=14, color=INK, zorder=3, label="mean per distance bin")
    lam, floor = spatial_autocorrelation(sttc, dist)
    lam_f, amp, floor_f = spatial_autocorrelation_nugget(sttc, dist)
    xs = np.linspace(0, dist[iu].max(), 200)
    ax.plot(xs, spatial_exponential_floor(xs, lam, floor), color=ACCENT_2, lw=1.4,
            label=f"pinned to 1 at d=0: SA_lambda = {lam:.2f}")
    if np.isfinite(lam_f):
        ax.plot(xs, amp * np.exp(-xs / lam_f) + floor_f, color=ACCENT, lw=1.6,
                label=f"free start: SA_lambda_free = {lam_f:.2f}")
    ax.set_xlabel("distance (electrode pitches)")
    ax.set_ylabel("STTC (unthresholded)")
    top = max(0.3, float(np.nanmax(c_bin)) * 2.5)
    ax.set_ylim(-0.02, top)
    ax.set_xlim(0, dist[iu].max() * 1.02)
    ax.legend(loc="upper right", frameon=False, fontsize=6.8, markerscale=1.5)
    return save(fig, "spatiotemporal")


# ── Stats & ML tab ────────────────────────────────────────────────────────────


def grouped_folds():
    """Culture-grouped cross-validation: every age of a culture shares a fold."""
    from sklearn.model_selection import StratifiedGroupKFold

    n_cultures, ages = 10, [7, 14, 21, 28]
    genotype = np.array(["WT"] * 5 + ["KO"] * 5)
    rows = [(c, a) for c in range(n_cultures) for a in ages]
    groups = np.array([c for c, _ in rows])
    y = genotype[groups]
    fold_of = np.empty(len(rows), dtype=int)
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for k, (_, test) in enumerate(splitter.split(np.zeros(len(rows)), y, groups)):
        fold_of[test] = k

    fig, ax = figure((4.6, 2.3))
    for i, (c, a) in enumerate(rows):
        ax.add_patch(Rectangle((ages.index(a) - 0.42, c - 0.4), 0.84, 0.8,
                               facecolor=PALETTE[fold_of[i]], alpha=0.85, edgecolor="white"))
    ax.set_xlim(-0.6, len(ages) - 0.4)
    ax.set_ylim(n_cultures - 0.5, -0.5)
    ax.set_xticks(range(len(ages)), [f"DIV {a}" for a in ages])
    ax.set_yticks(range(n_cultures), [f"{genotype[c]} culture {c % 5 + 1}" for c in range(n_cultures)],
                  fontsize=6.8)
    ax.tick_params(length=0)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_title("Colour = the CV fold each recording is tested in (5 folds)", fontsize=8)
    return save(fig, "stats_folds")


def main():
    return [
        channel_layouts(),
        sttc_tiles(),
        prob_threshold_null(),
        nmf_plateau(),
        sa_fit(),
        grouped_folds(),
    ]


if __name__ == "__main__":
    for p in main():
        print(p)
