"""Deterministic network metrics, ported from the Brain Connectivity Toolbox
(``Functions/2019_03_03_BCT/*.m``) as called by ``ExtractNetMet.m``.

Only metrics that are *pure, deterministic functions of a fixed adjacency
matrix* are ported here. ``ExtractNetMet.m`` also computes several metrics
that depend on randomized null models or community detection — those are
NOT bit-reproducible even across two MATLAB runs of the same data, and are
out of scope for this module:

- ``SW`` / ``SWw`` (small-worldness) and the *saved* ``CC`` / ``PL`` fields
  — MATLAB computes these via ``small_worldness_RL_wu``, which normalizes
  against randomized (``randmio_und_v2``) and lattice (``latmio_und_v2``)
  null models (10000/5000 rewiring iterations). This module's ``CC``/``PL``
  are the *raw*, unnormalized clustering coefficient / path length (what
  ``small_worldness_RL_wu`` calls ``C`` and ``PL`` internally, before
  dividing by the null models) — NOT the same numbers MATLAB saves into
  ``NetMet``.
- ``Q`` / ``Ci`` / ``nMod`` (modularity, via consensus clustering)
- ``PC`` / ``PC_raw`` / ``Z`` (participation coefficient, within-module
  z-score — both depend on the module assignment ``Ci`` above)
- ``Hub3`` / ``Hub4`` (depend on PC/Z)
- ``RC`` (rich club coefficient), ``Cmcblty`` (communicability)
"""

from __future__ import annotations

import numpy as np


# ── Weight conversion (weight_conversion.m) ────────────────────────────────

def weight_conversion_lengths(w: np.ndarray) -> np.ndarray:
    """Invert nonzero weights to lengths: ``L[E] = 1/W[E]``."""
    length = w.copy().astype(float)
    nonzero = length != 0
    length[nonzero] = 1.0 / length[nonzero]
    return length


def weight_conversion_normalize(w: np.ndarray) -> np.ndarray:
    """Rescale by the maximal absolute weight."""
    max_abs = np.max(np.abs(w))
    if max_abs == 0:
        return w.copy()
    return w / max_abs


# ── Node degree / edge weight (findNodeDegEdgeWeight.m) ────────────────────

