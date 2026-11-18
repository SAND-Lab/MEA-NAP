"""MaxWell Biosystems ``.raw.h5`` recordings: metadata, TTL events and voltage.

A spike-sorted import (:mod:`meanap.pipeline.sorted_import`) needs four things
from the raw recording and none of its voltage: the sampling rate, the exact
duration, where each recorded electrode sits, and the TTL events a stimulus
left. On a MaxOne the voltage is ``(n_routed, n_frames)`` uint16 — 4.7 GB for
two minutes on 941 electrodes — so :func:`read_maxwell_meta` and
:func:`read_maxwell_ttl` read small datasets only.

Step 1's own spike detection does need the voltage, and
:func:`load_maxwell_traces` reads it. Two things make that different from
every other format:

* The voltage is compressed with MaxWell's own HDF5 filter (ID 401), which
  h5py cannot decode without MaxWell's plugin library.
  :func:`ensure_maxwell_plugin` finds it (``HDF5_PLUGIN_PATH``, then
  ``~/hdf5_plugin_path_maxwell``) and says how to install it when it cannot;
  nothing here downloads anything.
* It is big: 1012 channels at 20 kHz are 4.9 GB a minute as float32, and the
  file on disk is ~4x smaller than that, so the size of the file says little.
  :class:`MaxwellTraces` keeps the file's uint16 counts (half the float32
  size) and scales each channel to µV as it is read out.

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

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: The TTL word a MaxWell legacy file records in ``bits``, one row per change.
TTL_DATASET = "bits/0000"

#: The HDF5 filter MaxWell compresses ``groups/routed/raw`` with.
MAXWELL_FILTER_ID = 401

#: Where neo's ``auto_install_maxwell_hdf5_compression_plugin`` puts the
#: plugin when ``HDF5_PLUGIN_PATH`` is unset — searched after that variable.
DEFAULT_PLUGIN_DIR = Path.home() / "hdf5_plugin_path_maxwell"

#: Volts per bit when a file has no ``settings/lsb``: MaxWell's 10-bit ADC
#: over 3.3 V at the recorded gain (512 if that is missing too) — what neo and
#: SpikeInterface assume.
_DEFAULT_GAIN = 512.0


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
            return is_maxwell_open(f)
    except (OSError, ValueError):
        return False


def is_maxwell_open(f) -> bool:
    """Whether the open ``h5py.File`` *f* is a MaxWell recording."""
    return "mxw_version" in f or "data_store" in f or "wells" in f \
        or ("recordings" in f and "wellplate" in f)


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


# ── Voltage ───────────────────────────────────────────────────────────────────

class MaxwellPluginMissing(OSError):
    """The voltage is compressed with MaxWell's filter and no plugin decodes it."""


def _plugin_dirs() -> list[Path]:
    """Folders that may hold MaxWell's plugin, in the order they are tried."""
    dirs = [Path(p) for p in os.environ.get("HDF5_PLUGIN_PATH", "").split(os.pathsep) if p]
    if DEFAULT_PLUGIN_DIR not in dirs:
        dirs.append(DEFAULT_PLUGIN_DIR)
    return dirs


def ensure_maxwell_plugin() -> None:
    """Make MaxWell's compression filter available to h5py, or say how to.

    HDF5 reads ``HDF5_PLUGIN_PATH`` once, when the library starts — usually
    before anything here runs — so setting the variable later changes nothing.
    Each candidate folder is therefore prepended to the running library's
    search path instead, which takes effect at once.
    """
    import h5py

    if h5py.h5z.filter_avail(MAXWELL_FILTER_ID):
        return
    tried = _plugin_dirs()
    for folder in tried:
        if folder.is_dir():
            h5py.h5pl.prepend(str(folder).encode())
            if h5py.h5z.filter_avail(MAXWELL_FILTER_ID):
                return
    lib = {"win32": "compression.dll", "darwin": "libcompression.dylib"}.get(
        sys.platform, "libcompression.so")
    raise MaxwellPluginMissing(
        "This MaxWell recording's voltage is compressed with MaxWell's own HDF5 "
        f"filter ({MAXWELL_FILTER_ID}), and its decoder was not found (looked in "
        f"{', '.join(str(d) for d in tried)}). To read the voltage:\n"
        f"  1. Get MaxWell's plugin, {lib}. It ships with MaxLab Live, and "
        "MaxWell Biosystems provide it for download; the Python package neo "
        "can fetch it for you with\n"
        "       python -c \"from neo.rawio.maxwellrawio import "
        "auto_install_maxwell_hdf5_compression_plugin as f; f()\"\n"
        f"  2. Put it in {DEFAULT_PLUGIN_DIR} (where that command puts it), or in "
        "a folder named by the HDF5_PLUGIN_PATH environment variable.\n"
        "Spike-sorted imports do not need it: they read no voltage.")


