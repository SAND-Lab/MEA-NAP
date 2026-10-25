"""Spike Time Tiling Coefficient (STTC), port of ``get_sttc.m`` / ``sttc_m.m``.

Reference: Cutts & Eglen (2014), "Detecting Pairwise Correlations in Spike
Trains: An Objective Comparison of Methods and Application to the Study of
Retinal Waves", https://www.ncbi.nlm.nih.gov/pubmed/25339742
"""

from __future__ import annotations

import warnings

import numpy as np

from meanap.pipeline.parallel import numba_threads

# ``run_P`` (below) is a monotonic two-pointer whose result is *order-dependent*
# on the input spike trains — it does not sort. For spike-detection data the
# trains are already sorted, but CAT-NAP peak times can arrive unsorted (see
# ``catnap/adjacency.py``), and MATLAB's ``sttc_m.m`` runs on them as-is, so we
# must replicate the literal loop rather than assume sorted order. Compile it
# with numba when available (same optional pattern as ``null_models.py``); the
# pure-Python fallback is identical, just slower.
try:
    from numba import njit, prange, set_num_threads

    _HAVE_NUMBA = True
except Exception:  # pragma: no cover - numba optional / version-gated
    _HAVE_NUMBA = False


def _run_p_impl(t1: np.ndarray, t2: np.ndarray, dt: float) -> int:
    """Literal port of ``run_P`` in ``sttc_m.m``: count spikes in ``t1`` that
    have a coincident spike in ``t2`` within ``dt``, using MATLAB's monotonic,
    non-resetting ``j`` pointer (does not assume either train is sorted)."""
    n1 = t1.shape[0]
    n2 = t2.shape[0]
    nab = 0
    j = 0
    for i in range(n1):
        while j < n2:
            if abs(t1[i] - t2[j]) <= dt:
                nab += 1
                break
            elif t2[j] > t1[i]:
                break
            else:
                j += 1
    return nab


_run_p_jit = njit(cache=True)(_run_p_impl) if _HAVE_NUMBA else _run_p_impl


def _sttc_row_impl(flat: np.ndarray, starts: np.ndarray, tiled: np.ndarray,
                   dt: float, out: np.ndarray, i: int) -> None:
    """Fill ``out[i, i+1:]`` with the STTC of train ``i`` against each later one.

    Train ``i`` is ``flat[starts[i]:starts[i + 1]]`` and ``tiled[i]`` its
    normalised ``run_T``. The arithmetic is :func:`_sttc_from_tiled`'s,
    written out so a whole sweep is one compiled call. Pairs with an empty
    train are left as they are (NaN, which ``get_sttc`` zeroes).
    """
    n = starts.shape[0] - 1
    n1 = starts[i + 1] - starts[i]
    if n1 == 0:
        return
    t1 = flat[starts[i]:starts[i + 1]]
    ta = tiled[i]
    for j in range(i + 1, n):
        n2 = starts[j + 1] - starts[j]
        if n2 == 0:
            continue
        t2 = flat[starts[j]:starts[j + 1]]
        tb = tiled[j]
        pa = _run_p_jit(t1, t2, dt) / n1
        pb = _run_p_jit(t2, t1, dt) / n2
        out[i, j] = 0.5 * (pa - tb) / (1 - tb * pa) + 0.5 * (pb - ta) / (1 - ta * pb)


