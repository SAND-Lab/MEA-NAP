"""Non-negative matrix factorization dimensionality metrics, port of
``calNMF.m`` (called from ``ExtractNetMet.m`` for the ``num_nnmf_components``
/``nComponentsRelNS``/``nnmf_residuals``/``nnmf_var_explained`` fields).

**Not bit-reproducible against MATLAB, and not even algorithm-identical** —
unlike the rest of this port, this isn't just "same algorithm, independent
RNG stream". MATLAB's built-in ``nnmf`` defaults to Alternating Least
Squares; this module uses ``sklearn.decomposition.NMF`` (coordinate
descent), the closest available equivalent in the Python scientific stack.
Different NMF solvers can converge to different local optima and even pick
a different ``num_nnmf_components`` for the same input, since that value
depends on where each solver's reconstruction residual happens to cross the
shuffled-data reference residual. The *control flow* (search for the number
of components by comparing residuals against a phase-randomized reference,
then sweep every possible rank up to the active-electrode count) is a
faithful port; the underlying factorization is not.

Also diverges from ``calNMF.m`` in one deliberate way for tractability: MATLAB
builds the phase-randomized ("wrap") spike matrix at the *native* sampling
rate first (``spikeTimesToSpikeMatrix`` at ``fs``, potentially tens of
millions of rows for a long recording) and only downsamples afterward
(``downSampleSum``). This module bins spike times directly into the final
downsampled time bins — mathematically identical whenever the native
matrix's row count is evenly divisible by the downsampled bin count (the
same condition MATLAB's ``reshape``-based ``downSampleSum`` silently
requires to not error), while avoiding ever materializing that huge
intermediate array.
"""

from __future__ import annotations

import warnings
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from itertools import islice

import numpy as np
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from meanap.pipeline.parallel import compute_threads


def randomise_spike_train(
    spike_times: np.ndarray, duration_s: float, rng: np.random.Generator,
) -> np.ndarray:
    """Circularly "wrap" a spike train around a random cut point, port of
    ``randomiseSpikeTrain.m``'s ``'wrap'`` method.
    """
    if len(spike_times) == 0:
        return spike_times
    cut_time = rng.random() * duration_s
    before = spike_times < cut_time
    out = np.empty_like(spike_times)
    out[before] = (duration_s - cut_time) + spike_times[before]
    out[~before] = spike_times[~before] - cut_time
    return out


def _bin_spike_times(spike_times_list: list[np.ndarray], duration_s: float, n_bins: int) -> np.ndarray:
    """Bin each channel's spike times into ``n_bins`` equal-width bins
    spanning ``[0, duration_s]``. Combined ``spikeTimesToSpikeMatrix`` (at
    native ``fs``) + ``downSampleSum`` from ``calNMF.m``, computed directly
    at the target resolution — see module docstring.
    """
    n_channels = len(spike_times_list)
    bin_edges = np.linspace(0.0, duration_s, n_bins + 1)
    out = np.zeros((n_bins, n_channels))
    for ch, times in enumerate(spike_times_list):
        if len(times) == 0:
            continue
        out[:, ch], _ = np.histogram(times, bins=bin_edges)
    return out


def _draw_seed(rng: np.random.Generator) -> int:
    """One fit's ``random_state``, drawn exactly as ``_nnmf`` always drew it.

    Seeds are drawn one call at a time and in rank order, never as an array:
    an array draw takes a different path through the generator, so the seeds
    (and every fit) would change.
    """
    return int(rng.integers(0, 2**31 - 1))