def _uses_filter(dset, filter_id: int) -> bool:
    plist = dset.id.get_create_plist()
    return any(plist.get_filter(i)[0] == filter_id for i in range(plist.get_nfilters()))


def uv_per_bit(meta: MaxwellMeta) -> float:
    """Microvolts per ADC count: ``settings/lsb``, or 3.3 V / (1024 × gain)."""
    if meta.lsb_v is not None:
        return float(meta.lsb_v) * 1e6
    gain = meta.gain or _DEFAULT_GAIN
    return 3.3 / (1024 * gain) * 1e6


def node_ids(meta: MaxwellMeta) -> np.ndarray:
    """The ID each routed row goes by in the pipeline: its electrode number.

    Electrode numbers (0–26399 on a MaxOne) name a place on the array, so
    they mean the same thing in every recording and in a spike-sorted import
    of the same file (:func:`meanap.pipeline.sorted_import.to_spike_file` uses
    them too); a routed channel number does not — the same amplifier channel
    serves different electrodes in different routings. Falls back to the
    channel numbers in the (never seen) case that two rows share an electrode.
    """
    electrodes = np.asarray(meta.electrodes, dtype=np.int64)
    if len(np.unique(electrodes)) == len(electrodes):
        return electrodes
    return np.asarray(meta.channels, dtype=np.int64)


def electrode_table(meta: MaxwellMeta) -> dict[str, np.ndarray]:
    """The ``electrodes`` argument of :func:`~meanap.pipeline.io.save_spike_times_npz`.

    The same table a spike-sorted import writes, so ``channel_layout =
    "FromFile"`` places detected MaxWell channels exactly as it places imported
    units' electrodes.
    """
    from meanap.pipeline.sorted_import import layout_coords_from_um

    coords, _ = layout_coords_from_um(meta.xy_um)
    return {"ids": node_ids(meta), "coords": coords,
            "coords_um": np.asarray(meta.xy_um, dtype=float)}


class MaxwellTraces:
    """A MaxWell recording's voltage in µV, kept in memory as the file's counts.

    Behaves like the ``(n_samples, n_channels)`` float32 array the other
    loaders return as far as step 1 uses one — ``shape``, ``dat[:, ch]``,
    ``dat[:, [ch, ...]]``, ``np.asarray(dat)`` — but stores the uint16 ADC
    counts, half the memory, and scales only what is read out. Step 1 reads one
    channel at a time, so that costs one channel's copy per thread rather than
    a second copy of the recording.

    Counts are held ``(n_channels, n_samples)``, as the file stores them, so a
    channel is one contiguous row.

    µV = counts × lsb × 1e6, with no offset subtracted: exactly what neo and
    SpikeInterface return (their ``offset_uV`` is 0). The ~3.2 mV of DC that
    leaves (counts sit near 512) is removed by step 1's band-pass before any
    threshold sees it.
    """

    ndim = 2
    dtype = np.dtype(np.float32)

    def __init__(self, counts: np.ndarray, uv_per_bit: float):
        if counts.ndim != 2:
            raise ValueError(f"counts must be (n_channels, n_samples), got {counts.shape}")
        self.counts = counts
        #: float32, as SpikeInterface scales (``float32(counts) * float32(gain)``),
        #: so the two give bit-identical µV.
        self.uv_per_bit = np.float32(uv_per_bit)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.counts.shape[1], self.counts.shape[0])

    @property
    def size(self) -> int:
        return int(self.counts.size)

    @property
    def nbytes(self) -> int:
        """Bytes actually held — the counts, not their float32 equivalent."""
        return int(self.counts.nbytes)

    def __len__(self) -> int:
        return self.shape[0]

    def __getitem__(self, key) -> np.ndarray:
        out = np.asarray(self.counts.T[key]).astype(np.float32)
        out *= self.uv_per_bit
        return out

    def __array__(self, dtype=None, copy=None) -> np.ndarray:
        """The whole recording as a float32 array — twice the memory held."""
        out = np.empty(self.counts.shape, dtype=dtype or np.float32)
        for i in range(0, self.counts.shape[0], 64):
            out[i:i + 64] = self.counts[i:i + 64]
            out[i:i + 64] *= self.uv_per_bit
        return out.T


