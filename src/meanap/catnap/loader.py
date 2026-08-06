"""Load suite2p output files into numpy arrays."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Suite2pData:
    """All arrays loaded from one suite2p/plane0 directory."""

    # Raw fluorescence, shape (n_cells_all, n_frames)
    F: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    # Inferred spike probabilities, shape (n_cells_all, n_frames)
    spks: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    # iscell[:,0] is 1 for cells, 0 for non-cells; shape (n_rois, 2)
    iscell: np.ndarray = field(default_factory=lambda: np.empty((0, 2)))
    # XY centroids, shape (2, n_rois)
    xy_loc: np.ndarray = field(default_factory=lambda: np.empty((2, 0)))
    # Sampling rate (Hz)
    fs: float = 0.0
    # Number of frames
    n_frames: int = 0
    # Duration in seconds
    duration_s: float = 0.0

    # Pre-computed denoising outputs (present only if Fdenoised.npy exists)
    F_denoised: np.ndarray | None = None           # (n_rois, n_frames)
    peak_start_frames: np.ndarray | None = None    # (n_rois, max_peaks), NaN-padded
    peak_end_frames: np.ndarray | None = None
    peak_heights: np.ndarray | None = None
    event_areas: np.ndarray | None = None
    time_points: np.ndarray | None = None          # (n_frames,) in seconds
    # suite2p's mean projection of the registered movie, (height, width) —
    # the enhanced ``meanImgE`` when present, else the raw ``meanImg``. Used as
    # the backdrop for spatial network plots so nodes can be checked against
    # the actual field of view.
    mean_img: np.ndarray | None = None

    # Derived: cell-only views (filtered by iscell)
    @property
    def cell_mask(self) -> np.ndarray:
        return self.iscell[:, 0].astype(bool)

    @property
    def n_cells(self) -> int:
        return int(self.cell_mask.sum())

    @property
    def F_cells(self) -> np.ndarray:
        """F for labelled cells only, shape (n_cells, n_frames)."""
        return self.F[self.cell_mask]

    @property
    def spks_cells(self) -> np.ndarray:
        return self.spks[self.cell_mask]

    @property
    def xy_cells(self) -> np.ndarray:
        """XY centroids for cells, shape (n_cells, 2)."""
        return self.xy_loc[:, self.cell_mask].T

    @property
    def F_denoised_cells(self) -> np.ndarray | None:
        if self.F_denoised is None:
            return None
        return self.F_denoised[self.cell_mask]


def load_suite2p(plane0_dir: str | Path) -> Suite2pData:
    """
    Load all available suite2p outputs from *plane0_dir*.

    Required files: F.npy, iscell.npy, stat.npy, ops.npy
    Optional files: spks.npy, Fdenoised.npy, peakStartFrames.npy,
    peakEndFrames.npy, peakHeights.npy, eventAreas.npy, timePoints.npy
    """
    d = Path(plane0_dir)

    F = np.load(d / "F.npy")
    iscell = np.load(d / "iscell.npy")

    stat = np.load(d / "stat.npy", allow_pickle=True)
    x_loc = np.array([s["med"][0] for s in stat])
    y_loc = np.array([s["med"][1] for s in stat])
    xy_loc = np.stack([x_loc, y_loc])

    ops = np.load(d / "ops.npy", allow_pickle=True).item()
    fs = float(ops["fs"])
    # meanImgE is suite2p's contrast-enhanced projection, made for exactly this
    # kind of display; meanImg is the raw average and is much flatter.
    mean_img = None
    for key in ("meanImgE", "meanImg"):
        if key in ops and np.ndim(ops[key]) == 2:
            mean_img = np.asarray(ops[key])
            break

    n_frames = F.shape[1]
    duration_s = n_frames / fs

    spks = np.load(d / "spks.npy") if (d / "spks.npy").exists() else np.zeros_like(F)

    data = Suite2pData(
        F=F,
        spks=spks,
        iscell=iscell,
        xy_loc=xy_loc,
        fs=fs,
        n_frames=n_frames,
        duration_s=duration_s,
        mean_img=mean_img,
    )

    # Load pre-computed denoising outputs if present
    if (d / "Fdenoised.npy").exists():
        data.F_denoised = np.load(d / "Fdenoised.npy")
        data.time_points = (np.load(d / "timePoints.npy")
                            if (d / "timePoints.npy").exists()
                            else np.arange(n_frames) / fs)
        if (d / "peakStartFrames.npy").exists():
            data.peak_start_frames = np.load(d / "peakStartFrames.npy")
            data.peak_end_frames = np.load(d / "peakEndFrames.npy")
            data.peak_heights = np.load(d / "peakHeights.npy")
            data.event_areas = np.load(d / "eventAreas.npy")

    return data
