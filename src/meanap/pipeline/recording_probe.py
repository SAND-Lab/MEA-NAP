"""Read a recording's sampling rate and channels without loading it, and say
which electrode layout the recordings were made on.

The sampling rate is never something to ask for: every format stores it, and
every step already reads each recording's own. The layout is not stored as
such, but the channels give it away:

=====================================  ==========================
What the files show                    Layout
=====================================  ==========================
an MCS ``.h5``                         MCS60, or MCS59 at 59 channels
an Axion ``.raw``                      Axion64, or Axion16 at 16 per well
a ``.mat`` with 16 channels            Axion16
a ``.mat`` with 59 / 60 channels       MCS59 / MCS60
a ``.mat`` with 64 channels (11–88)    see below
=====================================  ==========================

A 64-channel ``.mat`` is either an Axion 8×8 well or an MCS 60-electrode
recording padded to the full grid. An MCS array has no corner electrodes
(11, 18, 81, 88), so the two are told apart by whether those channels carry
signal. That takes a few seconds of data, which a v7.3 (HDF5) ``.mat`` gives
cheaply; a v7 ``.mat`` would have to be read whole, so there the sampling rate
breaks the tie (Axion records at 12.5 kHz) and the guess is flagged as one.

MCS60 and MCS60old put every electrode in the same place, so which of the two
an MCS recording is never changes a figure; MCS60 is the one suggested.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = [
    "CORNER_CHANNELS", "LayoutGuess", "RecordingProbe", "detect_layout",
    "probe_folder", "probe_recording",
]

CORNER_CHANNELS = (11, 18, 81, 88)
#: How much of a recording the corner check reads.
_CORNER_SECONDS = 2.0
#: A corner is "live" when its spread is at least this fraction of the typical
#: electrode's; a padded channel is all zeros or a constant.
_LIVE_FRACTION = 0.1
#: Axion Maestro's sampling rate: the tie-breaker when the corners can't be read.
AXION_FS = 12500.0
#: At most this many recordings are opened; enough to see a batch's layout
#: and rates without stalling on a folder of hundreds.
MAX_PROBED = 24


@dataclass(frozen=True)
class RecordingProbe:
    name: str
    #: ``"mat"``, ``"mcs"`` or ``"axion"``.
    format: str
    fs: float
    n_channels: int
    #: Whether channels 11, 18, 81 and 88 carry signal, for a 64-channel
    #: ``.mat``; ``None`` where that wasn't checked or doesn't apply.
    corners_live: bool | None = None


@dataclass(frozen=True)
class LayoutGuess:
    #: A name from :data:`meanap.pipeline.channel_layout` layouts, or None.
    layout: str | None
    #: False when the evidence was indirect or the recordings disagree.
    sure: bool
    #: One sentence for the person, saying what it was read from.
    reason: str
    #: Each probed recording's sampling rate, in Hz.
    rates: tuple[float, ...] = ()


def _corners_live(dat, channels: np.ndarray, fs: float) -> bool | None:
    """Whether the corner channels of an (n_channels, n_samples) dataset carry signal."""
    n = int(min(dat.shape[1], max(1, fs * _CORNER_SECONDS)))
    sample = np.asarray(dat[:, :n], dtype=np.float64)
    spread = sample.std(axis=1)
    corner = np.isin(channels, CORNER_CHANNELS)
    if not corner.any() or corner.all():
        return None
    typical = float(np.median(spread[~corner]))
    if typical <= 0:
        return None
    return bool(np.all(spread[corner] >= _LIVE_FRACTION * typical))


def probe_recording(path: str | Path) -> RecordingProbe:
    """Sampling rate and channel count of one raw file, from its header."""
    import h5py
    import scipy.io as sio

    from meanap.pipeline.axion_raw import is_axion_raw, read_axion_metadata
    from meanap.pipeline.io import (
        _find_mcs_stream_name, _mcs_label_to_channel, _mcs_sampling_rate,
    )

    path = Path(path)
    if is_axion_raw(path):
        meta = read_axion_metadata(path)
        first = meta.wells()[0]
        per_well = sum(1 for ch in meta.channels if ch.well == first)
        return RecordingProbe(path.stem, "axion", float(meta.sampling_frequency), per_well)

    if not h5py.is_hdf5(path):  # v7 .mat
        mat = sio.loadmat(path, variable_names=("fs", "channels"))
        return RecordingProbe(path.stem, "mat", float(np.asarray(mat["fs"]).ravel()[0]),
                              int(np.asarray(mat["channels"]).size))

    with h5py.File(path, "r") as f:
        stream = _find_mcs_stream_name(f)
        if stream is not None:
            info = f[stream]["InfoChannel"][()]
            return RecordingProbe(path.stem, "mcs", _mcs_sampling_rate(info),
                                  len({_mcs_label_to_channel(x) for x in info["Label"]}))
        channels = f["channels"][()].ravel().astype(int)
        fs = float(f["fs"][()].ravel()[0])
        live = _corners_live(f["dat"], channels, fs) if len(channels) == 64 else None
        return RecordingProbe(path.stem, "mat", fs, len(channels), live)


def probe_folder(folder: str | Path, limit: int = MAX_PROBED) -> list[RecordingProbe]:
    """Probe the raw recordings in *folder* (up to *limit*), skipping unreadable ones.

    Only the first 64-channel v7.3 ``.mat`` has its corners read: one is enough
    to tell the hardware, and each read is a few seconds of data.
    """
    from meanap.pipeline.io import RAW_EXTENSIONS

    folder = Path(folder)
    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS)
    probes: list[RecordingProbe] = []
    corners_read = False
    for path in files:
        if len(probes) >= limit:
            break
        try:
            probe = probe_recording(path)
        except Exception:  # not a recording after all, or unreadable: skip it
            continue
        if probe.corners_live is not None:
            if corners_read:
                probe = RecordingProbe(probe.name, probe.format, probe.fs,
                                       probe.n_channels, None)
            corners_read = True
        probes.append(probe)
    return probes


def _layout_of(probe: RecordingProbe, corners: bool | None) -> tuple[str | None, bool, str]:
    """``(layout, sure, reason)`` for one kind of recording."""
    n = probe.n_channels
    if probe.format == "mcs":
        layout = "MCS59" if n == 59 else "MCS60"
        return layout, True, f"Multi Channel Systems files with {n} channels"
    if probe.format == "axion":
        if n in (16, 64):
            return f"Axion{n}", True, f"Axion files with {n} electrodes per well"
        return None, False, f"Axion files with {n} electrodes per well, which no layout has"
    if n == 16:
        return "Axion16", True, "16 channels, a 4×4 Axion well"
    if n == 59:
        return "MCS59", True, "59 channels, an MCS 59-electrode array"
    if n == 60:
        return "MCS60", True, "60 channels, an MCS 60-electrode array"
    if n == 64:
        if corners is True:
            return "Axion64", True, ("64 channels with signal on the corner electrodes, "
                                     "which only an Axion 8×8 well has")
        if corners is False:
            return "MCS60", True, ("64 channels with empty corners, an MCS "
                                   "60-electrode array padded to the full grid")
        if probe.fs == AXION_FS:
            return "Axion64", False, ("64 channels recorded at 12.5 kHz, most likely an "
                                      "Axion 8×8 well (the corner electrodes couldn't "
                                      "be checked in this file format)")
        return "MCS60", False, ("64 channels, most likely an MCS 60-electrode array "
                                "padded to the full grid (the corner electrodes "
                                "couldn't be checked in this file format)")
    return None, False, f"{n} channels, which no built-in layout has"


def detect_layout(probes: list[RecordingProbe]) -> LayoutGuess:
    """The layout the probed recordings were made on, and how sure that is."""
    if not probes:
        return LayoutGuess(None, False, "No recordings could be read.")
    rates = tuple(p.fs for p in probes)
    corners = next((p.corners_live for p in probes if p.corners_live is not None), None)
    verdicts = [_layout_of(p, corners) for p in probes]
    counts = Counter(v[0] for v in verdicts)
    layout, _ = counts.most_common(1)[0]
    layout_sure, reason = next((s, r) for lay, s, r in verdicts if lay == layout)
    if len(counts) > 1:
        others = ", ".join(f"{k or 'unknown'} ({v})" for k, v in counts.items() if k != layout)
        return LayoutGuess(layout, False,
                           f"The recordings don't agree: most look like {layout}, "
                           f"others like {others}.", rates)
    return LayoutGuess(layout, layout_sure, f"Read from the files: {reason}.", rates)
