"""Known-answer controls, and the threshold they set.

A match rate means nothing without knowing what the pipeline scores when the
answer is "no match". These controls supply the floor, and the floor is what the
tracking threshold has to clear.

**The shift control must move the ROIs only.** An earlier control translated the
FOV image along with them, so its stripes moved with the sample -- which is
precisely what a real recording does not do. It flattered ROICaT (the shift was
recoverable from the image) and, once pre-registration was added, it
double-corrected and read as a catastrophic failure. :func:`roi_shift_control`
moves the ROIs and leaves the image alone, which is how stage drift presents.

Measured on the Mecp2 dataset:

============================  ==================  =========================
control                       baseline pipeline   pre-registered pipeline
============================  ==================  =========================
ROI-only shift (same cells)   0.023               1.000
foreign FOV, median           --                  0.023
foreign FOV, p95              --                  0.069
foreign FOV, max (n=15)       --                  0.091
============================  ==================  =========================

So 0.05 sits *below* the floor and must not be used. The default threshold is
0.10; 0.15 is safe. **Re-measure for a new rig or dataset** rather than
inheriting these numbers -- and use at least ~15 foreign pairs, because two is
not a distribution.

The floor is worst when a large session is paired with a small one, since
``frac_of_smaller`` divides by the small count.
"""

from __future__ import annotations

import numpy as np

#: Enough foreign pairs to quote a p95 rather than a couple of points.
MIN_FOREIGN_PAIRS = 15


def roi_shift_control(stat: np.ndarray, dy: int, dx: int, frame_px: int) -> np.ndarray:
    """Move the ROIs by a known offset, leaving the FOV image untouched.

    ROIs pushed off the edge are **dropped, not clipped**: a cell that leaves
    the frame genuinely cannot be matched, whereas clipping would pile deformed
    masks against the border and invent structure there.
    """
    out = []
    for roi in stat:
        moved = dict(roi)
        ypix = np.asarray(roi["ypix"]) + dy
        xpix = np.asarray(roi["xpix"]) + dx
        if (ypix.min() < 0 or xpix.min() < 0
                or ypix.max() >= frame_px or xpix.max() >= frame_px):
            continue
        moved["ypix"] = ypix
        moved["xpix"] = xpix
        moved["med"] = [roi["med"][0] + dy, roi["med"][1] + dx]
        out.append(moved)
    return np.array(out, dtype=object)


def summarise_floor(foreign_rates: list[float]) -> dict:
    """Turn foreign-FOV match rates into a threshold recommendation."""
    rates = np.asarray([r for r in foreign_rates if np.isfinite(r)], dtype=float)
    if rates.size == 0:
        return {"n": 0, "note": "no foreign controls measured"}
    out = {
        "n": int(rates.size),
        "median": float(np.median(rates)),
        "p95": float(np.percentile(rates, 95)),
        "max": float(rates.max()),
    }
    # clear the observed maximum, then round up to a readable step
    out["recommended_threshold"] = float(np.ceil(out["max"] * 20) / 20) or 0.05
    if rates.size < MIN_FOREIGN_PAIRS:
        out["warning"] = (f"only {rates.size} foreign pairs; "
                          f"{MIN_FOREIGN_PAIRS}+ needed to quote a floor")
    return out
