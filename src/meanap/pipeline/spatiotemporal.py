"""Spatial and temporal autocorrelation, after Shinn et al. (2023).

Shinn, M. et al. *Functional brain networks reflect spatial and temporal
autocorrelation.* Nature Neuroscience 26, 867–878 (2023).
https://doi.org/10.1038/s41593-023-01299-3

The paper's argument is that two low-level properties of the recorded
signals — how smooth each node's timeseries is (temporal autocorrelation) and
how correlation falls off with distance (spatial autocorrelation) — explain a
large share of the graph metrics usually read as network *topology*. It gives
three summary statistics and a generative model built from nothing else:

``TA_regional`` (TA-Δ₁, per node)
    The lag-1 autocorrelation of the node's timeseries.
``TA_global``
    Their mean over the network's nodes.
``SA_lambda`` (SA-λ) / ``SA_inf`` (SA-∞)
    The length scale and floor of ``corr(d) = (1 − SA∞)·exp(−d/SA-λ) + SA∞``,
    fitted to the mean pairwise correlation at each distance.
``SA_lambda_free`` / ``SA_amp`` / ``SA_inf_free``
    Not the paper's: the same curve with its start left free,
    ``amp·exp(−d/λ) + floor``. The paper's reaches 1 at d → 0, which coupling
    between distinct electrodes or cells never does, and that biases SA-λ
    short. See :func:`spatial_autocorrelation_nugget`.

The **spatiotemporal model** draws surrogate timeseries with the observed
SA-λ, SA-∞ and per-node TA-Δ₁ (and nothing else). Building a network from them
the same way as the data, and computing the same graph metrics on it, says
how much of each metric those three statistics alone would predict; Lin's
concordance between the data and the model across recordings is the paper's
measure of that.

The functions here are a reimplementation of the reference ``spatiotemporal``
package (Max Shinn, MIT licence, https://github.com/mwshinn/spatiotemporal),
not a dependency on it, with three changes for use on MEA and calcium data:

* the SA fit excludes the diagonal and any non-finite pair. The reference
  flattens the whole matrix, which is harmless for a correlation matrix with
  ones on the diagonal but wrong for an adjacency matrix with zeros there;
* the SA fit bins distance into a fixed number of bins over the observed range,
  and bounds SA-λ relative to that range, rather than using fixed 1 mm bins and
  a 0.1–100 bound. Those are fMRI millimetres, and the distances here are
  electrode pitches or imaging pixels;
* the fit profiles out SA-∞ in closed form (it is linear given SA-λ) and
  searches SA-λ on a grid before refining, instead of starting one local
  optimiser at λ=10. The result is the same least-squares fit, but it is
  deterministic and cannot stall in a local minimum.

The model reproduces the reference's correlated spectral sampling and its
brown-noise-plus-white-noise construction. Only the random-number API differs
(``numpy.random.Generator`` throughout, so a run's seed controls it).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.spatial.distance import cdist
from scipy.stats import spearmanr

# ── Temporal autocorrelation ────────────────────────────────────────────────


def temporal_autocorrelation(x: np.ndarray) -> np.ndarray:
    """TA-Δ₁ of each row of *x* (``(n_nodes, n_timepoints)``).

    The Pearson correlation of each timeseries with itself shifted by one
    sample — the biased estimator the paper uses (``np.corrcoef(x[:-1], x[1:])``),
    vectorised over rows. A row with no variance on either side of the shift
    (a silent channel, a constant trace) has no defined autocorrelation and is
    NaN rather than 0.
    """
    x = np.atleast_2d(np.asarray(x, dtype=float))
    if x.shape[1] < 3:
        return np.full(x.shape[0], np.nan)
    a = x[:, :-1] - x[:, :-1].mean(axis=1, keepdims=True)
    b = x[:, 1:] - x[:, 1:].mean(axis=1, keepdims=True)
    num = np.sum(a * b, axis=1)
    den = np.sqrt(np.sum(a * a, axis=1) * np.sum(b * b, axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def bin_event_times(
    event_times: list[np.ndarray], duration_s: float, bin_s: float,
) -> np.ndarray:
    """Event counts per node in consecutive bins of *bin_s* seconds.

    Returns ``(n_nodes, n_bins)``. A trailing partial bin is dropped so every bin
    covers the same span. Spike trains have no TA-Δ₁ of their own; this is the
    timeseries one is computed from.
    """
    n_bins = int(np.floor(duration_s / bin_s))
    out = np.zeros((len(event_times), max(n_bins, 0)))
    if n_bins < 1:
        return out
    edges = np.arange(n_bins + 1) * bin_s
    for i, t in enumerate(event_times):
        t = np.asarray(t, dtype=float).ravel()
        if t.size:
            out[i] = np.histogram(t, bins=edges)[0]
    return out


# ── Spatial autocorrelation ─────────────────────────────────────────────────


def spatial_exponential_floor(
    dist: np.ndarray, sa_lambda: float, sa_inf: float,
) -> np.ndarray:
    """The SA model's correlation at distance *dist*: ``(1−SA∞)·e^(−d/λ) + SA∞``."""
    return np.exp(-np.asarray(dist, dtype=float) / sa_lambda) * (1.0 - sa_inf) + sa_inf


