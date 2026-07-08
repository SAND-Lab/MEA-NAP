"""Consensus-clustering modularity, port of ``mod_consensus_cluster_iterate.m``.

Runs Louvain community detection (``louvain.py``) many times, builds a
consensus co-classification matrix (Lancichinetti & Fortunato 2012), and
repeats on the thresholded consensus matrix until it becomes block-diagonal
(stable partition).

**Not bit-reproducible against MATLAB.** Louvain's local-moving phase visits
nodes in a random order each pass (``randperm`` in MATLAB, a different RNG
stream than Python's), so the specific community *labels* and even the
partition itself can differ between MATLAB and Python runs — same situation
as Step 3's probabilistic thresholding. What's expected to match is
*quality*: modularity Q should land in a similar range, and consensus
clustering should still converge to a stable, block-diagonal partition.
"""

from __future__ import annotations

import numpy as np

from meanap.pipeline.louvain import community_louvain


def consensus_coclassify(partitions: list[np.ndarray]) -> np.ndarray:
    """Co-classification matrix: fraction of partitions where i, j share a module."""
    stack = np.stack(partitions, axis=1)  # (n_nodes, n_partitions)
    n = stack.shape[0]
    d = np.zeros((n, n))
    for k in range(stack.shape[1]):
        labels = stack[:, k]
        d += (labels[:, None] == labels[None, :]).astype(float)
    return d / stack.shape[1]


def consensuscheck(d: np.ndarray) -> bool:
    """True if ``d`` is binary (only 0s and 1s) and symmetric (block-diagonal)."""
    if not np.allclose(d.sum(axis=0), d.sum(axis=1)):
        return False
    return bool(np.count_nonzero((d == 0) | (d == 1)) == d.size)


def mod_consensus_cluster_iterate(
    adj_m: np.ndarray,
    threshold: float = 0.4,
    rep_num: int = 50,
    rng: np.random.Generator | None = None,
    max_outer_iterations: int = 50,
) -> tuple[np.ndarray, float, int]:
    """Returns (Ci, Q, num_repeats): consensus community affiliation + modularity.

    ``max_outer_iterations`` is a safety cap not present in MATLAB (which
    loops unconditionally until block-diagonal) — consensus clustering on
    real data converges in a handful of iterations; this just prevents a
    pathological input from hanging forever.
    """
    if rng is None:
        rng = np.random.default_rng()

    n = adj_m.shape[0]
    if n < 2:
        return np.ones(max(n, 1), dtype=int), 0.0, 0

    m = [community_louvain(adj_m, rng=rng)[0] for _ in range(rep_num)]
    d = consensus_coclassify(m)
    d[d < threshold] = 0.0

    num_repeats = 0
    block_diag = False
    b = m  # fallback if the loop never executes (shouldn't happen for n>=2)
    q_list = [0.0] * rep_num

    while not block_diag and num_repeats < max_outer_iterations:
        b = []
        q_list = []
        for _ in range(rep_num):
            ci, q = community_louvain(d, rng=rng)
            b.append(ci)
            q_list.append(q)

        d = consensus_coclassify(b)
        d[d < threshold] = 0.0

        num_repeats += 1
        block_diag = consensuscheck(d)

    return b[0], q_list[0], num_repeats
