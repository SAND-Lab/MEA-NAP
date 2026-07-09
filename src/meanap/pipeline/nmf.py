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

import numpy as np
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning


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


def _nnmf(x: np.ndarray, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, float]:
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
    seed = int(rng.integers(0, 2**31 - 1))
    try:
        model = NMF(n_components=k, init="random", solver="cd", max_iter=100, random_state=seed)
        with warnings.catch_warnings():
            # Not reaching full convergence within a bounded iteration count
            # is expected/tolerated here, same as MATLAB's own ALS default
            # — this metric is inherently approximate, not exactly
            # reproducible even between two MATLAB runs on the same data.
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            w = model.fit_transform(x)
        h = model.components_
        d = model.reconstruction_err_ / np.sqrt(m * n)
    except Exception:
        w = np.zeros((m, k))
        h = np.zeros((k, n))
        d = float("inf")
    return w, h, float(d)


def cal_nmf(
    spike_times_list: list[np.ndarray],
    spike_counts: np.ndarray,
    duration_s: float,
    downsample_freq: float,
    fs: float,
    min_spike_count: int = 1,
    include_nmf_components: bool = False,
    rng: np.random.Generator | None = None,
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
    """
    if rng is None:
        rng = np.random.default_rng()

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
    residual = 0.0
    rand_residual = 1.0
    k = 1
    rand_residual_per_component: list[float] = []
    while residual < rand_residual and k <= n_channels:
        nmf_factors, nmf_weights, residual = _nnmf(down_sample_spike_matrix, k, rng)
        _, _, rand_residual = _nnmf(rand_spike_matrix, k, rng)
        rand_residual_per_component.append(rand_residual)
        k += 1
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
    nnmf_residuals = np.zeros(network_size)
    nnmf_var_explained = np.zeros(network_size)
    var_explained_threshold = 0.95
    threshold_reached = False
    nmf_factors_var_threshold: np.ndarray | None = None
    nmf_weights_var_threshold: np.ndarray | None = None

    for kk in range(1, network_size + 1):
        w, h, res = _nnmf(down_sample_active, kk, rng)
        nnmf_residuals[kk - 1] = res

        predicted = w @ h
        ss_res = np.sum((predicted - down_sample_active) ** 2)
        grand_mean = down_sample_active.mean()
        ss_tot = np.sum((down_sample_active - grand_mean) ** 2)
        var_explained = (1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        nnmf_var_explained[kk - 1] = var_explained

        if var_explained > var_explained_threshold and not threshold_reached:
            threshold_reached = True
            nmf_factors_var_threshold = w
            nmf_weights_var_threshold = h

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
