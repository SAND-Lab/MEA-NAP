"""Solve a per-session offset for each chain, and stage the shifted ROIs.

ROICaT cannot register this data itself (see the package docstring), so the
offsets are solved here from the ROI footprints and applied before ROICaT sees
anything. Three things about this are not obvious and each of them cost a full
dataset run to learn:

**Solve over all pairs, and weight them.** Chaining consecutive days accumulates
error, and plain least squares over every pair is worse still: a pair on
genuinely different fields contributes a meaningless displacement, and letting
it constrain the fit drags sessions that were already aligned. One chain moved
from a 12 px offset to 89 px that way. Pairs below :data:`RELIABLE_NCC` are
dropped, the rest are weighted by how well their layouts agree, and each
**connected component is solved separately** so a session on a different field
is left where it is rather than averaged into a meaningless common frame.

**Do not correct an offset you cannot measure.** Shifting an already-aligned
chain injects more error than it removes -- "correcting" 8 px offsets, which is
one density bin, made 47 day-pairs worse. :data:`MIN_SHIFT_PX` is two bins:
both the measurement resolution and the empirical cliff at which matching
collapsed.

**Pad the canvas, do not clip.** Growing the frame to absorb the offsets keeps
every ROI; clipping would pile deformed masks against the border. Padding was
verified harmless on its own (0.742 against an unshifted 0.740).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from meanap.catnap.tracking.footprint import DENSITY_BIN_PX, displacement

#: Below this ROI-layout agreement a day-pair is a different field of view and
#: its measured displacement is noise, not a constraint. Calibrated against the
#: controls: same-FOV scores 0.96-1.00, rotated or foreign 0.18-0.35.
RELIABLE_NCC = 0.45

#: Chains whose measured offset is smaller than this are passed through
#: untouched. Two density bins.
MIN_SHIFT_PX = 16.0


@dataclass
class PairMeasurement:
    """What the footprints say about one day-pair."""

    a: int
    b: int
    dy: float
    dx: float
    peak_z: float
    aligned_ncc: float

    @property
    def shift_px(self) -> float:
        return float(np.hypot(self.dy, self.dx))


@dataclass
class ChainOffsets:
    """Per-session offsets for one chain, and why they are what they are."""

    offsets: np.ndarray                      # (n_sessions, 2) int, (dy, dx)
    pairs: list[PairMeasurement] = field(default_factory=list)
    components: np.ndarray | None = None     # which sessions were solved together

    @property
    def median_shift_px(self) -> float:
        """Median measured offset across pairs -- what :data:`MIN_SHIFT_PX` gates on."""
        return float(np.median([p.shift_px for p in self.pairs])) if self.pairs else 0.0

    @property
    def should_register(self) -> bool:
        return self.median_shift_px >= MIN_SHIFT_PX


def measure_pairs(density_maps: list[np.ndarray], *, bin_px: int = DENSITY_BIN_PX
                  ) -> list[PairMeasurement]:
    """Displacement and layout agreement for every day-pair in a chain."""
    out = []
    for i in range(len(density_maps)):
        for j in range(i + 1, len(density_maps)):
            dy, dx, pz, ncc = displacement(density_maps[i], density_maps[j], bin_px=bin_px)
            out.append(PairMeasurement(i, j, dy, dx, pz, ncc))
    return out


def solve_offsets(
    density_maps: list[np.ndarray],
    *,
    reliable_ncc: float = RELIABLE_NCC,
    bin_px: int = DENSITY_BIN_PX,
) -> ChainOffsets:
    """Per-session offsets putting a chain's sessions in one common frame."""
    n = len(density_maps)
    pairs = measure_pairs(density_maps, bin_px=bin_px)

    rows, rhs, weights, edges = [], [], [], []
    for p in pairs:
        if p.aligned_ncc < reliable_ncc:
            continue
        # displacement() peaks at (dy, dx) when a feature at p in session i sits
        # at p - (dy, dx) in session j, so o_j - o_i = -(dy, dx)
        rows.append((p.a, p.b))
        rhs.append([-p.dy, -p.dx])
        weights.append(p.aligned_ncc - reliable_ncc)
        edges.append((p.a, p.b))

    offsets = np.zeros((n, 2), dtype=float)
    if not edges:
        return ChainOffsets(offsets=offsets.astype(int), pairs=pairs,
                            components=np.arange(n))

    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    ii = [a for a, _ in edges] + [b for _, b in edges]
    jj = [b for _, b in edges] + [a for a, _ in edges]
    adj = coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(n, n))
    n_comp, comp = connected_components(adj, directed=False)

    for c in range(n_comp):
        members = np.nonzero(comp == c)[0]
        if members.size < 2:
            continue  # nothing to align this session against; leave it alone
        index = {m: k for k, m in enumerate(members)}
        keep = [k for k, (a, _) in enumerate(edges) if comp[a] == c]
        A = np.zeros((len(keep) + 1, members.size))
        B = np.zeros((len(keep) + 1, 2))
        for row, k in enumerate(keep):
            a, b = edges[k]
            w = weights[k]
            A[row, index[a]], A[row, index[b]] = -w, w
            B[row] = np.asarray(rhs[k]) * w
        A[-1, :] = 1.0          # pin the component's mean offset at zero
        solution, *_ = np.linalg.lstsq(A, B, rcond=None)
        offsets[members] = solution

    return ChainOffsets(offsets=np.round(offsets).astype(int), pairs=pairs,
                        components=comp)


