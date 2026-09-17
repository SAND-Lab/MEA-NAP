"""ROI footprints as a registration signal.

The obvious way to align two recordings is to correlate their mean images, and
on this data it does not work: every ``ops_fields.npz`` mean image carries the
same vertical scan-line texture, and it dominates the pixel variance. Unrelated
cultures correlate at 0.87; an image correlates *less* with itself shifted 1 px
(0.62) than with a different recording (0.91); phase correlation pins every pair
at exactly (0, 0) with a huge peak. Five linear-filtering variants were tried
and the best same-FOV/different-FOV margin was 0.66 vs 0.53.

So registration here uses the **ROI masks** instead. Footprints are rasterised
into coarse bins and cross-correlated; the peak gives the shift and its value,
with both maps unit-normalised, is the agreement between the two ROI layouts
once that shift is undone.

Calibration on known-answer controls (``controls.py``):

=========================  ==============  =============
control                    measured shift  aligned NCC
=========================  ==============  =============
identity                   0.0 px          1.000
translate by (150, -90)    175.6 px        0.960
rotate 90 degrees          541 px          0.345
different field of view    312 / 556 px    0.300 / 0.177
=========================  ==============  =============

The estimator recovers a 175.0 px truth as 175.6, and ``aligned_ncc`` separates
same-FOV (0.96-1.00) from unrelated (0.18-0.35).
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.signal import fftconvolve

#: Bin size for the density map. 8 px is ~2 ROI diameters (suite2p ROIs here are
#: ~4 px across), which is fine enough to localise a shift and coarse enough
#: that the map is not dominated by individual cells appearing and disappearing.
DENSITY_BIN_PX = 8

#: Gaussian smoothing of the binned map, in bins.
DENSITY_SMOOTH_BINS = 1.5

#: Correlation peaks beyond this fraction of the frame are not considered. A
#: real stage drift is a small part of the field; a peak out at the edge is the
#: wrap-around of an unrelated pair.
MAX_SHIFT_FRACTION = 0.4


def density_map(
    stat: np.ndarray,
    frame_px: int,
    *,
    bin_px: int = DENSITY_BIN_PX,
    smooth_bins: float = DENSITY_SMOOTH_BINS,
) -> np.ndarray:
    """Rasterise lam-weighted ROI footprints into a smoothed, binned map.

    ``stat`` must already be filtered to ``iscell``. Passing the unfiltered
    array is the single most damaging mistake available here: the ~85% rejected
    ROIs dominate the similarity graph and tracking yield drops from 45% to 6%.
    """
    n_bin = int(np.ceil(frame_px / bin_px))
    dens = np.zeros((n_bin, n_bin), dtype=np.float64)
    for roi in stat:
        ypix = np.asarray(roi["ypix"])
        xpix = np.asarray(roi["xpix"])
        lam = np.asarray(roi["lam"], dtype=float)
        keep = (ypix >= 0) & (xpix >= 0) & (ypix < frame_px) & (xpix < frame_px)
        if not keep.any():
            continue
        np.add.at(dens, (ypix[keep] // bin_px, xpix[keep] // bin_px), lam[keep])
    return gaussian_filter(dens, smooth_bins)


def displacement(
    a: np.ndarray,
    b: np.ndarray,
    *,
    bin_px: int = DENSITY_BIN_PX,
    max_shift_fraction: float = MAX_SHIFT_FRACTION,
) -> tuple[float, float, float, float]:
    """Shift of ``b`` relative to ``a``, in pixels, with two quality numbers.

    Returns ``(dy, dx, peak_z, aligned_ncc)``.

    Sign convention: the peak sits at ``(dy, dx)`` when a feature at position
    ``p`` in ``a`` sits at ``p - (dy, dx)`` in ``b``. So ``b`` is brought into
    ``a``'s frame by **adding** ``(dy, dx)`` to its coordinates.
    ``register.solve_offsets`` encodes this as ``o_j - o_i = -(dy, dx)``, and
    ``verify_offsets`` checks it empirically rather than trusting the algebra.

    ``aligned_ncc`` is the correlation of the two ROI layouts after the shift --
    both maps are unit-normalised, so the peak itself is that correlation. It is
    the same-field-of-view test. ``peak_z`` is how far the peak stands out of
    its own surface in SDs; a flat surface means the two layouts share no common
    structure at any offset.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a - a.mean()
    b = b - b.mean()
    a = a / (np.linalg.norm(a) or 1.0)
    b = b / (np.linalg.norm(b) or 1.0)

    surface = fftconvolve(a, b[::-1, ::-1], mode="full")

    n_bin = a.shape[0]
    limit = max(int(n_bin * max_shift_fraction), 1)
    centre = n_bin - 1
    lo, hi = centre - limit, centre + limit + 1
    window = surface[lo:hi, lo:hi]

    idx = np.unravel_index(int(np.argmax(window)), window.shape)
    peak = float(window[idx])
    dy = float((idx[0] + lo - centre) * bin_px)
    dx = float((idx[1] + lo - centre) * bin_px)
    peak_z = float((peak - np.median(surface)) / (surface.std() or 1.0))
    return dy, dx, peak_z, peak
