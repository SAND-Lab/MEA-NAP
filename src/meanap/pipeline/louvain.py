"""Louvain modularity optimization, port of ``community_louvain.m`` (BCT).

Single-run community detection. Inherently stochastic (random node
processing order each pass) — used as the building block for
``modularity.py``'s consensus-clustering wrapper, which stabilizes the
randomness across many runs. Not bit-reproducible against MATLAB (different
RNG stream) — see ``modularity.py``'s module docstring.
"""

from __future__ import annotations

import numpy as np


def community_louvain(
    w: np.ndarray, gamma: float = 1.0, rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, float]:
    """Returns (M, Q): community affiliation vector (1-indexed, like MATLAB) and modularity.

    Direct port of ``community_louvain.m``'s default ('modularity') path
    with no initial partition — matches how ``mod_consensus_cluster_iterate.m``
    always calls it (``community_louvain(adjM)``, no extra args). Renumbering
    of module labels happens exactly once per hierarchical level, after the
    local-moving phase fully converges — matching MATLAB's structure, not
    after every node sweep.
    """
    if rng is None:
        rng = np.random.default_rng()

    w = np.asarray(w, dtype=float)
    n = len(w)
    s = w.sum()
    if s == 0:
        return np.arange(1, n + 1), 0.0

    b = (w - gamma * np.outer(w.sum(axis=1), w.sum(axis=0)) / s) / s
    b = (b + b.T) / 2.0

    m = np.arange(n)   # final (across-hierarchy) community label per original node
    mb = np.arange(n)  # current level's community label

    hnm = np.zeros((n, n))
    for mod in range(mb.max() + 1):
        hnm[:, mod] = b[:, mb == mod].sum(axis=1)

    q0 = -np.inf
    q = b[np.equal.outer(m, m)].sum()  # m == arange(n) here: just trace(b)
    first_iteration = True

    while q - q0 > 1e-10:
        flag = True
        while flag:
            flag = False
            for u in rng.permutation(len(mb)):
                ma = mb[u]
                dq = hnm[u, :] - hnm[u, ma] + b[u, u]
                dq[ma] = 0.0
                mb_new = int(np.argmax(dq))
                max_dq = dq[mb_new]
                if max_dq > 1e-10:
                    flag = True
                    mb[u] = mb_new
                    hnm[:, mb_new] += b[:, u]
                    hnm[:, ma] -= b[:, u]

        _, mb = np.unique(mb, return_inverse=True)

        m0 = m.copy()
        if first_iteration:
            m = mb.copy()
            first_iteration = False
        else:
            for u in range(m0.max() + 1):
                m[m0 == u] = mb[u]

        n_mod = mb.max() + 1
        b1 = np.zeros((n_mod, n_mod))
        for u in range(n_mod):
            for v in range(u, n_mod):
                bm = b[np.ix_(mb == u, mb == v)].sum()
                b1[u, v] = bm
                b1[v, u] = bm
        b = b1

        mb = np.arange(n_mod)
        hnm = b.copy()

        q0 = q
        q = float(np.trace(b))

    return m + 1, float(q)  # +1 to match MATLAB's 1-indexed community labels