def find_node_deg_edge_weight(
    adj_m: np.ndarray, edge_thresh: float | list[float] = 0.0001, exclude_zeros: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (ND, MEW): mean node degree and mean edge weight per node."""
    n = adj_m.shape[0]
    if n == 0:
        return np.zeros(0), np.zeros(0)

    thresholds = np.atleast_1d(edge_thresh)
    degree_vec = np.zeros((n, len(thresholds)))
    for count, cutoff in enumerate(thresholds):
        edges = adj_m - np.eye(n)
        edges = np.nan_to_num(edges, nan=0.0)
        edges = (edges >= cutoff).astype(float)
        degree_vec[:, count] = edges.sum(axis=0)
    nd = np.round(degree_vec.mean(axis=1))

    weights = adj_m - np.eye(n)
    weights = np.nan_to_num(weights, nan=0.0)
    weights[weights < 0] = 0.0
    if exclude_zeros:
        weights = np.where(weights == 0, np.nan, weights)
    with np.errstate(invalid="ignore"):
        mew = np.nanmean(weights, axis=0)

    return nd, mew


def strengths_und(adj_m: np.ndarray) -> np.ndarray:
    """Node strength: sum of edge weights connected to each node."""
    return adj_m.sum(axis=0)


# ── Density (density_und.m) ────────────────────────────────────────────────

def density_und(adj_m: np.ndarray) -> float:
    n = adj_m.shape[0]
    if n < 2:
        return 0.0
    k = np.count_nonzero(np.triu(adj_m))
    return k / ((n**2 - n) / 2)


# ── Clustering coefficient (clustering_coef_wu.m) ──────────────────────────

def clustering_coef_wu(w: np.ndarray) -> np.ndarray:
    """Weighted clustering coefficient (geometric mean of triangle intensities)."""
    k = np.count_nonzero(w, axis=1).astype(float)
    cyc3 = np.diag(np.linalg.matrix_power(w ** (1 / 3), 3))
    k[cyc3 == 0] = np.inf
    with np.errstate(invalid="ignore", divide="ignore"):
        c = cyc3 / (k * (k - 1))
    return np.nan_to_num(c, nan=0.0)


# ── Distances (distance_wei.m) + characteristic path length (charpath.m) ──

def distance_wei(length_mat: np.ndarray) -> np.ndarray:
    """Dijkstra shortest-path distance matrix from a connection-length matrix."""
    n = length_mat.shape[0]
    d = np.full((n, n), np.inf)
    np.fill_diagonal(d, 0.0)

    for u in range(n):
        temporary = np.ones(n, dtype=bool)
        l1 = length_mat.copy()
        active = [u]
        while True:
            for v in active:
                temporary[v] = False
                l1[:, v] = 0.0
            for v in active:
                neighbours = np.nonzero(l1[v, :])[0]
                if len(neighbours) == 0:
                    continue
                candidate = d[u, v] + l1[v, neighbours]
                better = candidate < d[u, neighbours]
                d[u, neighbours[better]] = candidate[better]

            remaining = d[u, temporary]
            if remaining.size == 0:
                break
            min_d = remaining.min()
            if np.isinf(min_d):
                break
            active = np.nonzero((d[u, :] == min_d) & temporary)[0].tolist()

    return d


def charpath(d: np.ndarray) -> tuple[float, float]:
    """Returns (lambda, efficiency): mean shortest path length + mean inverse.

    Matches ``charpath(D, 0, 0)``: excludes the diagonal and infinite
    (disconnected) path lengths from both statistics.
    """
    n = d.shape[0]
    mask = ~np.eye(n, dtype=bool)
    finite = mask & np.isfinite(d)
    dv = d[finite]
    if dv.size == 0:
        return np.nan, np.nan
    lam = float(np.mean(dv))
    efficiency = float(np.mean(1.0 / dv))
    return lam, efficiency


# ── Efficiency (efficiency_wei.m) ──────────────────────────────────────────

def _distance_inv_wei(w: np.ndarray) -> np.ndarray:
    d = distance_wei(w)
    with np.errstate(divide="ignore"):
        d_inv = 1.0 / d
    np.fill_diagonal(d_inv, 0.0)
    return d_inv


def efficiency_wei_global(w: np.ndarray) -> float:
    n = w.shape[0]
    if n < 2:
        return 0.0
    length_mat = weight_conversion_lengths(w)
    di = _distance_inv_wei(length_mat)
    return float(di.sum() / (n**2 - n))


def efficiency_wei_local(w: np.ndarray) -> np.ndarray:
    """Modified local efficiency (``efficiency_wei(W, 2)``), for normalized ``W``."""
    n = w.shape[0]
    a_bool = w > 0
    a = a_bool.astype(float)
    length_mat = weight_conversion_lengths(w)
    cbrt_w = w ** (1 / 3)
    cbrt_l = length_mat ** (1 / 3)

    e = np.zeros(n)
    for u in range(n):
        v = np.nonzero(a_bool[u, :] | a_bool[:, u])[0]
        if len(v) == 0:
            continue
        sw = cbrt_w[u, v] + cbrt_w[v, u]
        di = _distance_inv_wei(cbrt_l[np.ix_(v, v)])
        se = di + di.T
        numer = np.sum(np.outer(sw, sw) * se) / 2
        if numer != 0:
            sa = a[u, v] + a[v, u]
            denom = np.sum(sa) ** 2 - np.sum(sa**2)
            if denom != 0:
                e[u] = numer / denom
    return e


# ── Betweenness centrality (betweenness_wei.m) ─────────────────────────────

def betweenness_wei(g: np.ndarray) -> np.ndarray:
    """Node betweenness centrality (Brandes' algorithm) from a length matrix."""
    n = g.shape[0]
    bc = np.zeros(n)

    for u in range(n):
        d = np.full(n, np.inf)
        d[u] = 0.0
        num_paths = np.zeros(n)
        num_paths[u] = 1.0
        temporary = np.ones(n, dtype=bool)
        pred = np.zeros((n, n), dtype=bool)
        order: list[int] = []

        g1 = g.copy()
        active = [u]
        while True:
            for v in active:
                temporary[v] = False
                g1[:, v] = 0.0
            for v in active:
                order.append(v)
                w_idx = np.nonzero(g1[v, :])[0]
                for w in w_idx:
                    d_uw = d[v] + g1[v, w]
                    if d_uw < d[w]:
                        d[w] = d_uw
                        num_paths[w] = num_paths[v]
                        pred[w, :] = False
                        pred[w, v] = True
                    elif d_uw == d[w]:
                        num_paths[w] += num_paths[v]
                        pred[w, v] = True

            remaining_d = d[temporary]
            if remaining_d.size == 0:
                break
            min_d = remaining_d.min()
            if np.isinf(min_d):
                unreached = np.nonzero(np.isinf(d) & temporary)[0]
                order.extend(unreached.tolist())
                break
            active = np.nonzero((d == min_d) & temporary)[0].tolist()

        dependency = np.zeros(n)
        # Iterate all but the source, in reverse Dijkstra finishing order
        for w in reversed(order):
            if w == u:
                continue
            bc[w] += dependency[w]
            preds = np.nonzero(pred[w, :])[0]
            for v in preds:
                if num_paths[w] != 0:
                    dependency[v] += (1 + dependency[w]) * num_paths[v] / num_paths[w]

    return bc
