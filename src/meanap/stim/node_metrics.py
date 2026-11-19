"""Node metrics of the baseline, evoked and post-stimulus networks.

The stimulus networks (:mod:`meanap.stim.evoked_network`) give each epoch an
STTC matrix, its trial-shuffle mean and its significance-thresholded
version. Each makes a different network, and they answer different questions
(the same two views MEA-Sim tells apart):

``significant``   only edges above the trial-shuffle null — what step 3
                  keeps, so comparable with the rest of MEA-NAP.
``coactivation``  every pair, weighted by its trial-averaged STTC: are these
                  nodes active together, for whatever reason — the response
                  to the stimulus included.
``beyond``        every pair, weighted by how far its STTC is above the trial
                  shuffle: co-variation *beyond* what each node's own
                  stimulus-locked response explains. The stimulus is common
                  input to every responding node, as a network burst is; this
                  is the stim counterpart of MEA-Sim's "STTC above jitter
                  expectation".

                  The excess is soft-thresholded at ``BEYOND_K`` (2) SDs of the
                  shuffle: ``max(STTC − mean − 2·SD, 0)``. Setting negatives to
                  0 alone keeps the positive half of the noise, about 0.4 SD a
                  pair — and the noise is far larger in a sparse pre-stimulus
                  window than in a busy evoked one, so plain clipping makes
                  strength *fall* during stimulation for nodes that only share
                  the response. The soft threshold keeps ~0.01 SD of noise. Its
                  price: a real excess is reported 2 SD smaller, a little more
                  so in the sparser window.

Every weighting goes through step 4's own
:func:`~meanap.pipeline.step4.compute_network_metrics` (small-worldness left
out: it is not a node metric and is the slow part on a dense network), so a
node's strength, controllability or participation here means what it means
in a step-4 run. Firing rate in the epoch is kept beside them: an epoch's
metric change that only follows its rate change is the first thing to rule
out.
"""

from __future__ import annotations

import numpy as np

__all__ = ["WEIGHTINGS", "NODE_METRICS", "FIGURE_METRICS", "weights", "epoch_node_metrics",
           "summarise_recordings", "paired_tests"]

WEIGHTINGS = {
    "significant": "Significant STTC",
    "coactivation": "Co-activation (all STTC)",
    "beyond": "Beyond the response (STTC − shuffle)",
}

#: Saved per node, in this order (``rate_hz`` first, then step 4's names).
NODE_METRICS = {
    "rate_hz": "Firing rate (Hz)",
    "ND": "Node degree",
    "NS": "Node strength",
    "aveControl": "Average controllability",
    "modalControl": "Modal controllability",
    "PC": "Participation coefficient",
    "Z": "Within-module degree z",
    "BC": "Betweenness centrality",
    "Eloc": "Local efficiency",
    "NE": "Nodal efficiency",
    "CC_raw": "Clustering coefficient",
}

#: The columns of figure 17.
FIGURE_METRICS = ("NS", "aveControl", "PC", "BC", "Eloc")


#: Soft threshold of the ``beyond`` weighting, in shuffle SDs.
BEYOND_K = 2.0


def weights(sttc: np.ndarray, sttc_thr: np.ndarray, null_mean: np.ndarray,
            weighting: str, null_sd: np.ndarray | None = None) -> np.ndarray:
    """The edge weights of one weighting (NaN rows/columns kept as they are)."""
    if weighting == "significant":
        w = np.array(sttc_thr, float)
    elif weighting == "coactivation":
        w = np.array(sttc, float)
    elif weighting == "beyond":
        w = np.array(sttc, float) - np.nan_to_num(np.array(null_mean, float))
        if null_sd is not None:
            w = w - BEYOND_K * np.nan_to_num(np.array(null_sd, float))
    else:
        raise ValueError(f"Unknown weighting {weighting!r}; expected one of {list(WEIGHTINGS)}")
    w[w < 0] = 0.0
    return w


