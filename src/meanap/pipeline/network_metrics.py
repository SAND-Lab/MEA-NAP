"""Network metrics, ported from the Brain Connectivity Toolbox
(``Functions/2019_03_03_BCT/*.m``) as called by ``ExtractNetMet.m``.

Most of this module is *pure, deterministic functions of a fixed adjacency
matrix* — ND, NS, MEW, Dens, CC (raw), PL (raw), Eglob, Eloc, BC, NE, plus
``participation_coef`` (raw), ``module_degree_zscore``, and ``rich_club_wu``.
These (plus ``classify_node_cartography``, a simple deterministic threshold
classification of PC/Z) require a community assignment (``Ci``) as input —
deterministic *given* ``Ci``, but ``Ci`` itself comes from ``modularity.py``'s
consensus clustering, which is stochastic (see that module's docstring).

``participation_coef_norm`` is additionally stochastic on top of that — it
needs 100 iterations of degree-preserving network randomization
(``null_models.null_model_und_sign``, also not bit-reproducible against
MATLAB) to normalize the raw participation coefficient. **This is the
function whose first output MEA-NAP actually saves as ``NetMet.PC``** —
`participation_coef`'s raw formula is genuinely a different, deterministic
quantity, kept because it's independently useful and testable.

``small_worldness_rl_wu`` (``SW``/``SWw``, and the *saved* ``NetMet.CC``/
``NetMet.PL``) is likewise stochastic on top of its deterministic formula —
it needs a random (``null_models.randmio_und_v2``) and a lattice-like
(``null_models.latmio_und_v2``) null model built from the same adjacency
matrix to normalize against (10000/5000 rewiring iterations respectively,
matching ``ExtractNetMet.m``'s call site). This module's ``compute_network_
metrics`` (in ``step4.py``) keeps the *raw*, unnormalized clustering
coefficient / path length available too, under ``CC_raw``/``PL_raw`` — NOT
the same numbers MATLAB saves into ``NetMet.CC``/``NetMet.PL``, but
independently useful/testable deterministic quantities in their own right,
same relationship as ``PC``/``PC_raw``.

``num_nnmf_components``/``nComponentsRelNS``/``nnmf_residuals``/
``nnmf_var_explained`` (NMF-based dimensionality, port of ``calNMF.m``) live
in ``nmf.py`` rather than here, since they operate on spike times/matrices
rather than an adjacency matrix — **read that module's docstring**, this one
is not just RNG-stream-different from MATLAB but algorithm-different
(``sklearn``'s NMF solvers vs. MATLAB's built-in ``nnmf``), so even
``num_nnmf_components`` itself can legitimately differ, not just the
underlying factor matrices.

Still NOT ported (out of scope): spatial/temporal autocorrelation
(``SA_lambda``/``SA_inf``/``TA_regional``/``TA_global``) — these aren't in
MATLAB's own default ``netMetToCal`` list either (`AdvancedSettings.m` calls
them out as "other optional ones"), and the temporal-autocorrelation code
path is an explicit `% TODO` stub in `ExtractNetMet.m` itself, so there's no
complete MATLAB reference behavior to port yet. ``Cmcblty`` (communicability)
also needs no work: not actually computed by MATLAB's current pipeline
either, the code path that would call it (``fcn_find_hubs_wu.m``) is
commented out in ``ExtractNetMet.m``.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import schur
from scipy.sparse.linalg import svds

from meanap.pipeline.null_models import null_model_und_sign


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


# ── Participation coefficient (participation_coef_norm.m, raw/3rd output) ──

def participation_coef(w: np.ndarray, ci: np.ndarray) -> np.ndarray:
    """Raw (unnormalized) participation coefficient (Guimera & Amaral 2005).

    ``ci`` is a 1-indexed community affiliation vector (e.g. from
    ``modularity.mod_consensus_cluster_iterate``). This is the *3rd* output
    of MATLAB's ``participation_coef_norm.m`` — NOT the normalized value
    MEA-NAP saves as ``NetMet.PC`` (that requires 100 iterations of
    degree-preserving randomization on top of this).
    """
    n = w.shape[0]
    ko = w.sum(axis=1)
    gc = (w != 0) @ np.diag(ci)

    kc2 = np.zeros(n)
    for i in range(1, ci.max() + 1):
        kc2 += (w * (gc == i)).sum(axis=1) ** 2

    with np.errstate(divide="ignore", invalid="ignore"):
        pc = 1.0 - kc2 / (ko**2)
    pc[ko == 0] = 0.0
    return pc


def participation_coef_norm(
    w: np.ndarray, ci: np.ndarray, n_iter: int = 100, rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Normalized participation coefficient — **this is what MEA-NAP actually
    saves as ``NetMet.PC``**, and what colors
    ``4_MEA_NetworkPlotNodedegreeParticipationcoefficient.png``.

    Full port of ``participation_coef_norm.m``: computes the raw PC (same as
    :func:`participation_coef`), then runs ``n_iter`` degree-preserving
    network randomizations (``null_models.null_model_und_sign``) to measure
    how much of each node's raw PC is attributable to its module sizes alone
    vs. genuine cross-module diversity, and normalizes it out.

    **Not bit-reproducible against MATLAB** (the randomizations are
    stochastic) — see ``null_models.py``'s docstring. ``n_iter=100`` at
    ~59-64 nodes takes roughly 15-35s; budget for that per (recording, lag).

    Returns (PC_norm, PC_residual, PC, between_mod_k) — matching MATLAB's
    output order exactly (MEA-NAP's caller only keeps the first).
    """
    if rng is None:
        rng = np.random.default_rng()

    n = w.shape[0]
    ko = w.sum(axis=1)
    gc = (w != 0) @ np.diag(ci)
    pc = participation_coef(w, ci)

    within_mod_k = np.zeros(n)
    for i in range(1, ci.max() + 1):
        mask = ci == i
        within_mod_k[mask] = w[np.ix_(mask, mask)].sum(axis=1)
    between_mod_k = ko - within_mod_k

    kc2_rnd = np.zeros((n, n_iter))
    for it in range(n_iter):
        w_rnd = null_model_und_sign(w, bin_swaps=5, rng=rng)
        gc_rnd = (w_rnd != 0) @ np.diag(ci)
        kc2_rnd_loop = np.zeros(n)
        with np.errstate(divide="ignore", invalid="ignore"):
            for i in range(1, ci.max() + 1):
                term = (w * (gc == i)).sum(axis=1) / ko - (w_rnd * (gc_rnd == i)).sum(axis=1) / ko
                kc2_rnd_loop += term**2
        kc2_rnd[:, it] = np.sqrt(0.5 * kc2_rnd_loop)

    with np.errstate(invalid="ignore"):
        pc_norm = 1.0 - np.median(kc2_rnd, axis=1)
    pc_norm[ko == 0] = 0.0
    pc_norm = np.nan_to_num(pc_norm, nan=0.0)

    module_size = np.array([np.sum(ci == ci[j]) for j in range(n)], dtype=float)
    if n > 1 and np.std(module_size) > 0:
        p_coef = np.polyfit(module_size, pc, 1)
        yfit = np.polyval(p_coef, module_size)
        pc_residual = pc - yfit
    else:
        pc_residual = np.zeros(n)
    pc_residual[ko == 0] = 0.0

    return pc_norm, pc_residual, pc, between_mod_k