def _require_memory(n_bytes: int, path: Path) -> None:
    """Refuse, with numbers, to load what will not fit in free RAM.

    Without this a long recording runs the machine into swap — or the kernel
    kills the run with no message at all — minutes after it started. Free
    memory can only be measured with psutil; without it the load goes ahead.
    The 1 GB margin is roughly what one detection thread then needs on a
    five-minute recording (step 1 sizes its thread pool to what is left).
    """
    from meanap.pipeline import parallel

    if not parallel._HAVE_PSUTIL:
        return
    free = parallel.available_ram_gb() * 1e9
    if n_bytes + 1e9 > free:
        raise MemoryError(
            f"{path.name}: its voltage needs {n_bytes / 1e9:.1f} GB of memory, "
            f"plus about 1 GB to analyse, and only {free / 1e9:.1f} GB is free. "
            "Close other applications, run it on a computer with more memory, "
            "or record (or export) a shorter stretch.")


def load_maxwell_traces(path: str | Path, well: int = 0, rec: int = 0, *,
                        meta: MaxwellMeta | None = None, compact: bool = True,
                        max_frames: int | None = None,
                        block_frames: int = 100_000):
    """Read a MaxWell recording's voltage: ``(traces, meta)``.

    ``traces`` is a :class:`MaxwellTraces` (``compact=True``, half the memory)
    or a plain ``(n_samples, n_channels)`` float32 array in µV. Either way its
    columns are in routed-row order, the order of ``meta.channels``.
    ``max_frames`` reads only the start of the recording (``meta`` still
    describes all of it).

    The file chunks the voltage across every channel at once (``(n_routed,
    200)`` frames on the MaxOne files seen so far), so it is read in blocks of
    whole chunks spanning all channels: reading one channel would decompress
    every channel to get it.
    """
    import h5py

    path = Path(path)
    meta = meta or read_maxwell_meta(path, well, rec)
    with h5py.File(path, "r") as f:
        g, _ = _recording_group(f, well, rec)
        if "raw" not in g["groups/routed"]:
            raise ValueError(
                f"{path.name}: this MaxWell file holds no voltage "
                "(groups/routed/raw), only metadata — it can be used for a "
                "spike-sorted import, not for spike detection.")
        dset = g["groups/routed/raw"]
        if dset.shape != (len(meta.channels), meta.n_frames):
            raise ValueError(
                f"{path.name}: voltage is {dset.shape} but the file lists "
                f"{len(meta.channels)} channels × {meta.n_frames} frames")
        if _uses_filter(dset, MAXWELL_FILTER_ID):
            ensure_maxwell_plugin()
        n = meta.n_frames if max_frames is None else min(meta.n_frames, int(max_frames))
        bytes_per = 2 if compact else 4
        _require_memory(len(meta.channels) * n * bytes_per, path)

        chunk = dset.chunks[1] if dset.chunks else 1
        block = max(chunk, (block_frames // chunk) * chunk)
        scale = np.float32(uv_per_bit(meta))
        if compact:
            counts = np.empty((dset.shape[0], n), dtype=dset.dtype)
            for a in range(0, n, block):
                sel = np.s_[:, a:min(n, a + block)]
                dset.read_direct(counts, source_sel=sel, dest_sel=sel)
            return MaxwellTraces(counts, scale), meta

        out = np.empty((dset.shape[0], n), dtype=np.float32)
        for a in range(0, n, block):
            b = min(n, a + block)
            out[:, a:b] = dset[:, a:b]
            out[:, a:b] *= scale
        return out.T, meta
