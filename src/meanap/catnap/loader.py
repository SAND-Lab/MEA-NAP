"""Load suite2p output files into numpy arrays."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from meanap.pipeline.atomic import atomic_savez


class Suite2pOutputMismatch(ValueError):
    """``iscell.npy`` describes a different ROI list from ``F.npy``/``stat.npy``.

    Nothing downstream can proceed: ``iscell[:, 0]`` selects rows of ``F`` and
    ``stat``, so if the row counts differ there is no way to tell which
    classification belongs to which trace. Raised at load time, with the counts
    named, rather than letting it surface as a bare numpy ``IndexError`` from
    inside the adjacency step — which is both unreadable and many minutes late,
    since every ROI is denoised first.
    """


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
        # This sidecar is ours and is cheap to rebuild, so a damaged one is
        # deleted and regenerated rather than raised over — otherwise a single
        # interrupted write would fail this recording on every future run.
        # ``guard_readable`` is the same treatment resume artefacts get.
        from meanap.pipeline.atomic import guard_readable

        if guard_readable(cached):
            with np.load(cached) as data:
                img = data["mean_img"] if "mean_img" in data.files else None
                return float(data["fs"]), (np.asarray(img) if img is not None
                                           else None)

    ops = _load_npy(ops_path, allow_pickle=True).item()
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
            atomic_savez(out, compressed=True, **arrays)
        except OSError:
            # A read-only suite2p folder with no derived root configured: the
            # cache is an optimisation, never a requirement.
            pass

    return fs, mean_img


def _check_roi_counts(
    plane0: Path, counts: dict[str, int], iscell: np.ndarray,
) -> None:
    """Refuse a suite2p folder whose files disagree about how many ROIs there are.

    The commonest cause has a signature worth reporting back. suite2p's GUI
    *prepends* hand-drawn ROIs and writes them into ``iscell.npy`` with a
    classifier probability of exactly ``1.0`` (``drawroi.py``:
    ``np.concatenate((np.ones((nROIs, 2)), iscell_prob))``), saving ``stat``,
    ``F``, ``Fneu`` and ``spks`` in the same breath. When only ``iscell.npy``
    grew, that save was incomplete — and the leading block of probability-1.0
    rows says so, and says how far out of step the two files are.

    That diagnosis is offered, not acted on. Dropping the block would line the
    files back up, but a wrong guess silently reassigns every cell label to a
    different neuron, so the repair belongs in suite2p where the traces exist.
    """
    if len(set(counts.values())) == 1:
        return
    n_traces = counts["F.npy"]

    lines = [
        f"The suite2p output in {plane0} is inconsistent — its files disagree "
        "about how many ROIs the recording has:",
        "",
        *(f"    {name:<12} {n} ROIs" for name, n in counts.items()),
        "",
        "iscell.npy says which ROIs are cells by row position, so MEA-NAP "
        "cannot tell which classification belongs to which trace.",
    ]

    # ``iscell[:, 1]`` is a probability, so an exact 1.0 is not something the
    # classifier produces by chance.
    drawn = np.nonzero(iscell[:, 1] == 1.0)[0]
    extra = len(iscell) - n_traces
    if extra > 0 and len(drawn) == extra and drawn.max() == extra - 1:
        lines += [
            "",
            f"The first {extra} rows of iscell.npy have a classifier "
            f"probability of exactly 1.0, which is what suite2p writes for ROIs "
            "drawn by hand in its GUI — and it prepends them. So this folder "
            f"looks like {extra} hand-drawn ROIs that reached iscell.npy while "
            "the matching save of stat.npy / F.npy / Fneu.npy / spks.npy did "
            "not: iscell row N describes ROI N minus "
            f"{extra} of the other files.",
            "",
            "Re-open the recording in the suite2p GUI and save it again so all "
            "five files describe the same ROI list. MEA-NAP will not realign "
            "them itself — guessing wrong would attach every cell label to the "
            "wrong neuron.",
        ]
    else:
        lines += [
            "",
            "Re-run or re-save the recording in suite2p so all of its files "
            "describe the same ROI list.",
        ]
    raise Suite2pOutputMismatch("\n".join(lines))


class UnreadableSuite2pFile(RuntimeError):
    """A ``.npy`` in a suite2p folder is empty, truncated, or not a ``.npy``.

    Raised in place of numpy's own message, which names neither the file nor
    the recording: ``EOFError: No data left in file`` is what an empty ``.npy``
    produces, and on a batch of hundreds of recordings that alone is not enough
    to act on.
    """


def _load_npy(path: Path, *, allow_pickle: bool = False):
    """``np.load`` that says which file failed, and what to do about it.

    Empty and truncated ``.npy`` files are the two ways an interrupted or
    out-of-space write shows up later, and both surface here rather than as a
    bare numpy error three frames down.
    """
    try:
        return np.load(path, allow_pickle=allow_pickle)
    except (EOFError, ValueError, OSError) as exc:
        size = path.stat().st_size if path.exists() else None
        detail = ("is empty (0 bytes)" if size == 0 else
                  f"could not be read ({exc})" if size else "is missing")
        raise UnreadableSuite2pFile(
            f"{path} {detail}. A suite2p .npy in this state is usually the "
            f"result of a run, download or copy that was interrupted part-way. "
            f"Delete the file and let it be re-fetched or re-created; if it is "
            f"empty at the source, the recording needs re-exporting from "
            f"suite2p."
        ) from exc


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

    F = _load_npy(d / "F.npy")
    iscell = _load_npy(d / "iscell.npy")
    stat = _load_npy(d / "stat.npy", allow_pickle=True)
    spks = (_load_npy(d / "spks.npy") if (d / "spks.npy").exists()
            else np.zeros_like(F))

    # Before anything reads a row of them: every one of these is indexed by
    # ``iscell[:, 0]``, so they all have to be the same length.
    _check_roi_counts(d, {"F.npy": F.shape[0], "stat.npy": len(stat),
                          "spks.npy": spks.shape[0], "iscell.npy": len(iscell)},
                      iscell)

    x_loc = np.array([s["med"][0] for s in stat])
    y_loc = np.array([s["med"][1] for s in stat])
    xy_loc = np.stack([x_loc, y_loc])

    fs, mean_img = _load_ops_fields(d, derived_root, recording)

    n_frames = F.shape[1]
    duration_s = n_frames / fs

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
        data.F_denoised = _load_npy(denoised)
        time_points = derived("timePoints.npy")
        data.time_points = (_load_npy(time_points) if time_points is not None
                            else np.arange(n_frames) / fs)
        # The four peak arrays are written together and indexed together, so
        # they are taken together: a folder holding some of them is a folder
        # whose denoising was interrupted, and reading the survivors would
        # silently analyse a recording against half a peak set. Older runs
        # wrote Fdenoised first, so this is the shape an interrupt left behind.
        peaks = {name: derived(name) for name in
                 ("peakStartFrames.npy", "peakEndFrames.npy",
                  "peakHeights.npy", "eventAreas.npy")}
        present = {n: p for n, p in peaks.items() if p is not None}
        if len(present) == len(peaks):
            data.peak_start_frames = _load_npy(present["peakStartFrames.npy"])
            data.peak_end_frames = _load_npy(present["peakEndFrames.npy"])
            data.peak_heights = _load_npy(present["peakHeights.npy"])
            data.event_areas = _load_npy(present["eventAreas.npy"])
        elif present:
            raise UnreadableSuite2pFile(
                f"{d}: denoising left only "
                f"{', '.join(sorted(present))} — {', '.join(sorted(set(peaks) - set(present)))} "
                f"never got written, so the previous denoising run was "
                f"interrupted. Delete the derived files for this recording "
                f"(including Fdenoised.npy) and let it denoise again.")

    return data
