"""Does the correlation structure among tracked cells survive across days?

The per-cell fingerprint asks whether *one* match is real, and answers weakly:
AUC 0.68 against a co-located different cell, which is not enough to decide an
individual match. This asks a different question of the same data -- whether the
**set** of matched cells preserves its correlation structure -- and answers it
far more strongly, because a whole matrix of edges averages out the noise that
swamps a single cell's row.

Measured over 259 day-pairs from 72 chains of the Mecp2 dataset:

============================  ======
matched cells                 +0.546
nearest-neighbour null        +0.033
AUC vs that null              0.939
============================  ======

and it decays with elapsed time -- +0.608 at a DIV gap under 8, +0.529 at 8-15,
+0.389 at 15-25 -- which is what a network that drifts rather than resets looks
like.

The distinction matters for how tracking gets used: individual matches are
uncertain, but the population of matches within a chain carries real network
structure. Network-level longitudinal analysis is on firmer ground than
per-cell claims.

**The null has to be spatial.** Shuffling cell identities at random gives AUC
0.987, which sounds better and means less: it destroys position as well as
identity, so it cannot separate "we tracked the right cells" from "nearby cells
have similar correlations". Swapping each matched cell for its nearest
neighbour holds position roughly fixed and varies only identity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Below this many shared cells an edge-weight correlation is too noisy to read:
#: eight cells give 28 edges.
MIN_SHARED_CELLS = 8

#: And below this many usable edges after dropping non-finite ones.
MIN_EDGES = 20


@dataclass
class NetworkStability:
    """One day-pair's answer, with the null it has to be read against."""

    n_shared: int
    n_edges: int
    edge_r: float = float("nan")
    null_r: float = float("nan")
    div_gap: int | None = None

    @property
    def usable(self) -> bool:
        return np.isfinite(self.edge_r)


def shared_indices(labels_a: np.ndarray, labels_b: np.ndarray
                   ) -> tuple[list[int], list[int], list[int]]:
    """Row indices of the cells tracked into both sessions, in one order."""
    index_a = {int(c): i for i, c in enumerate(labels_a) if c >= 0}
    index_b = {int(c): i for i, c in enumerate(labels_b) if c >= 0}
    shared = sorted(set(index_a) & set(index_b))
    return shared, [index_a[c] for c in shared], [index_b[c] for c in shared]


def subnetwork(corr: np.ndarray, rows: list[int]) -> np.ndarray:
    """The correlation matrix restricted to ``rows``, in that order."""
    return np.asarray(corr)[np.ix_(rows, rows)]


def _upper(matrix: np.ndarray) -> np.ndarray:
    return matrix[np.triu_indices(matrix.shape[0], 1)]


def _edge_corr(a: np.ndarray, b: np.ndarray) -> tuple[float, int]:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < MIN_EDGES or a[ok].std() < 1e-9 or b[ok].std() < 1e-9:
        return float("nan"), int(ok.sum())
    return float(np.corrcoef(a[ok], b[ok])[0, 1]), int(ok.sum())


def nearest_neighbour_rows(centroids: np.ndarray, rows: list[int]) -> list[int]:
    """For each row, the closest *other* cell -- the spatial null's stand-in."""
    out = []
    for j in rows:
        d = np.linalg.norm(centroids - centroids[j], axis=1)
        d[j] = np.inf
        out.append(int(np.argmin(d)))
    return out


def stability(corr_a: np.ndarray, corr_b: np.ndarray,
              labels_a: np.ndarray, labels_b: np.ndarray,
              centroids_b: np.ndarray, *, div_gap: int | None = None
              ) -> NetworkStability:
    """Edge-weight agreement across two days, and its spatial null."""
    shared, rows_a, rows_b = shared_indices(labels_a, labels_b)
    if len(shared) < MIN_SHARED_CELLS:
        return NetworkStability(n_shared=len(shared), n_edges=0, div_gap=div_gap)

    va = _upper(subnetwork(corr_a, rows_a))
    vb = _upper(subnetwork(corr_b, rows_b))
    edge_r, n_edges = _edge_corr(va, vb)

    null_rows = nearest_neighbour_rows(np.asarray(centroids_b, dtype=float), rows_b)
    null_r, _ = _edge_corr(va, _upper(subnetwork(corr_b, null_rows)))

    return NetworkStability(n_shared=len(shared), n_edges=n_edges,
                            edge_r=edge_r, null_r=null_r, div_gap=div_gap)