def _binned_correlation_profile(
    corr: np.ndarray, dist: np.ndarray, n_bins: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Mean distance and mean correlation of each non-empty distance bin.

    Upper triangle only, so each pair counts once, and the diagonal (distance
    0, a node with itself) is never part of it.
    """
    iu = np.triu_indices_from(corr, k=1)
    d = np.asarray(dist, dtype=float)[iu]
    c = np.asarray(corr, dtype=float)[iu]
    ok = np.isfinite(d) & np.isfinite(c)
    d, c = d[ok], c[ok]
    if d.size == 0:
        return d, c
    lo, hi = d.min(), d.max()
    if hi <= lo:
        return np.array([d.mean()]), np.array([c.mean()])
    edges = np.linspace(lo, hi, n_bins + 1)
    idx = np.clip(np.searchsorted(edges, d, side="right") - 1, 0, n_bins - 1)
    counts = np.bincount(idx, minlength=n_bins)
    keep = counts > 0
    d_mean = np.bincount(idx, weights=d, minlength=n_bins)[keep] / counts[keep]
    c_mean = np.bincount(idx, weights=c, minlength=n_bins)[keep] / counts[keep]
    return d_mean, c_mean


def _best_floor(e: np.ndarray, y: np.ndarray) -> float:
    """Least-squares SA-∞ for fixed decay ``e = exp(−d/λ)``, clipped to [−1, 1].

    ``y ≈ e + SA∞·(1 − e)`` is linear in SA∞, so its optimum is closed form;
    the SSE is a parabola in SA∞, so clipping it to the bound is exact too.
    """
    g = 1.0 - e
    den = float(np.dot(g, g))
    if den <= 0:
        return 0.0
    return float(np.clip(np.dot(g, y - e) / den, -1.0, 1.0))


def spatial_autocorrelation(
    corr: np.ndarray, dist: np.ndarray, n_bins: int = 20,
) -> tuple[float, float]:
    """SA-λ and SA-∞ for one network.

    Parameters
    ----------
    corr
        ``(n, n)`` pairwise coupling — correlation or STTC — **before**
        thresholding. Thresholding zeroes the weak long-range pairs and would
        pull SA-∞ towards zero.
    dist
        ``(n, n)`` distances between the same nodes. SA-λ comes back in the
        same unit.
    n_bins
        Distance bins the profile is averaged into before fitting, as in the
        paper (which bins at 1 mm). Equal-width over the observed range.

    Returns ``(nan, nan)`` when fewer than three bins have pairs in them, the
    least the two-parameter curve can be meaningfully fitted to.
    """
    d, y = _binned_correlation_profile(corr, dist, n_bins)
    if d.size < 3 or d.max() <= 0:
        return float("nan"), float("nan")

    def sse(log_lam: float) -> float:
        e = np.exp(-d / np.exp(log_lam))
        floor = _best_floor(e, y)
        return float(np.sum((y - (e * (1.0 - floor) + floor)) ** 2))

    # λ from a thousandth to a hundred times the observed range. Below the
    # lower bound every pair is already at the floor; above the upper bound
    # the curve is a straight line over the data and λ is unidentifiable.
    lo = np.log(d.max() * 1e-3)
    hi = np.log(d.max() * 1e2)
    grid = np.linspace(lo, hi, 61)
    best = grid[int(np.argmin([sse(g) for g in grid]))]
    step = grid[1] - grid[0]
    res = minimize_scalar(sse, bounds=(max(lo, best - step), min(hi, best + step)),
                          method="bounded")
    log_lam = res.x if res.fun <= sse(best) else best
    lam = float(np.exp(log_lam))
    return lam, _best_floor(np.exp(-d / lam), y)


def _best_amp_floor(e: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Least-squares ``(amp, floor)`` for fixed decay ``e``, constrained.

    ``y ≈ amp·e + floor`` is linear in both, so the unconstrained optimum is
    closed form. The constraints — amp ≥ 0, floor ∈ [−1, 1], amp + floor ≤ 1
    (coupling between distinct nodes cannot exceed a node's with itself) —
    cut out a convex region and the SSE is a convex quadratic, so when the
    free optimum lies outside, the constrained one is the best of the boundary
    faces' own optima. The amp + floor = 1 face is the paper's pinned curve.
    """
    def sse(a: float, f: float) -> float:
        return float(np.sum((y - (a * e + f)) ** 2))

    candidates: list[tuple[float, float]] = []
    design = np.column_stack([e, np.ones_like(e)])
    (a, f), *_ = np.linalg.lstsq(design, y, rcond=None)
    if a >= 0 and -1 <= f <= 1 and a + f <= 1:
        return float(a), float(f)
    f = _best_floor(e, y)                                   # amp + floor = 1
    candidates.append((1.0 - f, f))
    candidates.append((0.0, float(np.clip(np.mean(y), -1.0, 1.0))))   # amp = 0
    ee = float(np.dot(e, e))                                # floor = −1
    if ee > 0:
        candidates.append((float(np.clip(np.dot(e, y + 1.0) / ee, 0.0, 2.0)), -1.0))
    return min(candidates, key=lambda c: sse(*c))


def spatial_autocorrelation_nugget(
    corr: np.ndarray, dist: np.ndarray, n_bins: int = 20,
) -> tuple[float, float, float]:
    """SA-λ, amplitude and floor with the curve's start left free.

    Fits ``corr(d) = amp·exp(−d/λ) + floor`` for d > 0, where
    :func:`spatial_autocorrelation` fixes ``amp = 1 − floor``. The paper's
    curve reaches 1 as d → 0, which suits fMRI, whose neighbouring voxels
    sample one smooth field. Two electrodes, however close, record different
    neurons with independent noise, so coupling between distinct sites starts
    well below 1 — a jump at d = 0 that geostatistics calls the *nugget*. The
    pinned curve can only reach that lower start by shortening λ, which mixes
    how *strongly* neighbours couple into how *far* coupling reaches. Here
    ``amp + floor`` is the coupling just above d = 0 and λ is the length
    scale alone.

    Returns ``(λ, amp, floor)``. NaN where the profile cannot separate them:

    * fewer than three distance bins → all NaN;
    * no spatial structure (best amp is 0) → λ NaN, amp 0;
    * decay complete before the nearest bin (``exp(−d_min/λ) < 0.1``): only
      the product of amp and the decay is seen, not each → λ and amp NaN;
    * decay barely begun across the array (λ > 10 × the largest distance):
      the curve is a straight line, and neither λ nor the floor it would
      settle to is identifiable → all NaN.
    """
    nan3 = (float("nan"),) * 3
    d, y = _binned_correlation_profile(corr, dist, n_bins)
    if d.size < 3 or d.max() <= 0:
        return nan3

    def sse(log_lam: float) -> float:
        e = np.exp(-d / np.exp(log_lam))
        a, f = _best_amp_floor(e, y)
        return float(np.sum((y - (a * e + f)) ** 2))

    lo = np.log(d.max() * 1e-3)
    hi = np.log(d.max() * 1e2)
    grid = np.linspace(lo, hi, 61)
    best = grid[int(np.argmin([sse(g) for g in grid]))]
    step = grid[1] - grid[0]
    res = minimize_scalar(sse, bounds=(max(lo, best - step), min(hi, best + step)),
                          method="bounded")
    lam = float(np.exp(res.x if res.fun <= sse(best) else best))
    amp, floor = _best_amp_floor(np.exp(-d / lam), y)

    if amp <= 1e-9:
        return float("nan"), 0.0, floor
    if lam > 10 * d.max():
        return nan3
    if np.exp(-d.min() / lam) < 0.1:
        return float("nan"), float("nan"), floor
    return lam, amp, floor


# ── Spatiotemporal model ────────────────────────────────────────────────────


class PositiveSemidefiniteError(ValueError):
    """The SA correlation matrix cannot be realised with the given spectra."""


def make_spectrum(
    n_timepoints: int, sample_interval_s: float, alpha: float,
    highpass_hz: float = 0.0,
) -> np.ndarray:
    """Amplitude spectrum of 1/f^α noise (α=2 is brown), DC removed.

    Port of ``spatiotemporal.models.make_spectrum``. *highpass_hz* > 0 applies
    the reference's 4th-order Butterworth high-pass response.
    """
    freqs = np.fft.rfftfreq(n_timepoints, sample_interval_s)
    spectrum = np.zeros_like(freqs)
    spectrum[1:] = freqs[1:] ** (-alpha / 2.0)
    if highpass_hz > 0:
        import scipy.signal
        fs = 1.0 / sample_interval_s
        b, a = scipy.signal.iirfilter(N=4, Wn=highpass_hz, btype="highpass",
                                      ftype="butter", fs=fs, output="ba")
        _, h = scipy.signal.freqz(b, a, worN=len(freqs), fs=fs, include_nyquist=True)
        spectrum = spectrum * np.abs(h)
    spectrum[0] = 0.0
    return spectrum


def spectrum_ta(spectrum: np.ndarray) -> float:
    """Expected TA-Δ₁ of random-phase timeseries with this amplitude spectrum."""
    n = len(spectrum)
    p = spectrum ** 2
    return float(np.sum(p * np.cos(np.pi * np.arange(n) / n)) / np.sum(p))


def how_much_noise(spectrum: np.ndarray, target_ta: float) -> float:
    """SD of white noise to add to timeseries with *spectrum* to reach *target_ta*.

    Port of ``spatiotemporal.models.how_much_noise``. A target at or above the
    noiseless spectrum's own TA-Δ₁ needs no noise, and returns 0 rather than
    the reference's NaN (the square root of a negative variance).
    """
    n = len(spectrum)
    weighted = np.sum(spectrum[1:] ** 2 * np.cos(np.pi * np.arange(1, n) / n))
    var = (weighted - np.sum(spectrum ** 2) * target_ta) / (target_ta * n ** 2)
    return float(np.sqrt(var)) if var > 0 else 0.0


def correlated_spectral_sampling(
    cm: np.ndarray, spectra: np.ndarray, rng: np.random.Generator,
) -> np.ndarray:
    """Timeseries with the given amplitude spectra and correlation matrix.

    Port of ``spatiotemporal.models.correlated_spectral_sampling``: draw each
    frequency's real and imaginary coefficients jointly Gaussian across nodes,
    with the covariance that gives correlation *cm* once scaled by the spectra.
    Returns ``(n_nodes, 2·(n_freqs − 1))``.
    """
    n_nodes, n_freqs = spectra.shape
    if cm.shape != (n_nodes, n_nodes):
        raise ValueError("cm and spectra disagree on the number of nodes")
    sum_sq = np.sum(spectra ** 2, axis=1, keepdims=True)
    cosine = (spectra @ spectra.T) / np.sqrt(sum_sq @ sum_sq.T)
    cov = cm / cosine
    evals, evecs = np.linalg.eigh((cov + cov.T) / 2.0)
    if evals.min() < -1e-8:
        raise PositiveSemidefiniteError(
            "this correlation matrix is not realisable with these spectra")
    root = evecs * np.sqrt(np.clip(evals, 0.0, None))
    draws = rng.standard_normal((2 * n_freqs, n_nodes)) @ root.T
    reals = draws[:n_freqs].T * spectra
    imags = draws[n_freqs:].T * spectra
    # Even length: the Nyquist coefficient is its own conjugate, so real. And
    # the DC component is zero.
    imags[:, -1] = 0.0
    reals[:, 0] = 0.0
    imags[:, 0] = 0.0
    return np.fft.irfft(reals + 1j * imags, n=2 * (n_freqs - 1), axis=-1)


def spatiotemporal_model_timeseries(
    dist: np.ndarray,
    sa_lambda: float,
    sa_inf: float,
    ta: np.ndarray,
    n_timepoints: int,
    sample_interval_s: float,
    rng: np.random.Generator,
    highpass_hz: float = 0.0,
) -> np.ndarray:
    """Surrogate timeseries from the paper's spatiotemporal model.

    Brown noise correlated across nodes by the SA curve, plus independent white
    noise sized per node to bring each one down to its own TA-Δ₁. Port of
    ``spatiotemporal.models.spatiotemporal_model_timeseries``; *n_timepoints* is
    rounded down to even, which the spectral construction needs.
    """
    n_timepoints -= n_timepoints % 2
    if n_timepoints < 4:
        raise ValueError("too few timepoints to simulate")
    spectrum = make_spectrum(n_timepoints, sample_interval_s, 2.0, highpass_hz)
    ta = np.asarray(ta, dtype=float)
    spectra = np.tile(spectrum, (len(ta), 1))
    corr = spatial_exponential_floor(dist, sa_lambda, sa_inf)
    np.fill_diagonal(corr, 1.0)
    tss = correlated_spectral_sampling(corr, spectra, rng)
    # As the reference: a TA-Δ₁ at or below zero is taken as 0.001, i.e. very
    # nearly white. A NaN (no defined autocorrelation) is treated the same.
    targets = np.where(np.isfinite(ta), np.maximum(ta, 0.001), 0.001)
    noise_sd = np.array([how_much_noise(spectrum, t) for t in targets])
    tss += rng.standard_normal(tss.shape) * noise_sd[:, None]
    return tss


def density_matched_network(model_corr: np.ndarray, data_adj: np.ndarray) -> np.ndarray:
    """The model's network, given the data's edge count and edge weights.

    Keeps as many edges as *data_adj* has, the model's strongest pairs, and
    hands them the data's edge weights in rank order (strongest pair gets the
    strongest weight). The two networks then share their nodes, density and
    weight distribution exactly, and differ only in *where* the edges sit —
    which is the part the model is meant to predict. Without the weight
    matching, every weighted metric would also compare correlation
    coefficients against STTC values, which are on different scales.
    """
    n = data_adj.shape[0]
    iu = np.triu_indices(n, k=1)
    weights = np.asarray(data_adj, dtype=float)[iu]
    weights = np.sort(weights[weights > 0])[::-1]
    out = np.zeros((n, n))
    k = weights.size
    if k == 0:
        return out
    scores = np.asarray(model_corr, dtype=float)[iu]
    scores = np.where(np.isfinite(scores), scores, -np.inf)
    # Stable on ties so the result depends only on the inputs.
    order = np.argsort(-scores, kind="stable")[:k]
    out[iu[0][order], iu[1][order]] = weights
    return out + out.T


# ── Agreement between data and model ────────────────────────────────────────


def lins_concordance(x: np.ndarray, y: np.ndarray) -> float:
    """Lin's concordance correlation coefficient between *x* and *y*.

    Pairs with a non-finite value on either side are dropped. Unlike Pearson's
    r it penalises a shift or a change of scale, so it is 1 only when the model
    gets the values themselves right, not just their ordering. NaN with fewer
    than three pairs.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 3:
        return float("nan")
    mx, my = x.mean(), y.mean()
    vx, vy = x.var(), y.var()
    cov = np.mean((x - mx) * (y - my))
    den = vx + vy + (mx - my) ** 2
    return float(2 * cov / den) if den > 0 else float("nan")


def node_rank_agreement(data: np.ndarray, model: np.ndarray) -> float:
    """Spearman ρ between a node metric in the data and in the model.

    NaN when either side is constant or there are fewer than three nodes with
    finite values on both.
    """
    data = np.asarray(data, dtype=float)
    model = np.asarray(model, dtype=float)
    ok = np.isfinite(data) & np.isfinite(model)
    if ok.sum() < 3 or np.ptp(data[ok]) == 0 or np.ptp(model[ok]) == 0:
        return float("nan")
    return float(spearmanr(data[ok], model[ok])[0])


def pairwise_distances(coords: np.ndarray) -> np.ndarray:
    """Euclidean distance matrix between rows of *coords*."""
    coords = np.asarray(coords, dtype=float)
    return cdist(coords, coords)


# ── Per-network analysis ────────────────────────────────────────────────────

#: Recording-level graph metrics the model is scored on. The *raw* clustering
#: coefficient and path length, not ``CC``/``PL``: those are normalised by
#: lattice/random null networks that are themselves rebuilt from each network,
#: and the comparison here is between the networks as they are. ``NDmean`` and
#: ``Dens`` are absent because density matching makes them equal by
#: construction.
MODEL_REC_METRICS = ("NDtop25", "CC_rawMean", "PL_raw", "Eglob", "ElocMean", "Q")

#: Node-level graph metrics the model is scored on, by rank agreement across
#: the nodes of each network.
MODEL_NODE_METRICS = ("ND", "NS", "CC_raw", "Eloc", "BC")


def graph_summary(
    sub: np.ndarray, rng: np.random.Generator, exclude_zeros: bool = True,
) -> dict:
    """:data:`MODEL_REC_METRICS` and :data:`MODEL_NODE_METRICS` for one network.

    Each is computed exactly as ``step4.compute_network_metrics`` computes it
    for the data. That sameness is what makes the comparison mean anything, and
    ``test_spatiotemporal`` pins it.
    """
    from meanap.pipeline import network_metrics as nm
    from meanap.pipeline.modularity import mod_consensus_cluster_iterate

    n = sub.shape[0]
    nd, _ = nm.find_node_deg_edge_weight(sub, edge_thresh=0.0001,
                                         exclude_zeros=exclude_zeros)
    out: dict = {"ND": nd, "NS": nm.strengths_und(sub)}
    out["NDtop25"] = float(np.mean(nd[nd >= np.percentile(nd, 75)]))
    out["CC_raw"] = nm.clustering_coef_wu(sub)
    out["CC_rawMean"] = float(np.mean(out["CC_raw"]))
    pl_raw, _ = nm.charpath(nm.distance_wei(nm.weight_conversion_lengths(sub)))
    out["PL_raw"] = pl_raw
    out["Eglob"] = nm.efficiency_wei_global(sub)
    out["Eloc"] = nm.efficiency_wei_local(nm.weight_conversion_normalize(sub))
    out["ElocMean"] = float(np.mean(out["Eloc"]))
    bc = nm.betweenness_wei(1.0 / (sub + 0.01))
    out["BC"] = bc / ((n - 1) * (n - 2)) if n > 2 else np.full(n, np.nan)
    if n > 1:
        _ci, q, _ = mod_consensus_cluster_iterate(sub, threshold=0.4, rep_num=50, rng=rng)
        out["Q"] = q
    return out


def spatiotemporal_metrics(
    metrics: dict,
    raw_adj: np.ndarray,
    dist: np.ndarray,
    ta: np.ndarray,
    *,
    n_timepoints: int,
    sample_interval_s: float,
    null_model: bool = False,
    n_reps: int = 3,
    n_bins: int = 20,
    exclude_zeros: bool = True,
    rng: np.random.Generator | None = None,
) -> dict:
    """SA/TA metrics, and optionally the model comparison, for one network.

    Parameters
    ----------
    metrics
        What ``compute_network_metrics`` returned for this network. Its
        ``activeChannelIndex`` picks the nodes, so SA and TA describe the same
        nodes as every other metric; and its graph metrics are what the model is
        compared against. A network too small to have metrics (no ``adjMsub``)
        gets none of these either.
    raw_adj
        The full, **unthresholded** coupling matrix (all channels).
    dist
        Distances between all channels, in the unit SA-λ is reported in.
    ta
        TA-Δ₁ of every channel, of the timeseries the model will imitate.
    n_timepoints, sample_interval_s
        Length and sampling interval of that timeseries; the model's
        surrogates are drawn at the same resolution.
    null_model
        Draw the model networks and score them. Off, only the four statistics
        are returned.
    n_reps
        Model networks per data network. Their recording-level metrics are
        averaged; their node-level ones are averaged per node before the rank
        agreement is taken.

    Returns ``SA_lambda``, ``SA_inf``, ``SA_lambda_free``, ``SA_amp``,
    ``SA_inf_free``, ``TA_global``, ``TA_regional`` (one per active node), and
    with *null_model*: ``ST_<metric>`` for each of
    :data:`MODEL_REC_METRICS` (the model's value) and ``STrho_<metric>`` for
    each of :data:`MODEL_NODE_METRICS` (Spearman ρ between the data's and the
    model's per-node values).
    """
    sub = metrics.get("adjMsub")
    if sub is None:
        return {}
    idx = np.asarray(metrics["activeChannelIndex"], dtype=int)
    raw_sub = np.asarray(raw_adj, dtype=float)[np.ix_(idx, idx)]
    dist_sub = np.asarray(dist, dtype=float)[np.ix_(idx, idx)]
    ta_sub = np.asarray(ta, dtype=float)[idx]

    sa_lambda, sa_inf = spatial_autocorrelation(raw_sub, dist_sub, n_bins)
    lam_free, amp, inf_free = spatial_autocorrelation_nugget(raw_sub, dist_sub, n_bins)
    out: dict = {
        "SA_lambda": sa_lambda,
        "SA_inf": sa_inf,
        "SA_lambda_free": lam_free,
        "SA_amp": amp,
        "SA_inf_free": inf_free,
        "TA_global": float(np.nanmean(ta_sub)) if np.isfinite(ta_sub).any() else float("nan"),
        "TA_regional": ta_sub,
    }
    if not null_model or not np.isfinite(sa_lambda) or n_reps < 1:
        return out

    if rng is None:
        rng = np.random.default_rng()
    rec_vals: dict[str, list[float]] = {k: [] for k in MODEL_REC_METRICS}
    node_vals: dict[str, list[np.ndarray]] = {k: [] for k in MODEL_NODE_METRICS}
    for _ in range(n_reps):
        try:
            tss = spatiotemporal_model_timeseries(
                dist_sub, sa_lambda, sa_inf, ta_sub, n_timepoints,
                sample_interval_s, rng)
        except (PositiveSemidefiniteError, ValueError):
            return out
        with np.errstate(invalid="ignore", divide="ignore"):
            model_corr = np.corrcoef(tss)
        model = density_matched_network(model_corr, sub)
        summary = graph_summary(model, rng, exclude_zeros=exclude_zeros)
        for k in MODEL_REC_METRICS:
            rec_vals[k].append(float(summary.get(k, np.nan)))
        for k in MODEL_NODE_METRICS:
            node_vals[k].append(np.asarray(summary[k], dtype=float))

    for k, vals in rec_vals.items():
        out[f"ST_{k}"] = float(np.nanmean(vals)) if np.isfinite(vals).any() else float("nan")
    for k, vals in node_vals.items():
        if k in metrics:
            with np.errstate(invalid="ignore"):
                model_mean = np.nanmean(np.vstack(vals), axis=0)
            out[f"STrho_{k}"] = node_rank_agreement(metrics[k], model_mean)
    return out


def concordance_table(all_results: dict) -> "pd.DataFrame":
    """How well the model predicts each graph metric across recordings.

    *all_results* is ``{recording: {lag_key: metrics}}`` as step 4 holds it.
    One row per (lag, metric): Lin's concordance and Pearson's r between the
    data's and the model's values across recordings — the paper's measure, and
    the one that says whether the metric tells recordings apart for reasons
    other than their SA and TA. For the node-level metrics, the median over
    recordings of the per-network rank agreement (``STrho_*``) instead, which
    says whether the model also gets the *nodes* right.

    Empty when the model was not run.
    """
    import pandas as pd

    rows = []
    lags = sorted({lag for rec in all_results.values() for lag in rec},
                  key=lambda k: float(str(k).replace("mslag", "") or 0))
    for lag in lags:
        per_lag = [rec[lag] for rec in all_results.values() if lag in rec]
        for k in MODEL_REC_METRICS:
            pairs = [(m.get(k, np.nan), m[f"ST_{k}"]) for m in per_lag if f"ST_{k}" in m]
            if not pairs:
                continue
            data, model = (np.asarray(v, dtype=float) for v in zip(*pairs))
            ok = np.isfinite(data) & np.isfinite(model)
            r = (float(np.corrcoef(data[ok], model[ok])[0, 1])
                 if ok.sum() >= 3 and np.ptp(data[ok]) > 0 and np.ptp(model[ok]) > 0
                 else float("nan"))
            rows.append({"Lag": lag, "Metric": k, "Level": "recording",
                         "nRecordings": int(ok.sum()),
                         "LinsConcordance": lins_concordance(data, model),
                         "PearsonR": r, "MedianNodeSpearman": float("nan")})
        for k in MODEL_NODE_METRICS:
            rho = np.array([m[f"STrho_{k}"] for m in per_lag if f"STrho_{k}" in m], dtype=float)
            if rho.size == 0:
                continue
            rows.append({"Lag": lag, "Metric": k, "Level": "node",
                         "nRecordings": int(np.isfinite(rho).sum()),
                         "LinsConcordance": float("nan"), "PearsonR": float("nan"),
                         "MedianNodeSpearman": (float(np.nanmedian(rho))
                                                if np.isfinite(rho).any() else float("nan"))})
    return pd.DataFrame(rows)