def _sttc_upper_impl(flat: np.ndarray, starts: np.ndarray, tiled: np.ndarray,
                     dt: float, out: np.ndarray) -> None:
    """Fill the upper triangle of ``out``, rows in parallel.

    Row ``i`` has ``n - 1 - i`` pairs, so rows are taken in pairs from both
    ends (``f`` and ``n - 1 - f``), giving every parallel step the same
    ``n - 1`` pairs. Each pair is computed exactly as in the serial loop and
    written to its own cell, so the result does not depend on the thread
    count.
    """
    n = starts.shape[0] - 1
    for f in _prange((n + 1) // 2):
        _sttc_row(flat, starts, tiled, dt, out, f)
        g = n - 1 - f
        if g != f:
            _sttc_row(flat, starts, tiled, dt, out, g)


# ``error_model="numpy"``: a zero denominator gives inf/NaN, as it does for
# the NumPy scalars in :func:`_sttc_from_tiled`, instead of raising.
if _HAVE_NUMBA:
    _prange = prange
    _sttc_row = njit(cache=True, error_model="numpy")(_sttc_row_impl)
    _sttc_upper = njit(cache=True, error_model="numpy", parallel=True)(_sttc_upper_impl)
    # The same loop compiled without ``parallel``, where ``prange`` is a plain
    # range: what runs if no threading layer can be loaded (see ``get_sttc``).
    _sttc_upper_serial = njit(cache=True, error_model="numpy")(_sttc_upper_impl)
else:  # pragma: no cover - numba optional
    _prange = range
    _sttc_row = _sttc_row_impl
    _sttc_upper = _sttc_upper_serial = _sttc_upper_impl

#: Set once the parallel kernel has failed to start, so later calls go straight
#: to the serial one.
_PARALLEL_BROKEN = False


def _run_t(dt: float, t_start: float, t_end: float, times: np.ndarray) -> float:
    """Fraction-of-recording (unnormalised) tiled by ``times`` +/- ``dt``.

    Direct port of ``run_T`` in ``sttc_m.m`` — vectorised over consecutive
    spike gaps but preserves MATLAB's exact edge-case branching (the n==1
    case uses if/elseif; the n>1 case uses two independent ifs).
    """
    n = len(times)
    if n == 0:
        return 0.0

    time_a = 2 * n * dt

    if n == 1:
        t = times[0]
        if t - t_start < dt:
            time_a = time_a - t_start + t - dt
        elif t + dt > t_end:
            time_a = time_a - t - dt + t_end
        return time_a

    diffs = np.diff(times)
    overlap = diffs[diffs < 2 * dt]
    time_a -= np.sum(2 * dt - overlap)

    if times[0] - t_start < dt:
        time_a = time_a - t_start + times[0] - dt
    if t_end - times[-1] < dt:
        time_a = time_a - times[-1] - dt + t_end

    return time_a


def _run_p(t1: np.ndarray, t2: np.ndarray, dt: float) -> int:
    """Count of spikes in ``t1`` with >=1 coincident spike in ``t2`` within ``dt``.

    Faithful port of the monotonic two-pointer ``run_P`` in ``sttc_m.m`` (see
    :func:`_run_p_impl`). For sorted trains this equals the nearest-neighbour
    count; for unsorted trains it reproduces MATLAB's exact, order-dependent
    result — required for CAT-NAP peak-time parity.
    """
    if len(t1) == 0 or len(t2) == 0:
        return 0
    return int(_run_p_jit(np.ascontiguousarray(t1, dtype=np.float64),
                          np.ascontiguousarray(t2, dtype=np.float64),
                          float(dt)))


def _sttc_from_tiled(t1: np.ndarray, t2: np.ndarray, dt: float,
                     ta: float, tb: float) -> float:
    """STTC given each train's already-normalised ``run_T`` value.

    Split out of :func:`sttc_pair` so a pairwise sweep can compute ``run_T``
    once per train instead of once per pair — see :func:`get_sttc`.
    """
    n1 = len(t1)
    n2 = len(t2)
    if n1 == 0 or n2 == 0:
        return np.nan

    pa = _run_p(t1, t2, dt) / n1
    pb = _run_p(t2, t1, dt) / n2

    return 0.5 * (pa - tb) / (1 - tb * pa) + 0.5 * (pb - ta) / (1 - ta * pb)


def sttc_pair(spike_times_1: np.ndarray, spike_times_2: np.ndarray, dt: float,
              t_start: float, t_end: float) -> float:
    """Spike time tiling coefficient between two spike trains (in seconds)."""
    if len(spike_times_1) == 0 or len(spike_times_2) == 0:
        return np.nan

    t = t_end - t_start
    ta = _run_t(dt, t_start, t_end, spike_times_1) / t
    tb = _run_t(dt, t_start, t_end, spike_times_2) / t
    return _sttc_from_tiled(spike_times_1, spike_times_2, dt, ta, tb)


def get_sttc(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    lag_ms: float,
    duration_s: float,
) -> np.ndarray:
    """Pairwise STTC adjacency matrix, port of ``get_sttc.m``.

    Negative values and NaNs (including the diagonal, which is never
    computed) are zeroed, matching MATLAB's
    ``adjM(adjM<0)=0; adjM(isnan(adjM))=0;``.
    """
    dt = lag_ms / 1000.0
    adj_m = np.full((n_channels, n_channels), np.nan)

    times = [np.asarray(spike_times_dict.get(ch, np.array([]))) for ch in range(n_channels)]

    # ``run_T`` reads one train, so a channel's value is the same in every pair
    # it appears in — but :func:`sttc_pair` recomputes it per pair, which is
    # ``n_channels - 1`` times more often than needed. Hoisting it out turns
    # O(n^2) run_T calls into O(n). The saving is worth having on a 64-channel
    # MEA and decisive on a calcium recording with hundreds of cells, where
    # this runs 201 times per lag (once real, 200 circular-shift surrogates).
    t_span = duration_s
    tiled = [(_run_t(dt, 0.0, duration_s, tr) / t_span) if tr.size else 0.0
             for tr in times]

    # The pair sweep itself costs O(n_channels x total spikes): every pair walks
    # both trains. That is negligible on a 64-electrode MEA and ~2s per matrix
    # for 300 sorted units (so ~20 min of step 3 at 201 matrices x 3 lags),
    # which is why it runs as one compiled call, rows across cores. Trains go
    # in as one flat float64 array; spike times are float64 everywhere in the
    # pipeline, so this is the arithmetic the per-pair path did.
    starts = np.zeros(n_channels + 1, dtype=np.int64)
    np.cumsum([tr.size for tr in times], out=starts[1:])
    flat = (np.concatenate(times).astype(np.float64, copy=False) if n_channels
            else np.empty(0))
    args = (flat, starts, np.asarray(tiled, dtype=np.float64), float(dt), adj_m)
    global _PARALLEL_BROKEN
    if _HAVE_NUMBA and not _PARALLEL_BROKEN:
        try:
            set_num_threads(numba_threads())
            _sttc_upper(*args)
        except Exception as e:
            # numba loads its threading layer on the first parallel call, and
            # a build that is missing one (a frozen app, an unusual install)
            # fails here rather than at import. The serial kernel gives the
            # same matrix, just on one core.
            if "threading layer" not in str(e).lower():
                raise
            _PARALLEL_BROKEN = True
            warnings.warn(f"STTC runs on one core: numba could not start threads ({e})")
            _sttc_upper_serial(*args)
    else:
        _sttc_upper_serial(*args)
    lower = np.tril_indices(n_channels, -1)
    adj_m[lower] = adj_m.T[lower]

    adj_m[adj_m < 0] = 0.0
    adj_m[np.isnan(adj_m)] = 0.0
    return adj_m