def edges_above(corr: np.ndarray, quantile: float = 0.9) -> tuple[np.ndarray, float]:
    """Edge list above a quantile of the finite weights, and that threshold.

    A quantile rather than a fixed weight: correlation scale shifts between
    recordings, and a fixed cut would draw a dense graph on one day and an empty
    one on the next purely from that.
    """
    vals = _upper(np.asarray(corr))
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return np.empty((0, 2), dtype=int), float("nan")
    thr = float(np.quantile(vals, quantile))
    iu = np.triu_indices(corr.shape[0], 1)
    keep = np.isfinite(corr[iu]) & (corr[iu] >= thr)
    return np.column_stack([iu[0][keep], iu[1][keep]]), thr


def plot_tracked_network(
    corrs: list[np.ndarray],
    labels: list[np.ndarray],
    centroids: list[np.ndarray],
    divs: list[int],
    *,
    quantile: float = 0.9,
    title: str = "",
    dest=None,
):
    """One panel per day: the tracked cells, in place, with their strongest edges.

    Every panel draws the **same cells in the same positions** -- those tracked
    through every session, laid out on their first day's coordinates -- so what
    changes between panels is the correlation structure and nothing else. Laying
    each day out on its own coordinates would confound drift in the network with
    drift in the field of view.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    # cells present in every session, so the panels are comparable
    present = [set(int(c) for c in lab if c >= 0) for lab in labels]
    shared = sorted(set.intersection(*present)) if present else []
    if len(shared) < MIN_SHARED_CELLS:
        return None

    rows = [[{int(c): i for i, c in enumerate(lab) if c >= 0}[c] for c in shared]
            for lab in labels]
    xy = np.asarray(centroids[0], dtype=float)[rows[0]]

    n = len(divs)
    fig, axs = plt.subplots(1, n, figsize=(3.1 * n, 3.4), squeeze=False)
    for k in range(n):
        ax = axs[0][k]
        sub = subnetwork(corrs[k], rows[k])
        edges, thr = edges_above(sub, quantile)
        if len(edges):
            segs = [[(xy[i, 1], xy[i, 0]), (xy[j, 1], xy[j, 0])] for i, j in edges]
            weights = np.array([sub[i, j] for i, j in edges], dtype=float)
            span = weights.max() - weights.min()
            width = 0.4 + 1.6 * ((weights - weights.min()) / span if span > 0
                                 else np.ones_like(weights))
            ax.add_collection(LineCollection(segs, linewidths=width,
                                             colors="#2c7fb8", alpha=.45))
        strength = np.nansum(np.where(np.isfinite(sub), sub, 0), axis=1) - 1.0
        ax.scatter(xy[:, 1], xy[:, 0], s=14 + 26 * _unit(strength),
                   c="#d62728", zorder=3, linewidths=0)
        ax.set_title(f"DIV{divs[k]}\n{len(edges)} edges ≥ {thr:+.2f}", fontsize=9)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.invert_yaxis()

    fig.suptitle(title or f"{len(shared)} cells tracked through every day",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    if dest is not None:
        fig.savefig(dest, dpi=140, bbox_inches="tight")
        plt.close(fig)
        return dest
    return fig


def _unit(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros_like(values)
    lo, hi = finite.min(), finite.max()
    out = (values - lo) / (hi - lo) if hi > lo else np.zeros_like(values)
    return np.nan_to_num(out, nan=0.0)


#: Node measures computed per day on the tracked subnetwork. Each is a way of
#: asking "what kind of node is this?", and they answer differently: a cell can
#: hold its strength while its role in the module structure changes completely.
NODE_METRICS = ("strength", "clustering", "betweenness", "participation",
                "module_z")

#: MEA-NAP's six cartography roles, 1-indexed as ``classify_node_cartography``
#: returns them.
ROLE_NAMES = {
    1: "peripheral", 2: "non-hub connector", 3: "non-hub kinless",
    4: "provincial hub", 5: "connector hub", 6: "kinless hub",
}


def node_metrics(corr: np.ndarray, *, quantile: float = 0.9,
                 seed: int = 0) -> dict:
    """Per-node measures and cartography role for one day's subnetwork.

    The correlation matrix is thresholded before anything graph-theoretic is
    computed: on a dense matrix every node is connected to every other and
    measures like betweenness and participation lose their meaning. The same
    quantile is used as for the drawn edges, so the picture and the numbers
    describe the same graph.

    Negative weights are clipped rather than kept: participation coefficient
    and within-module z-score are defined for positive weights, and a mix of
    signs makes a module's "total weight" meaningless.
    """
    from meanap.pipeline.louvain import community_louvain
    from meanap.pipeline.network_metrics import (
        betweenness_wei,
        clustering_coef_wu,
        module_degree_zscore,
        participation_coef,
        strengths_und,
    )

    w = np.asarray(corr, dtype=float).copy()
    n = w.shape[0]
    if n < 3:
        # too small for any graph measure to mean anything; the shape still has
        # to match, or the caller trips over a missing key
        return ({k: [None] * n for k in NODE_METRICS}
                | {"role": [0] * n, "n_modules": n, "modularity": 0.0})
    w[~np.isfinite(w)] = 0.0
    np.fill_diagonal(w, 0.0)
    w = np.clip(w, 0.0, None)

    vals = w[np.triu_indices(n, 1)]
    positive = vals[vals > 0]
    if positive.size:
        w[w < float(np.quantile(positive, quantile))] = 0.0

    out = {
        "strength": strengths_und(w),
        "clustering": clustering_coef_wu(w),
        "betweenness": betweenness_wei(w),
    }
    # Not wrapped in a bare except: falling back to a single module makes
    # participation identically zero and every node "peripheral", which reads
    # as perfect role stability while measuring nothing at all.
    ci, modularity = community_louvain(w, rng=np.random.default_rng(seed))
    out["participation"] = participation_coef(w, ci)
    out["module_z"] = module_degree_zscore(w, ci)

    result = {k: [None if not np.isfinite(v) else round(float(v), 4)
                  for v in np.asarray(out[k], dtype=float)] for k in NODE_METRICS}
    result["role"] = _roles(out["participation"], out["module_z"])
    result["n_modules"] = int(len(set(np.asarray(ci).tolist())))
    result["modularity"] = round(float(modularity), 4)
    return result


def _roles(pc: np.ndarray, z: np.ndarray) -> list[int]:
    """Cartography roles, on MEA-NAP's default boundaries.

    The pipeline re-places these boundaries from the whole batch's PC/Z
    distribution; a single chain's subnetwork is far too small for that, so the
    defaults are used and the roles are comparable *within* a chain rather than
    against a batch-wide classification.
    """
    from meanap.params import Params
    from meanap.pipeline.network_metrics import classify_node_cartography

    p = Params()
    roles, _counts = classify_node_cartography(
        np.asarray(pc, dtype=float), np.asarray(z, dtype=float),
        p.hub_boundary_wm_d_deg, p.peri_part_coef,
        p.non_hub_connector_part_coef, p.pro_hub_part_coef,
        p.connector_hub_part_coef)
    return [int(r) for r in roles]


def metric_stability(values_a: list, values_b: list) -> float:
    """How well a node measure agrees across two days, for the same cells."""
    a = np.asarray([np.nan if v is None else v for v in values_a], dtype=float)
    b = np.asarray([np.nan if v is None else v for v in values_b], dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 5 or a[ok].std() < 1e-12 or b[ok].std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def role_stability(roles_a: list, roles_b: list) -> dict:
    """Do cells keep their cartography role across days?

    Raw agreement is not readable on its own: these subnetworks are ~90%
    peripheral, so two *unrelated* labellings agree ~82% of the time. Cohen's
    kappa removes that floor — 0 is chance, 1 is perfect — and is the number to
    quote.
    """
    a = np.asarray(roles_a, dtype=int)
    b = np.asarray(roles_b, dtype=int)
    ok = (a > 0) & (b > 0)
    a, b = a[ok], b[ok]
    if a.size < 5:
        return {"n": int(a.size), "agreement": float("nan"),
                "kappa": float("nan"), "expected": float("nan")}

    observed = float((a == b).mean())
    labels = sorted(set(a.tolist()) | set(b.tolist()))
    expected = float(sum((a == r).mean() * (b == r).mean() for r in labels))
    kappa = ((observed - expected) / (1 - expected)
             if expected < 1 else float("nan"))
    return {"n": int(a.size), "agreement": round(observed, 4),
            "expected": round(expected, 4),
            "kappa": None if not np.isfinite(kappa) else round(float(kappa), 4)}


def metric_stability_null(values_a: list, values_b: list, *,
                          n_shuffles: int = 20, seed: int = 0) -> float:
    """What a node measure's across-day agreement looks like by chance.

    Shuffling which cell is which, holding both days' values fixed. Any
    correlation left is what the measure's distribution produces on its own.
    """
    rng = np.random.default_rng(seed)
    b = np.asarray([np.nan if v is None else v for v in values_b], dtype=float)
    out = []
    for _ in range(n_shuffles):
        r = metric_stability(values_a, list(rng.permutation(b)))
        if np.isfinite(r):
            out.append(r)
    return float(np.median(out)) if out else float("nan")