def epoch_node_metrics(w: np.ndarray, spike_counts: np.ndarray, duration_s: float,
                       keep: np.ndarray, params, rng) -> np.ndarray:
    """``(len(NODE_METRICS), n)``: every node metric of one network, NaN for
    nodes left out (*keep* False) or below the activity threshold, and for the
    metrics undefined on a node with no edges (its degree and strength are 0)."""
    from meanap.pipeline.step4 import compute_network_metrics

    n = len(keep)
    out = np.full((len(NODE_METRICS), n), np.nan)
    kept = np.nonzero(keep)[0]
    counts = np.asarray(spike_counts, float)
    if duration_s and duration_s > 0:
        out[0, kept] = counts[kept] / duration_s
    if kept.size < 3 or not duration_s or duration_s <= 0:
        return out
    sub = np.nan_to_num(np.asarray(w, float)[np.ix_(kept, kept)])
    np.fill_diagonal(sub, 0.0)
    m = compute_network_metrics(sub, counts[kept], duration_s, params.min_activity_level, 3,
                                params=params, rng=rng, small_world=False)
    idx = kept[np.asarray(m.get("activeChannelIndex", []), int)]
    # Degree and strength straight from the weights, over the active nodes (as
    # step 4 defines them), so they exist even when step 4 declines a network
    # of fewer than 3 connected nodes — and an active node with no edges has
    # degree and strength 0, a real value a change can start or end at. The
    # rest (participation, betweenness, …) need step 4 and stay NaN without it.
    names = list(NODE_METRICS)
    active = kept[counts[kept] / duration_s >= params.min_activity_level]
    wa = np.nan_to_num(np.asarray(w, float)[np.ix_(active, active)])
    np.fill_diagonal(wa, 0.0)
    out[names.index("NS"), active] = wa.sum(axis=0)
    out[names.index("ND"), active] = (wa > 0).sum(axis=0)
    for r, key in enumerate(NODE_METRICS):
        if key in ("rate_hz", "NS", "ND"):
            continue
        v = m.get(key)
        if v is not None and np.ndim(v) == 1 and len(v) == len(idx):
            out[r, idx] = np.asarray(v, float)
    return out


# ── across recordings ────────────────────────────────────────────────────────

#: Per recording × condition × lag × weighting, for each metric:
#: ``<metric>_baseline``, ``_evoked``, ``_post`` (medians over nodes) and
#: ``<metric>_change`` (median over nodes of evoked − baseline).
SUMMARY_KEYS = ("FileName", "Grp", "DIV", "condition", "lag_ms", "weighting")


def summarise_recordings(node_rows: list[dict]) -> list[dict]:
    """One row per recording × condition × lag × weighting from the node table.

    Nodes are summarised by their median, so a few electrodes with extreme
    values do not decide a recording; the change is the median of each node's
    own evoked − baseline difference, which keeps the pairing within nodes.
    Stimulating electrodes are left out.
    """
    import pandas as pd

    if not node_rows:
        return []
    df = pd.DataFrame(node_rows)
    df = df[~df["stim_electrode"].astype(bool)]
    metrics = [m for m in NODE_METRICS if m in df.columns]
    out = []
    for keys, sub in df.groupby(list(SUMMARY_KEYS), sort=False, dropna=False):
        row = dict(zip(SUMMARY_KEYS, keys))
        wide = sub.pivot_table(index="node", columns="epoch", values=metrics, aggfunc="first")
        row["n_nodes"] = int(sub["node"].nunique())
        for m in metrics:
            for ep in ("baseline", "evoked", "post"):
                col = (m, ep)
                row[f"{m}_{ep}"] = (float(np.nanmedian(wide[col]))
                                    if col in wide and wide[col].notna().any() else np.nan)
            if (m, "baseline") in wide and (m, "evoked") in wide:
                d = (wide[(m, "evoked")] - wide[(m, "baseline")]).to_numpy(float)
                row[f"{m}_change"] = float(np.nanmedian(d)) if np.isfinite(d).any() else np.nan
                row[f"{m}_fracUp"] = (float(np.mean(d[np.isfinite(d)] > 0))
                                      if np.isfinite(d).any() else np.nan)
        out.append(row)
    return out


def paired_tests(summary_rows: list[dict]) -> list[dict]:
    """Evoked vs baseline across recordings, per group × DIV × condition × lag ×
    weighting × metric: a Wilcoxon signed-rank test on the recordings' node
    medians (each recording a pair). With fewer than 6 recordings the test
    cannot reach p < 0.05 and ``p`` is left blank, though the counts stay."""
    import pandas as pd
    from scipy.stats import wilcoxon

    if not summary_rows:
        return []
    df = pd.DataFrame(summary_rows)
    metrics = [m for m in NODE_METRICS if f"{m}_change" in df.columns]
    out = []
    for keys, sub in df.groupby(["Grp", "DIV", "condition", "lag_ms", "weighting"],
                                sort=False, dropna=False):
        for m in metrics:
            b = sub[f"{m}_baseline"].to_numpy(float)
            e = sub[f"{m}_evoked"].to_numpy(float)
            ok = np.isfinite(b) & np.isfinite(e)
            d = e[ok] - b[ok]
            p = np.nan
            if ok.sum() >= 6 and np.any(d != 0):
                p = float(wilcoxon(e[ok], b[ok]).pvalue)
            out.append({"Grp": keys[0], "DIV": keys[1], "condition": keys[2], "lag_ms": keys[3],
                        "weighting": keys[4], "metric": m, "n_recordings": int(ok.sum()),
                        "median_baseline": float(np.median(b[ok])) if ok.any() else np.nan,
                        "median_evoked": float(np.median(e[ok])) if ok.any() else np.nan,
                        "median_change": float(np.median(d)) if ok.any() else np.nan,
                        "n_up": int(np.sum(d > 0)), "n_down": int(np.sum(d < 0)),
                        "wilcoxon_p": p})
    return out