def _nnmf_seeded(x: np.ndarray, k: int, seed: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Rank-``k`` NNMF of ``x``, matching MATLAB's ``[W,H,D] = nnmf(A,k)``
    output convention: ``D`` is the root-mean-square residual
    ``norm(A - W*H, 'fro') / sqrt(m*n)``, not sklearn's raw Frobenius error.

    Uses ``init="random"``. (``init="nndsvda"`` was benchmarked and is ~8%
    *slower* here despite converging in fewer iterations: cal_nmf runs ~N fits
    on the same matrix for the per-rank sweep, and NNDSVD pays an SVD-based
    init cost on every fit that outweighs the convergence gain. NMF here is
    fit-count-bound, not init-bound.)

    Falls back to a large residual (rather than raising) on numerical
    failure — matching ``calNMF.m``'s own defensive early-exit on a failed
    ``nnmf`` call, just via Python's exception mechanism instead of
    MATLAB's ``lastwarn`` check (which targets a warning ID that doesn't
    appear to correspond to any warning MATLAB's ``nnmf`` actually raises).
    """
    m, n = x.shape
    k = max(1, min(k, m, n))
    try:
        model = NMF(n_components=k, init="random", solver="cd", max_iter=100, random_state=seed)
        w = model.fit_transform(x)
        h = model.components_
        d = model.reconstruction_err_ / np.sqrt(m * n)
    except Exception:
        w = np.zeros((m, k))
        h = np.zeros((k, n))
        d = float("inf")
    return w, h, float(d)


def _nnmf(x: np.ndarray, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, float]:
    """:func:`_nnmf_seeded` with the next seed from ``rng``."""
    return _fit_all([(x, k, _draw_seed(rng))], 1)[0]


def _quiet_single_blas():
    """Context for running fits: BLAS on one thread, ConvergenceWarning off.

    BLAS is held to one thread for every fit, threaded or not. A multi-threaded
    BLAS splits its sums differently for different thread counts, which moves
    the factors in the last bits, and the fits amplify that. With one BLAS
    thread a fit no longer depends on how many cores the machine has or on how
    many fits run at once.

    Not reaching full convergence within the bounded iteration count is
    expected and tolerated, as with MATLAB's own ALS default, so sklearn's
    ConvergenceWarning is silenced. That has to happen in the calling thread,
    once: ``warnings.catch_warnings`` swaps process-wide state, so entering it
    from several fit threads at once can leak warnings or leave the filter
    changed.
    """
    stack = ExitStack()
    stack.enter_context(warnings.catch_warnings())
    stack.enter_context(threadpool_limits(limits=1, user_api="blas"))
    warnings.simplefilter("ignore", category=ConvergenceWarning)
    return stack


def _fit_all(jobs: list[tuple[np.ndarray, int, int]], workers: int) -> list:
    """Run ``_nnmf_seeded`` on each ``(x, k, seed)``; results in job order.

    Every fit has its own seed, so running them on threads changes nothing but
    the wall time. sklearn's coordinate-descent update releases the GIL, so the
    threads do run in parallel.
    """
    with _quiet_single_blas():
        if workers <= 1 or len(jobs) <= 1:
            return [_nnmf_seeded(*job) for job in jobs]
        with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as ex:
            return list(ex.map(lambda job: _nnmf_seeded(*job), jobs))


def _sweep_fit(x: np.ndarray, k: int, seed: int) -> tuple[int, np.ndarray, np.ndarray, float, float]:
    """One rank of the per-rank sweep: the rank, its fit and variance explained."""
    w, h, res = _nnmf_seeded(x, k, seed)
    return k, w, h, res, _variance_explained(x, w, h)


def _fit_in_order(jobs: list[tuple[np.ndarray, int, int]], workers: int,
                  consume: Callable[[tuple], bool]) -> None:
    """Run ``_sweep_fit`` on each job, handing results to ``consume`` in order.

    Up to ``workers`` fits run at once, and a new one starts as soon as the
    oldest is consumed, so a slow fit does not hold up a whole batch. When
    ``consume`` returns False the remaining jobs are dropped (fits already
    running finish and are discarded).
    """
    with _quiet_single_blas():
        if workers <= 1:
            for job in jobs:
                if not consume(_sweep_fit(*job)):
                    return
            return
        with ThreadPoolExecutor(max_workers=workers) as ex:
            queued = iter(jobs)
            running = deque(ex.submit(_sweep_fit, *job) for job in islice(queued, workers))
            try:
                while running:
                    result = running.popleft().result()
                    nxt = next(queued, None)
                    if nxt is not None:
                        running.append(ex.submit(_sweep_fit, *nxt))
                    if not consume(result):
                        return
            finally:
                for fut in running:
                    fut.cancel()


def _variance_explained(x: np.ndarray, w: np.ndarray, h: np.ndarray) -> float:
    """``calNMF.m``'s variance explained: 1 - SS_res / SS_tot about the grand mean."""
    ss_res = np.sum((w @ h - x) ** 2)
    ss_tot = np.sum((x - x.mean()) ** 2)
    return (1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


#: Ranks over which ``cal_nmf``'s early stop judges that variance explained
#: has levelled off.
PLATEAU_WINDOW = 10


def _levelled_off(var_explained: np.ndarray, gain: float, threshold_reached: bool) -> bool:
    """Whether the per-rank sweep can stop after the ranks fitted so far.

    True once the curve has passed the 95% threshold, or once the best value
    over the last ``PLATEAU_WINDOW`` ranks beats the best before them by less
    than ``gain``. The maxima, not the last values, are compared because the
    curve is not monotonic: each rank is an independent fit from a random
    start, and a high rank that fails to converge can drop well below a lower
    one.
    """
    if threshold_reached:
        return True
    r = var_explained.shape[0]
    if r <= PLATEAU_WINDOW:
        return False
    return (np.max(var_explained[r - PLATEAU_WINDOW:])
            - np.max(var_explained[:r - PLATEAU_WINDOW])) < gain


def cal_nmf(
    spike_times_list: list[np.ndarray],
    spike_counts: np.ndarray,
    duration_s: float,
    downsample_freq: float,
    fs: float,
    min_spike_count: int = 1,
    include_nmf_components: bool = False,
    rng: np.random.Generator | None = None,
    plateau_gain: float = 0.0,
    max_workers: int | None = None,
) -> dict:
    """Non-negative matrix factorization dimensionality metrics for one
    recording (lag-independent — call once per recording, not once per lag,
    matching ``ExtractNetMet.m``'s ``if e == 1`` gate).

    Returns a dict with ``num_nnmf_components``, ``nComponentsRelNS``,
    ``nnmf_residuals``, ``nnmf_var_explained``, ``randResidualPerComponent``
    — the fields MATLAB unconditionally saves into ``NetMet`` — plus,
    only if ``include_nmf_components`` (space-heavy, off by default,
    matching MATLAB's ``Params.includeNMFcomponents``), ``nmfFactors``,
    ``nmfWeights``, ``downSampleSpikeMatrix``, ``nmfFactorsVarThreshold``,
    ``nmfWeightsVarThreshold``.

    ``plateau_gain`` > 0 ends the per-rank sweep early, once variance
    explained has risen by less than that over the last
    ``PLATEAU_WINDOW`` ranks (or has passed 95%); the ranks not fitted are
    NaN in ``nnmf_residuals``/``nnmf_var_explained``, and if 95% was never
    reached the ``*VarThreshold`` factors come from the last rank fitted
    rather than the last rank. 0 fits every rank, as ``calNMF.m`` does. ``max_workers`` caps the threads the fits run on
    (default: :func:`~meanap.pipeline.parallel.compute_threads`); the result
    is the same for any value.
    """
    if rng is None:
        rng = np.random.default_rng()
    workers = compute_threads() if max_workers is None else max(1, max_workers)

    downsample_freq = min(downsample_freq, fs)
    n_bins = max(int(round(downsample_freq * duration_s)), 1)

    down_sample_spike_matrix = _bin_spike_times(spike_times_list, duration_s, n_bins)
    randomised = [randomise_spike_train(st, duration_s, rng) for st in spike_times_list]
    rand_spike_matrix = _bin_spike_times(randomised, duration_s, n_bins)

    n_channels = down_sample_spike_matrix.shape[1]

    # ── Search for num_nnmf_components: keep adding components while the
    # real matrix's own reconstruction residual beats a phase-randomized
    # reference's — i.e. while more components still capture real structure
    # rather than fitting noise as readily as they'd fit shuffled data. ──
    nmf_factors: np.ndarray | None = None
    nmf_weights: np.ndarray | None = None
    rand_residual_per_component: list[float] = []
    k = 1
    block = 1
    searching = n_channels >= 1
    while searching:
        # Fit ranks k..k+block-1 at once, real and shuffled side by side. The
        # loop stops at the first rank whose residual no longer beats the
        # shuffled one, so fits past it are wasted: the block starts at one
        # rank and doubles while the search continues, up to the thread
        # count, so a search that ends at rank 1 or 2 costs what it did serially.
        ranks = list(range(k, min(k + block, n_channels + 1)))
        state = rng.bit_generator.state
        seeds = [(_draw_seed(rng), _draw_seed(rng)) for _ in ranks]
        fits = _fit_all([job for kk, (s_real, s_rand) in zip(ranks, seeds)
                         for job in ((down_sample_spike_matrix, kk, s_real),
                                     (rand_spike_matrix, kk, s_rand))], workers)
        used = 0
        for idx, kk in enumerate(ranks):
            nmf_factors, nmf_weights, residual = fits[2 * idx]
            rand_residual = fits[2 * idx + 1][2]
            rand_residual_per_component.append(rand_residual)
            used += 1
            k = kk + 1
            if not (residual < rand_residual and k <= n_channels):
                searching = False
                break
        if used < len(ranks):
            # Put the generator back as if only the ranks used had drawn
            # seeds, so everything after sees the stream the serial loop left.
            rng.bit_generator.state = state
            for _ in range(2 * used):
                _draw_seed(rng)
        block = min(2 * block, max(1, workers))
    num_nnmf_components = k - 1

    active_electrodes = spike_counts > min_spike_count
    network_size = int(np.sum(active_electrodes))

    result: dict = {
        "num_nnmf_components": num_nnmf_components,
        "nComponentsRelNS": (num_nnmf_components / network_size) if network_size else float("nan"),
        "randResidualPerComponent": np.array(rand_residual_per_component),
    }

    # ── Per-rank sweep over active electrodes only, for the "how many
    # components until we explain 95% of variance" curve. ──
    down_sample_active = down_sample_spike_matrix[:, active_electrodes]
    # NaN until fitted: an early stop leaves the ranks it skipped as NaN.
    nnmf_residuals = np.full(network_size, np.nan)
    nnmf_var_explained = np.full(network_size, np.nan)
    var_explained_threshold = 0.95
    threshold_reached = False
    nmf_factors_var_threshold: np.ndarray | None = None
    nmf_weights_var_threshold: np.ndarray | None = None

    # Every rank's seed is drawn up front, in rank order, so a rank's fit is the
    # same however many threads run the sweep and wherever it stops.
    sweep_seeds = [_draw_seed(rng) for _ in range(network_size)]
    last: list = [None, None]

    def take(fit: tuple) -> bool:
        nonlocal threshold_reached, nmf_factors_var_threshold, nmf_weights_var_threshold
        rank, w_r, h_r, res, var_explained = fit
        last[:] = [w_r, h_r]
        nnmf_residuals[rank - 1] = res
        nnmf_var_explained[rank - 1] = var_explained
        if var_explained > var_explained_threshold and not threshold_reached:
            threshold_reached = True
            nmf_factors_var_threshold = w_r
            nmf_weights_var_threshold = h_r
        return not (plateau_gain > 0 and _levelled_off(
            nnmf_var_explained[:rank], plateau_gain, threshold_reached))

    _fit_in_order([(down_sample_active, r, sweep_seeds[r - 1]) for r in range(1, network_size + 1)],
                  workers, take)
    w, h = last

    if network_size > 0 and not threshold_reached:
        nmf_factors_var_threshold = w
        nmf_weights_var_threshold = h

    result["nnmf_residuals"] = nnmf_residuals
    result["nnmf_var_explained"] = nnmf_var_explained

    if include_nmf_components:
        result["downSampleSpikeMatrix"] = down_sample_spike_matrix
        result["nmfFactors"] = nmf_factors
        result["nmfWeights"] = nmf_weights
        result["nmfFactorsVarThreshold"] = nmf_factors_var_threshold
        result["nmfWeightsVarThreshold"] = nmf_weights_var_threshold

    return result