# ── Within-module degree z-score (module_degree_zscore.m) ──────────────────

def module_degree_zscore(w: np.ndarray, ci: np.ndarray) -> np.ndarray:
    """Within-module degree z-score (undirected graph, ``flag=0`` in MATLAB)."""
    n = w.shape[0]
    z = np.zeros(n)
    for i in range(1, ci.max() + 1):
        mask = ci == i
        koi = w[np.ix_(mask, mask)].sum(axis=1)
        std = koi.std(ddof=1) if len(koi) > 1 else 0.0
        with np.errstate(divide="ignore", invalid="ignore"):
            z[mask] = (koi - koi.mean()) / std
    return np.nan_to_num(z, nan=0.0)


# ── Rich club coefficient (rich_club_wu.m) ──────────────────────────────────

def rich_club_wu(adj_m: np.ndarray, k_level: int | None = None) -> np.ndarray:
    """Weighted rich-club coefficient curve, ``Rw[k-1]`` for k = 1..k_level.

    Two distinct sources of NaN, both faithfully reproduced from
    ``rich_club_wu.m`` even though the first looks like an odd condition to
    special-case: (1) MATLAB skips (leaves NaN) whenever *no* nodes have
    degree < k — i.e. when every node already qualifies, no filtering is
    needed, and the loop takes an early ``continue`` rather than computing
    normally; (2) at the highest k-levels, only 1-2 nodes survive the
    degree cutoff, giving zero edges among them (``Er=0``) and a genuine
    ``0/0`` MATLAB division producing NaN, reproduced here the same way
    (not special-cased to 0).
    """
    node_degree = np.count_nonzero(adj_m, axis=0)
    if k_level is None:
        k_level = int(node_degree.max()) if node_degree.size else 0

    wrank = np.sort(adj_m.ravel())[::-1]
    rw = np.full(k_level, np.nan)

    for kk in range(1, k_level + 1):
        small_nodes = node_degree < kk
        if not np.any(small_nodes):
            continue
        keep = ~small_nodes
        cutout = adj_m[np.ix_(keep, keep)]
        wr = cutout.sum()
        er = np.count_nonzero(cutout)
        wrank_r = wrank[:er]
        with np.errstate(invalid="ignore", divide="ignore"):
            rw[kk - 1] = wr / wrank_r.sum()

    return rw


