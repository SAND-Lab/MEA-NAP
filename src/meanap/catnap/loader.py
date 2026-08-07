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


def _load_ops_fields(
    plane0: Path, derived_root: str | Path | None, recording: str | None,
) -> tuple[float, np.ndarray | None]:
    """The two things the pipeline needs from ``ops.npy``: ``fs`` and the mean image.

    ``ops.npy`` is a pickled dict — 493 MB in the CAT-NAP example dataset, the
    single largest file in a suite2p folder — and it must be read in full to
    reach either field, because a pickle has no partial reads. Doing that once
    per recording per phase is merely slow locally; over a network it is by far
    the most expensive thing the loader does.

    So the extracted fields are cached in a small sidecar (a few MB, dominated
    by the projection image) and re-read from there. The cache is keyed only by
    location — ``ops.npy`` is suite2p output and does not change under a run —
    but is ignored if it is older than the file it came from, so re-running
    suite2p invalidates it.
    """
    from meanap.catnap.derived import OPS_CACHE_NAME, resolve_read, resolve_write_dir

    ops_path = plane0 / "ops.npy"
    cached = (resolve_read(plane0, derived_root, recording, OPS_CACHE_NAME)
              if recording else None)
    if cached is not None and (not ops_path.exists()
                               or cached.stat().st_mtime >= ops_path.stat().st_mtime):
        with np.load(cached) as data:
            img = data["mean_img"] if "mean_img" in data.files else None
            return float(data["fs"]), (np.asarray(img) if img is not None else None)

    ops = np.load(ops_path, allow_pickle=True).item()
    fs = float(ops["fs"])
    # meanImgE is suite2p's contrast-enhanced projection, made for exactly this
    # kind of display; meanImg is the raw average and is much flatter.
    mean_img = None
    for key in ("meanImgE", "meanImg"):
        if key in ops and np.ndim(ops[key]) == 2:
            mean_img = np.asarray(ops[key])
            break

    if recording:
        try:
            out = resolve_write_dir(plane0, derived_root, recording) / OPS_CACHE_NAME
            arrays = {"fs": np.array(fs)}
            if mean_img is not None:
                arrays["mean_img"] = np.asarray(mean_img, dtype=np.float32)
            np.savez_compressed(out, **arrays)
        except OSError:
            # A read-only suite2p folder with no derived root configured: the
            # cache is an optimisation, never a requirement.
            pass

    return fs, mean_img


def load_suite2p(
    plane0_dir: str | Path,
    derived_root: str | Path | None = None,
    recording: str | None = None,
) -> Suite2pData:
    """
    Load all available suite2p outputs from *plane0_dir*.

    Required files: F.npy, iscell.npy, stat.npy, ops.npy
    Optional files: spks.npy, Fdenoised.npy, peakStartFrames.npy,
    peakEndFrames.npy, peakHeights.npy, eventAreas.npy, timePoints.npy

    ``derived_root`` + ``recording`` locate files this pipeline produced —
    denoising outputs and the ``ops`` field cache — which may live outside the
    suite2p folder when it is read-only or remote (see
    :mod:`meanap.catnap.derived`). Omit both for the historical behaviour of
    reading and writing everything in place.
    """
    from meanap.catnap.derived import resolve_read

    d = Path(plane0_dir)

    def derived(name: str) -> Path | None:
        if recording:
            return resolve_read(d, derived_root, recording, name)
        path = d / name
        return path if path.exists() else None

    F = np.load(d / "F.npy")
    iscell = np.load(d / "iscell.npy")

    stat = np.load(d / "stat.npy", allow_pickle=True)
    x_loc = np.array([s["med"][0] for s in stat])
    y_loc = np.array([s["med"][1] for s in stat])
    xy_loc = np.stack([x_loc, y_loc])

    fs, mean_img = _load_ops_fields(d, derived_root, recording)

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

    # Load pre-computed denoising outputs if present. These are *derived* files,
    # so they may live outside the suite2p folder — `derived` resolves both.
    denoised = derived("Fdenoised.npy")
    if denoised is not None:
        data.F_denoised = np.load(denoised)
        time_points = derived("timePoints.npy")
        data.time_points = (np.load(time_points) if time_points is not None
                            else np.arange(n_frames) / fs)
        starts = derived("peakStartFrames.npy")
        if starts is not None:
            data.peak_start_frames = np.load(starts)
            data.peak_end_frames = np.load(derived("peakEndFrames.npy"))
            data.peak_heights = np.load(derived("peakHeights.npy"))
            data.event_areas = np.load(derived("eventAreas.npy"))

    return data