def verify_offsets(density_maps: list[np.ndarray], offsets: np.ndarray,
                   *, bin_px: int = DENSITY_BIN_PX) -> dict[str, float]:
    """Residual displacement after applying the offsets.

    Checks the sign convention empirically instead of trusting the algebra: if
    the offsets are right the residual collapses towards zero, and if the sign
    were inverted it would roughly double.
    """
    shifted = []
    for dens, (oy, ox) in zip(density_maps, offsets):
        shifted.append(np.roll(np.roll(dens, -int(round(oy / bin_px)), axis=0),
                               -int(round(ox / bin_px)), axis=1))
    before = [p.shift_px for p in measure_pairs(density_maps, bin_px=bin_px)]
    after = [p.shift_px for p in measure_pairs(shifted, bin_px=bin_px)]
    return {
        "median_before_px": float(np.median(before)) if before else 0.0,
        "median_after_px": float(np.median(after)) if after else 0.0,
        "max_after_px": float(np.max(after)) if after else 0.0,
    }


def shift_stat(stat: np.ndarray, dy: int, dx: int, pad_y: int, pad_x: int,
               frame: tuple[int, int]) -> np.ndarray:
    """Move one session's ROIs into the padded common frame."""
    height, width = frame
    out = []
    for roi in stat:
        moved = dict(roi)
        ypix = np.asarray(roi["ypix"]) - dy + pad_y
        xpix = np.asarray(roi["xpix"]) - dx + pad_x
        if (ypix.min() < 0 or xpix.min() < 0
                or ypix.max() >= height or xpix.max() >= width):
            continue    # only reachable if the canvas was sized too small
        moved["ypix"] = ypix
        moved["xpix"] = xpix
        moved["med"] = [roi["med"][0] - dy + pad_y, roi["med"][1] - dx + pad_x]
        out.append(moved)
    return np.array(out, dtype=object)


def padded_frame(offsets: np.ndarray, frame_px: int) -> tuple[int, int, int, int]:
    """Canvas size and origin padding that hold every session's shifted ROIs.

    Returns ``(height, width, pad_y, pad_x)``.
    """
    oy, ox = offsets[:, 0], offsets[:, 1]
    pad_y = int(max(0, oy.max()))
    pad_x = int(max(0, ox.max()))
    span_y = pad_y + int(max(0, -oy.min()))
    span_x = pad_x + int(max(0, -ox.min()))
    return frame_px + span_y, frame_px + span_x, pad_y, pad_x
