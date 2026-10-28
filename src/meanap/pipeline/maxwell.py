"""MaxWell Biosystems ``.raw.h5`` recordings: metadata and TTL events only.

A spike-sorted import (:mod:`meanap.pipeline.sorted_import`) needs four things
from the raw recording and none of its voltage: the sampling rate, the exact
duration, where each recorded electrode sits, and the TTL events a stimulus
left. On a MaxOne the voltage is ``(n_routed, n_frames)`` uint16 — 4.7 GB for
two minutes on 941 electrodes — so everything here reads small datasets only.

Two file layouts exist. The *legacy* one (MaxOne, ``data_store/data0000``) is
what the MaxOne test data uses and what this module is checked
against. The newer one (MaxTwo and recent MaxOne software,
``recordings/rec0000/well000``) keeps the same ``groups/routed`` and
``settings`` datasets under a different parent; :func:`read_maxwell_meta`
finds either, but only the legacy layout has been verified on a real file.

Coordinates are MaxWell's own, in µm, with y increasing *down* the array (as
MaxLab draws it). Turning them into MEA-NAP plot coordinates (y up) is the
caller's job — see :func:`meanap.pipeline.sorted_import.layout_coords_from_um`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: The TTL word a MaxWell legacy file records in ``bits``, one row per change.
TTL_DATASET = "bits/0000"


@dataclass(frozen=True)
class MaxwellMeta:
    """What an import needs from a MaxWell recording, without its voltage.

    ``channels``, ``electrodes`` and ``xy_um`` are in the *row order of the
    routed raw array* — the order a sorter that read the file numbers its
    channels in (SpyKING CIRCUS's electrode 0 is row 0).
    """

    path: Path
    fs: float
    n_frames: int
    #: Frame number of the first sample. TTL events are stamped in frames on
    #: the same clock, so ``(frameno - first_frame) / fs`` is seconds into the
    #: recording.
    first_frame: int
    channels: np.ndarray
    electrodes: np.ndarray
    xy_um: np.ndarray
    lsb_v: float | None = None
    gain: float | None = None
    layout: str = "legacy"

    @property
    def duration_s(self) -> float:
        return self.n_frames / self.fs


def is_maxwell_h5(path: str | Path) -> bool:
    """Whether *path* is a MaxWell HDF5 recording (either layout)."""
    import h5py

    try:
        with h5py.File(path, "r") as f:
            return "mxw_version" in f or "data_store" in f or "wells" in f \
                or ("recordings" in f and "wellplate" in f)
    except (OSError, ValueError):
        return False


def _recording_group(f, well: int, rec: int):
    """The group holding ``groups/routed`` and ``settings``, and its layout name."""
    legacy = f.get(f"data_store/data{rec:04d}")
    if legacy is not None and "groups" in legacy:
        return legacy, "legacy"
    new = f.get(f"recordings/rec{rec:04d}/well{well:03d}")
    if new is not None and "groups" in new:
        return new, "new"
    raise ValueError(
        f"{f.filename}: no MaxWell recording found (looked for "
        f"data_store/data{rec:04d} and recordings/rec{rec:04d}/well{well:03d})")


def read_maxwell_meta(path: str | Path, well: int = 0, rec: int = 0) -> MaxwellMeta:
    """Sampling rate, duration and electrode positions of a MaxWell recording."""
    import h5py

    path = Path(path)
    with h5py.File(path, "r") as f:
        g, layout = _recording_group(f, well, rec)
        routed = g["groups/routed"]
        frame_nos = routed["frame_nos"][:].astype(np.int64)
        channels = routed["channels"][:].astype(np.int64)
        settings = g["settings"]
        fs = float(np.ravel(settings["sampling"][()])[0])
        mapping = settings["mapping"][:]
        lsb = float(np.ravel(settings["lsb"][()])[0]) if "lsb" in settings else None
        gain = float(np.ravel(settings["gain"][()])[0]) if "gain" in settings else None

    if frame_nos.size > 1 and np.any(np.diff(frame_nos) != 1):
        # Dropped frames would make sample index ≠ time. Not seen so far; say
        # so loudly rather than misplace every spike after the gap.
        n_gaps = int(np.sum(np.diff(frame_nos) != 1))
        raise ValueError(f"{path.name}: {n_gaps} gap(s) in frame numbers — "
                         "dropped frames are not supported")

    by_channel = {int(c): (int(e), float(x), float(y))
                  for c, e, x, y in zip(mapping["channel"], mapping["electrode"],
                                        mapping["x"], mapping["y"])}
    missing = [int(c) for c in channels if int(c) not in by_channel]
    if missing:
        raise ValueError(f"{path.name}: {len(missing)} routed channel(s) have no "
                         f"entry in settings/mapping (e.g. {missing[:5]})")
    rows = [by_channel[int(c)] for c in channels]
    return MaxwellMeta(
        path=path, fs=fs, n_frames=int(frame_nos.size),
        first_frame=int(frame_nos[0]) if frame_nos.size else 0,
        channels=channels,
        electrodes=np.array([r[0] for r in rows], dtype=np.int64),
        xy_um=np.array([(r[1], r[2]) for r in rows], dtype=float).reshape(-1, 2),
        lsb_v=lsb, gain=gain, layout=layout,
    )


def read_maxwell_ttl(path: str | Path, meta: MaxwellMeta | None = None
                     ) -> tuple[np.ndarray, np.ndarray]:
    """The TTL word at each change: ``(times_s, words)``.

    ``times_s`` is seconds from the first recorded frame. Interpreting the
    words — which bit is a frame sync, which value marks a stimulus — is
    :mod:`meanap.stim.events`'s job.
    """
    import h5py

    meta = meta or read_maxwell_meta(path)
    with h5py.File(path, "r") as f:
        if TTL_DATASET not in f:
            if meta.layout != "legacy":
                raise NotImplementedError(
                    f"{Path(path).name}: TTL events in the newer MaxWell layout "
                    "are not supported yet")
            return np.zeros(0), np.zeros(0, dtype=np.int64)
        bits = f[TTL_DATASET][:]
    times = (bits["frameno"].astype(np.int64) - meta.first_frame) / meta.fs
    return times.astype(float), bits["bits"].astype(np.int64)