# ── Node cartography classification (NodeCartography.m) ────────────────────

def classify_node_cartography(
    pc: np.ndarray,
    z: np.ndarray,
    hub_boundary_wm_d_deg: float,
    peri_part_coef: float,
    non_hub_connector_part_coef: float,
    pro_hub_part_coef: float,
    connector_hub_part_coef: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Classify each node into one of 6 cartography roles from PC/Z.

    Returns ``(nd_cart_div, pop_num_nc)``:

    - ``nd_cart_div``: ``(n,)`` int array, 1-6 per node — 1 Peripheral node,
      2 Non-hub connector, 3 Non-hub kinless node, 4 Provincial hub,
      5 Connector hub, 6 Kinless hub. 0 if a node doesn't fall in any region
      (shouldn't happen given MATLAB's boundaries are exhaustive, but a node
      can be missed if PC/Z are NaN).
    - ``pop_num_nc``: ``(6,)`` count of nodes in each role, 1-indexed by role.
    """
    n = len(pc)
    nd_cart_div = np.zeros(n, dtype=int)

    low_z = z <= hub_boundary_wm_d_deg
    high_z = z >= hub_boundary_wm_d_deg

    # Mirrors MATLAB's if/elseif chain: first matching condition wins, so a
    # node exactly on a boundary is resolved by *order*, not by whichever
    # mask happens to be applied last.
    conditions = [
        (1, low_z & (pc <= peri_part_coef)),
        (2, low_z & (pc >= peri_part_coef) & (pc <= non_hub_connector_part_coef)),
        (3, low_z & (pc >= non_hub_connector_part_coef)),
        (4, high_z & (pc <= pro_hub_part_coef)),
        (5, high_z & (pc >= pro_hub_part_coef) & (pc <= connector_hub_part_coef)),
        (6, high_z & (pc >= connector_hub_part_coef)),
    ]
    for role, mask in conditions:
        unassigned = nd_cart_div == 0
        nd_cart_div[mask & unassigned] = role

    pop_num_nc = np.array([int(np.sum(nd_cart_div == role)) for role in range(1, 7)])
    return nd_cart_div, pop_num_nc


# ── Hub classification (Hub3/Hub4, the ExtractNetMet.m inline block) ───────

def _matlab_round(x: float) -> int:
    """MATLAB's round(): half-away-from-zero, not Python's round-half-to-even."""
    return int(np.floor(x + 0.5)) if x >= 0 else -int(np.floor(-x + 0.5))


def hub_classification(
    nd: np.ndarray, pc: np.ndarray, bc: np.ndarray, ne: np.ndarray,
) -> tuple[float, float]:
    """Returns (Hub3, Hub4): fraction of nodes in the top 10% by >=3 / all 4
    of {node degree, participation coefficient, betweenness centrality,
    nodal efficiency}.

    Ties at the top-10% cutoff are all included (MATLAB uses value-based
    ``ismember`` against the top-N *values*, not a strict top-N *count*, so
    a tie can pull in more than ``round(aN/10)`` nodes) — reproduced here
    with ``np.isin`` for the same reason.
    """
    a_n = len(nd)
    n_top = _matlab_round(a_n / 10)

    def top_indices(values: np.ndarray) -> np.ndarray:
        threshold_vals = np.sort(values)[::-1][:n_top]
        return np.nonzero(np.isin(values, threshold_vals))[0]

    all_hubs = np.concatenate([
        top_indices(nd), top_indices(pc), top_indices(bc), top_indices(ne),
    ])
    counts = np.bincount(all_hubs, minlength=a_n)
    hub4 = float(np.sum(counts == 4) / a_n)
    hub3 = float(np.sum(counts >= 3) / a_n)
    return hub3, hub4


# ── Small-worldness (small_worldness_RL_wu.m) ──────────────────────────────

def small_worldness_rl_wu(
    a: np.ndarray, r: np.ndarray, l: np.ndarray,
) -> tuple[float, float, float, float]:
    """Small-worldness sigma/omega, port of ``small_worldness_RL_wu.m``.

    ``a`` is the real (sub-)network; ``r`` a degree-preserving random null
    model built from ``a`` (``null_models.randmio_und_v2``); ``l`` a
    lattice-like null model built from ``a`` (``null_models.latmio_und_v2``).
    Deterministic given fixed ``a``/``r``/``l`` — the stochasticity lives
    entirely in how ``r``/``l`` were generated (see ``null_models.py``).

    Returns ``(sw, sww, cc, pl)``:

    - ``sw``: sigma small-worldness, ``(C/Cr) / (PL/PLr)``. > 1 indicates
      small-world properties.
    - ``sww``: omega small-worldness, ``(PLr/PL) - (C/Cl)``, in [-1, 1].
      Close to 0 is small-world; close to 1 is random-like; close to -1 is
      lattice-like.
    - ``cc``: clustering coefficient normalized against the lattice model
      (``C/Cl``) — what MEA-NAP actually saves as ``NetMet.CC``.
    - ``pl``: path length normalized against the random model (``PL/PLr``)
      — what MEA-NAP actually saves as ``NetMet.PL``.
    """
    c = np.float64(np.mean(clustering_coef_wu(a)))
    cl = np.float64(np.mean(clustering_coef_wu(l)))
    cr = np.float64(np.mean(clustering_coef_wu(r)))

    pl, _ = charpath(distance_wei(weight_conversion_lengths(a)))
    plr, _ = charpath(distance_wei(weight_conversion_lengths(r)))
    pl, plr = np.float64(pl), np.float64(plr)

    # MATLAB divides these same quantities with no zero-guard, silently
    # producing Inf/NaN (e.g. when a null model happens to have zero
    # triangles) rather than erroring — match that with np.errstate + numpy
    # scalars rather than Python float division, which raises
    # ZeroDivisionError.
    with np.errstate(divide="ignore", invalid="ignore"):
        pl_norm = pl / plr
        pl_inv = plr / pl
        cc = c / cl
        sw = (c / cr) / (pl / plr)
        sww = pl_inv - cc

    return float(sw), float(sww), float(cc), float(pl_norm)


# ── Controllability ────────────────────────────────────────────────────────

def average_controllability(adj_m: np.ndarray) -> np.ndarray:
    """Returns values of average controllability for each node in a network.
    
    Port of ``ave_control.m`` (Bassett Lab, 2016). Average controllability
    measures the ease by which input at that node can steer the system into
    many easily-reachable states.
    """
    if adj_m.shape[0] == 0:
        return np.array([])
    
    try:
        _, s, _ = svds(adj_m.astype(float), k=1)
        max_s = s[0]
    except Exception:
        max_s = np.linalg.norm(adj_m, 2)
        
    a_norm = adj_m / (1 + max_s)
    t, u = schur(a_norm, output="real")
    
    mid_mat = (u ** 2).T
    v = np.diag(t)
    p_diag = 1 - v ** 2
    p = np.tile(p_diag[:, np.newaxis], (1, adj_m.shape[0]))
    
    return np.sum(mid_mat / p, axis=0)


def modal_controllability(adj_m: np.ndarray) -> np.ndarray:
    """Returns values of modal controllability for each node in a network.
    
    Port of ``modal_control.m`` (Bassett Lab, 2016). Modal controllability
    indicates the ability of that node to steer the system into
    difficult-to-reach states.
    """
    if adj_m.shape[0] == 0:
        return np.array([])
        
    try:
        _, s, _ = svds(adj_m.astype(float), k=1)
        max_s = s[0]
    except Exception:
        max_s = np.linalg.norm(adj_m, 2)
        
    a_norm = adj_m / (1 + max_s)
    t, u = schur(a_norm, output="real")
    
    
    eig_vals = np.diag(t)
    return (u ** 2) @ (1 - eig_vals ** 2)


# ── Effective Rank ─────────────────────────────────────────────────────────

def effective_rank(
    spike_times: list[np.ndarray],
    fs: float,
    duration_s: float,
    eff_fs: float,
    method: str = "covariance"
) -> float:
    """Computes Effective Rank of the network activity.
    
    Port of ``calEffRank.m`` (Roy and Vetterli, 2007).
    Constructs the dense binary spike matrix at `fs`, resamples it down to `eff_fs`
    using a polyphase FIR filter, and computes the Shannon entropy of the
    eigenvalues of the covariance/correlation matrix.
    """
    import scipy.signal as signal
    from scipy.sparse import csc_matrix
    from fractions import Fraction

    n_samples = int(np.ceil(duration_s * fs))
    n_channels = len(spike_times)
    
    indices_x = []
    indices_y = []
    for i, st in enumerate(spike_times):
        samples = np.round(st * fs).astype(int)
        samples = samples[(samples >= 0) & (samples < n_samples)]
        indices_x.extend(samples)
        indices_y.extend([i] * len(samples))
        
    activity = csc_matrix(
        (np.ones(len(indices_x)), (indices_x, indices_y)), 
        shape=(n_samples, n_channels)
    ).toarray()
    
    frac = Fraction(eff_fs).limit_denominator(1000000) / Fraction(fs).limit_denominator(1000000)
    p, q = frac.numerator, frac.denominator
    
    resampled = signal.resample_poly(activity, up=p, down=q, axis=0)
    
    if method.lower() in ("covariance", "ordinary"):
        cov_m = np.cov(resampled, rowvar=False)
    elif method.lower() == "correlation":
        cov_m = np.corrcoef(resampled, rowvar=False)
        cov_m[np.isnan(cov_m)] = 0.0
    else:
        raise ValueError(f"Unknown method {method}")
        
    eigen_v, _ = np.linalg.eigh(cov_m)
    # Filter out small negative eigenvalues due to numerical precision
    eigen_v = np.maximum(eigen_v, 0)
    
    total_eig = np.sum(eigen_v)
    if total_eig == 0:
        return float('nan')
        
    norm_eigen_v = eigen_v / total_eig
    # Avoid log(0)
    norm_eigen_v = norm_eigen_v[norm_eigen_v > 0]
    
    s_en = -np.sum(norm_eigen_v * np.log(norm_eigen_v))
    return float(np.exp(s_en))
