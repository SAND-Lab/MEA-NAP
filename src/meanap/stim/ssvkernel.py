"""Adaptive (locally-variable-bandwidth) kernel density estimate.

Port of ``ssvkernel.m`` (Shimazaki & Shinomoto 2010, "Kernel Bandwidth
Optimization in Spike Rate Estimation"). Used by the **population-level PSTH
plots** only — the CSV metrics use gaussian smoothing (see ``psth.py``), so this
is not on the headline parity path.

Deterministic for the 3-output call MEA-NAP uses (``[y, t, optw]``): the
bootstrap-CI branch (which needs the RNG) is only reached for ``nargout >= 6``.
The FFT-based smoothing yields a conjugate-symmetric spectrum, so ``ifft``
results are real up to numerical noise — we take the real part throughout, the
conventional approach for Python ports of this algorithm.
"""

from __future__ import annotations

import numpy as np

_M = 80  # number of bandwidths examined


def _logexp(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.empty_like(x)
    lo = x < 1e2
    out[lo] = np.log1p(np.exp(x[lo]))
    out[~lo] = x[~lo]
    return out


def _ilogexp(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.empty_like(x)
    lo = x < 1e2
    out[lo] = np.log(np.expm1(x[lo]))
    out[~lo] = x[~lo]
    return out


def _gauss(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    return 1.0 / np.sqrt(2 * np.pi) / w * np.exp(-(x ** 2) / 2.0 / (w ** 2))


def _fftkernel(x: np.ndarray, w: float) -> np.ndarray:
    """Gaussian FFT smoothing (port of ``fftkernel`` / Gauss branch of ``fftkernelWin``).

    Returns the **complex** ``ifft`` result (imaginary parts are numerical
    noise). MATLAB keeps them complex, and its ``min`` over the resulting
    ``C_local`` compares by magnitude — dropping the imaginary part here would
    flip occasional argmin picks and compound through the golden-section search
    (observed as a data-dependent ~5% divergence). See ``ssvkernel``.
    """
    L = x.shape[0]
    Lmax = L + 3 * w
    n = int(2 ** np.ceil(np.log2(Lmax)))
    X = np.fft.fft(x, n)
    f = np.concatenate([-np.arange(0, n // 2 + 1), np.arange(n // 2 - 1, 0, -1)]) / n
    K = np.exp(-0.5 * (w * 2 * np.pi * f) ** 2)
    y = np.fft.ifft(X * K, n)
    return np.real(y[:L])


def _histc(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """MATLAB ``histc``: bin k=[edges[k],edges[k+1]); last bin = ==edges[-1]; > ignored."""
    out = np.zeros(edges.shape[0])
    if x.size:
        idx = np.searchsorted(edges, x, side="right") - 1
        for k in idx:
            if 0 <= k < edges.shape[0] - 1:
                out[k] += 1
        out[-1] += np.sum(x == edges[-1])
    return out


def _cost_function(y_hist, N, t, dt, optws, WIN, g):
    """Port of the nested ``CostFunction`` — returns (Cg, yv, optwp)."""
    L = y_hist.shape[0]
    optwv = np.zeros(L)
    gs_all = optws / WIN[:, None]          # (M, L): optws(:,k)'/WIN per column
    gs_min = gs_all.min(axis=0)
    gs_max = gs_all.max(axis=0)
    win_min, win_max = WIN.min(), WIN.max()
    for k in range(L):
        if g > gs_max[k]:
            optwv[k] = win_min
        elif g < gs_min[k]:
            optwv[k] = win_max
        else:
            gs_k = gs_all[:, k]
            idx = np.flatnonzero(gs_k >= g)[-1]   # find(...,1,'last')
            optwv[k] = g * WIN[idx]

    # Nadaraya-Watson smoothing of the bandwidths
    optwp = np.zeros(L)
    wvg = optwv / g
    for k in range(L):
        Z = _gauss(t[k] - t, wvg)
        optwp[k] = np.sum(optwv * Z) / np.sum(Z)

    # Balloon density estimator (only over non-empty bins)
    nz = y_hist != 0
    yhnz = y_hist[nz]
    t_nz = t[nz]
    yv = np.empty(L)
    for k in range(L):
        yv[k] = np.sum(yhnz * dt * _gauss(t[k] - t_nz, optwp[k]))
    yv = yv * N / np.sum(yv * dt)

    cg = yv ** 2 - 2 * yv * y_hist + 2 / np.sqrt(2 * np.pi) / optwp * y_hist
    return float(np.sum(cg * dt)), yv, optwp


def ssvkernel(x: np.ndarray, tin: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(y, t, optw)`` — adaptive KDE of ``x`` evaluated at ``tin``.

    Faithful port of the ``[y,t,optw] = ssvkernel(x, tin)`` call path.
    """
    x = np.asarray(x, dtype=float).ravel()
    tin = np.asarray(tin, dtype=float).ravel()

    T = tin.max() - tin.min()
    x_ab = x[(x >= tin.min()) & (x <= tin.max())]
    # smallest nonzero gap between sorted samples
    dsort = np.diff(np.sort(x_ab))
    nz = dsort[dsort > 0]
    dt_samp = nz.min() if nz.size else np.inf

    if dt_samp > np.min(np.diff(tin)):
        t = np.linspace(tin.min(), tin.max(), int(min(np.ceil(T / dt_samp), 1e3)))
    else:
        t = tin
    dt = np.min(np.diff(t))

    y_hist = _histc(x_ab, t - dt / 2) / dt
    L = y_hist.shape[0]
    N = np.sum(y_hist * dt)

    lo = float(_ilogexp(np.array([5 * dt]))[0])   # MATLAB max(5*dt) == 5*dt (scalar)
    hi = float(_ilogexp(np.array([T]))[0])
    WIN = _logexp(np.linspace(lo, hi, _M))
    W = WIN

    c = np.zeros((_M, L))
    for j in range(_M):
        yh = _fftkernel(y_hist, W[j] / dt)
        c[j, :] = yh ** 2 - 2 * yh * y_hist + 2 / np.sqrt(2 * np.pi) / W[j] * y_hist

    optws = np.zeros((_M, L))
    for i in range(_M):
        C_local = np.zeros((_M, L))
        for j in range(_M):
            C_local[j, :] = _fftkernel(c[j, :], WIN[i] / dt)
        n = np.argmin(C_local, axis=0)
        optws[i, :] = W[n]

    # golden-section search over stiffness g
    tol = 1e-5
    a, b = 1e-12, 1.0
    phi = (np.sqrt(5) + 1) / 2
    c1 = (phi - 1) * a + (2 - phi) * b
    c2 = (2 - phi) * a + (phi - 1) * b
    f1, _, _ = _cost_function(y_hist, N, t, dt, optws, WIN, c1)
    f2, _, _ = _cost_function(y_hist, N, t, dt, optws, WIN, c2)

    yopt = None
    optw = None
    k = 1
    while abs(b - a) > tol * (abs(c1) + abs(c2)) and k < 30:
        # NB: assignments are sequential (not tuple-parallel) — MATLAB updates b/a
        # first, then derives the new c1/c2 from the *updated* bracket endpoint.
        if f1 < f2:
            b = c2
            c2 = c1
            c1 = (phi - 1) * a + (2 - phi) * b
            f2 = f1
            f1, yv1, optwp1 = _cost_function(y_hist, N, t, dt, optws, WIN, c1)
            yopt = yv1 / np.sum(yv1 * dt)
            optw = optwp1
        else:
            a = c1
            c1 = c2
            c2 = (2 - phi) * a + (phi - 1) * b
            f1 = f2
            f2, yv2, optwp2 = _cost_function(y_hist, N, t, dt, optws, WIN, c2)
            yopt = yv2 / np.sum(yv2 * dt)
            optw = optwp2
        k += 1

    if yopt is None:      # loop never ran (degenerate) — fall back to c1 solution
        _, yv1, optwp1 = _cost_function(y_hist, N, t, dt, optws, WIN, c1)
        yopt = yv1 / np.sum(yv1 * dt)
        optw = optwp1

    y = np.interp(tin, t, yopt)
    optw_out = np.interp(tin, t, optw)
    return y, tin, optw_out
