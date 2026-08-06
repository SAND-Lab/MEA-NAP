"""I/O helpers for MEA-NAP pipeline files.

Reads raw recordings in three layouts, so users don't have to pre-convert
anything to MATLAB before running the pipeline:

* ``.mat`` v7.3 (HDF5) holding ``dat``/``channels``/``fs`` — what
  ``convertMCSh5toMat.m`` and the Axion converter write for large recordings
* ``.mat`` v7 (the older non-HDF5 format) with the same variables — what those
  converters write for recordings under 2 GB; ``h5py`` cannot read these
* ``.h5`` straight off a Multi Channel Systems recorder — converted on read by
  :func:`load_mcs_h5`, reproducing ``convertMCSh5toMat.m`` exactly
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import scipy.io as sio

from meanap.pipeline.axion_raw import (
    is_axion_raw,
    load_axion_well,
    read_axion_metadata,
    split_well_suffix,
)


# ── Raw recording files ───────────────────────────────────────────────────────

#: Raw recording extensions the pipeline understands, in preference order.
#: ``.mat`` comes first so a folder holding both a recording and its conversion
#: keeps using the conversion — same data, cheaper to read.
RAW_EXTENSIONS = (".mat", ".h5", ".raw")


@dataclass(frozen=True)
class RawSource:
    """A recording's location: a file, plus which well of it, if it holds many.

    Most formats store one recording per file, so ``well`` is ``None``. An Axion
    ``.raw`` holds a whole plate, and MEA-NAP treats each well as its own
    recording — there ``well`` says which one.
    """

    path: Path
    well: str | None = None

    @property
    def name(self) -> str:
        return self.path.name if self.well is None else f"{self.path.name} [{self.well}]"

    def __fspath__(self) -> str:
        return str(self.path)


def find_raw_file(raw_dir: str | Path, filename: str) -> RawSource | None:
    """Locate the raw recording for ``filename``, whatever format it's in.

    Spreadsheets name recordings without an extension, so every step has to
    guess. A name ending in a well (``…_A1``) also matches an Axion ``.raw``
    holding that well — which is exactly how ``rawConvertFunc.m`` names the
    per-well ``.mat`` files it writes, so spreadsheets built for the converted
    workflow keep working against the unconverted plate.

    Returns ``None`` when no supported file exists, letting callers report a
    skip rather than raising.
    """
    if not raw_dir:
        return None
    raw_dir = Path(raw_dir)

    for ext in RAW_EXTENSIONS:
        candidate = raw_dir / f"{filename}{ext}"
        if candidate.exists():
            return RawSource(candidate)

    split = split_well_suffix(filename)
    if split is not None:
        stem, well = split
        candidate = raw_dir / f"{stem}.raw"
        if candidate.exists():
            return RawSource(candidate, well)
    return None


def is_mcs_h5(path: str | Path) -> bool:
    """True if ``path`` is a Multi Channel Systems HDF5 recording."""
    try:
        with h5py.File(path, "r") as f:
            return _find_mcs_stream_name(f) is not None
    except OSError:
        return False


def load_raw_recording(path: str | Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Load a raw MEA recording, dispatching on its actual format.

    Accepts a ``.mat`` (v7 or v7.3) holding ``dat``/``channels``/``fs``, a Multi
    Channel Systems ``.h5``, or an Axion ``.raw`` — dispatch is by file content,
    not extension, since recordings are sometimes renamed.

    Pass a :class:`RawSource` (what :func:`find_raw_file` returns) for an Axion
    plate, so the well is known; a bare path works for single-recording formats.

    Returns
    -------
    dat : (n_samples, n_channels) float32 array — raw voltage traces. Units
        follow the source: µV for MCS, volts for Axion, matching what each
        format's converter wrote (set "Potential difference unit" to suit).
    channels : (n_channels,) int array — channel IDs
    fs : float — sampling frequency in Hz
    """
    well = path.well if isinstance(path, RawSource) else None
    path = Path(path)

    if is_axion_raw(path):
        meta = read_axion_metadata(path)
        if well is None:
            raise ValueError(
                f"{path.name} is an Axion plate holding {len(meta.wells())} wells; "
                f"name the recording '<file>_<well>' in your spreadsheet to pick one "
                f"(available: {', '.join(meta.wells())})."
            )
        return load_axion_well(path, well, metadata=meta)

    try:
        f = h5py.File(path, "r")
    except OSError:
        # Not HDF5 at all — a v7 .mat, which scipy handles.
        return _load_raw_mat_v7(path)

    with f:
        stream_name = _find_mcs_stream_name(f)
        if stream_name is not None:
            return _load_mcs_h5_open(f, stream_name)
        if "dat" not in f:
            raise ValueError(
                f"{path.name}: HDF5 file is neither a MEA-NAP .mat (no 'dat' variable) "
                f"nor a Multi Channel Systems recording (no AnalogStream)."
            )
        dat = f["dat"][()].T.astype(np.float32)   # (n_channels, n_samples) → (n_samples, n_channels)
        channels = f["channels"][()].flatten().astype(int)
        fs = float(f["fs"][()].flatten()[0])
    return dat, channels, fs


def _load_raw_mat_v7(path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Load a pre-v7.3 ``.mat`` recording via scipy.

    Unlike the v7.3 branch, scipy already returns ``dat`` as
    (n_samples, n_channels) — MATLAB's own orientation — so no transpose.
    """
    try:
        mat = sio.loadmat(path, variable_names=("dat", "channels", "fs"))
    except Exception as exc:  # scipy raises bare ValueError/NotImplementedError
        raise ValueError(f"{path.name}: could not be read as a raw recording ({exc})") from exc
    missing = [k for k in ("dat", "channels", "fs") if k not in mat]
    if missing:
        raise ValueError(f"{path.name}: .mat is missing variable(s) {', '.join(missing)}")
    dat = np.asarray(mat["dat"], dtype=np.float32)
    channels = np.asarray(mat["channels"]).flatten().astype(int)
    fs = float(np.asarray(mat["fs"]).flatten()[0])
    return dat, channels, fs


# ── Multi Channel Systems HDF5 ────────────────────────────────────────────────

def _find_mcs_stream_name(f: "h5py.File") -> str | None:
    """Path to the analog stream holding the electrode data, or None.

    MCS files nest one or more recordings, each with one or more analog
    streams (raw, filtered, auxiliary). We take the first stream that carries
    both ``ChannelData`` and ``InfoChannel``, matching what
    ``convertMCSh5toMat.m`` does when it indexes ``AnalogStream{1}``.
    """
    data = f.get("Data")
    if not isinstance(data, h5py.Group):
        return None
    for rec_name in _in_index_order(data.keys()):
        streams = data.get(f"{rec_name}/AnalogStream")
        if not isinstance(streams, h5py.Group):
            continue
        for stream_name in _in_index_order(streams.keys()):
            stream = streams[stream_name]
            if isinstance(stream, h5py.Group) and "ChannelData" in stream and "InfoChannel" in stream:
                return f"Data/{rec_name}/AnalogStream/{stream_name}"
    return None


def _in_index_order(names: Any) -> list[str]:
    """Sort ``Recording_N``/``Stream_N`` names by N, not lexicographically.

    Plain sorting would put ``Stream_10`` ahead of ``Stream_2`` and pick the
    wrong stream in a file with ten or more of them.
    """
    def key(name: str) -> tuple[int, int | str]:
        _, _, suffix = name.rpartition("_")
        return (0, int(suffix)) if suffix.isdigit() else (1, name)
    return sorted(names, key=key)


def load_mcs_h5(path: str | Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Load a Multi Channel Systems ``.h5`` recording directly.

    Reproduces ``Functions/convertMCSh5toMat.m`` without going through the
    McsHDF5 MATLAB toolbox: ADC counts become µV via the per-channel
    ``ConversionFactor``/``ADZero``/``Exponent`` stored in ``InfoChannel``, and
    the electrode number is the last token of each channel's label.
    """
    with h5py.File(path, "r") as f:
        stream_name = _find_mcs_stream_name(f)
        if stream_name is None:
            raise ValueError(f"{Path(path).name}: no Multi Channel Systems analog stream found")
        return _load_mcs_h5_open(f, stream_name)


def _load_mcs_h5_open(f: "h5py.File", stream_name: str) -> tuple[np.ndarray, np.ndarray, float]:
    stream = f[stream_name]
    info = stream["InfoChannel"][()]
    channel_data = stream["ChannelData"]          # (n_channels, n_samples) ADC counts

    channels = np.array([_mcs_label_to_channel(lbl) for lbl in info["Label"]], dtype=int)
    fs = _mcs_sampling_rate(info)

    conv = info["ConversionFactor"].astype(np.float64)
    adzero = info["ADZero"].astype(np.float64)
    # MEA-NAP works in µV; MCS stores units of 10^Exponent V, so scaling by
    # 10^(exponent - (exponent + 6)) == 1e-6 lands on µV whatever the exponent.
    exponent = info["Exponent"].astype(np.float64)
    scale = conv * 10.0 ** (exponent - (exponent + 6))

    n_channels, n_samples = channel_data.shape
    dat = np.empty((n_samples, n_channels), dtype=np.float32)
    # Convert in blocks of samples rather than in one shot: the float64
    # intermediate for a 25 kHz hour-long 60-electrode recording is ~4 GB, twice
    # the size of the result. Blocks span *all* channels because MCS chunks do
    # (60 x ~2000 samples, gzipped) — reading channel by channel would
    # decompress the whole file once per channel.
    block = _mcs_block_size(channel_data)
    for start in range(0, n_samples, block):
        stop = min(start + block, n_samples)
        raw = channel_data[:, start:stop].astype(np.float64)   # (n_channels, block)
        dat[start:stop, :] = ((raw - adzero[:, None]) * scale[:, None]).T

    return dat, channels, fs


def _mcs_block_size(channel_data: "h5py.Dataset", target_bytes: int = 256 << 20) -> int:
    """Samples per conversion block: ~256 MB of float64, snapped to chunk edges."""
    n_channels = channel_data.shape[0]
    block = max(1, target_bytes // (n_channels * 8))
    chunk = channel_data.chunks
    if chunk is not None and chunk[1] > 0:
        block = max(chunk[1], (block // chunk[1]) * chunk[1])
    return block


def _mcs_label_to_channel(label: Any) -> int:
    """Electrode number from an MCS channel label, e.g. ``b'E-00223 47'`` → 47.

    The reference electrode is labelled ``Ref`` instead of a number; MEA-NAP
    assigns it 15, matching ``convertMCSh5toMat.m``.
    """
    if isinstance(label, bytes):
        label = label.decode("utf-8", "replace")
    token = str(label).split(" ")[-1].strip()
    if token == "Ref":
        return 15
    try:
        return int(token)
    except ValueError as exc:
        raise ValueError(f"could not read an electrode number from MCS label {label!r}") from exc


def _mcs_sampling_rate(info: np.ndarray) -> float:
    """Sampling rate in Hz from the per-channel sample interval (``Tick``, µs)."""
    ticks = np.unique(info["Tick"].astype(np.int64))
    if len(ticks) != 1:
        raise ValueError(f"MCS channels disagree on sampling interval: ticks {ticks.tolist()}")
    if ticks[0] <= 0:
        raise ValueError(f"MCS sampling interval is not positive: {ticks[0]}")
    return 1e6 / float(ticks[0])


# ── Spike detection output files ──────────────────────────────────────────────

def load_spike_times_mat(path: str | Path) -> dict[int, dict[str, np.ndarray]]:
    """Read spike times from a MEA-NAP ``_spikes.mat`` (HDF5/v7.3) file.

    Returns
    -------
    spike_times : dict[channel_index, dict[method, times_in_seconds]]
        ``channel_index`` is 0-based.  ``method`` is e.g. ``'bior1p5'``,
        ``'thr4'``, ``'thr5'``.
    """
    result: dict[int, dict[str, np.ndarray]] = {}
    with h5py.File(path, "r") as f:
        st = f["spikeTimes"]
        n_channels = st.shape[0]
        for ch_idx in range(n_channels):
            ref = st[ch_idx, 0]
            group = f[ref]
            if isinstance(group, h5py.Group):
                result[ch_idx] = {
                    k: _read_maybe_empty(group[k])
                    for k in group.keys()
                }
            else:
                result[ch_idx] = {"default": _read_maybe_empty(group)}
    return result


def _read_maybe_empty(dset: "h5py.Dataset") -> np.ndarray:
    """Read a v7.3 dataset, honoring MATLAB's empty-array marker.

    MATLAB stores an empty array ``[]`` as a small dataset holding the *shape*
    (e.g. ``[0 0]``) plus a ``MATLAB_empty`` attribute — reading it naively
    yields spurious ``[0, 0]``/``[0, 1]`` "values". Return an empty array in
    that case.
    """
    if int(dset.attrs.get("MATLAB_empty", 0)):
        return np.array([])
    return dset[()].flatten()


def save_spike_times_npz(
    path: str | Path,
    spike_times: dict[int, dict[str, np.ndarray]],
    channels: np.ndarray,
    fs: float,
    params: dict[str, Any] | None = None,
    duration_s: float | None = None,
) -> None:
    """Save spike detection results to a ``.npz`` file.

    Saved arrays
    ------------
    ``channels`` — channel IDs
    ``fs`` — sampling frequency
    ``duration_s`` — recording duration in seconds (omitted if not supplied)
    ``spike_times_{ch}_{method}`` — spike times in seconds for each channel/method

    Also saves a text file ``{stem}_params.txt`` alongside if ``params`` given.

    ``duration_s`` is stored so Steps 2-4 don't have to re-open the raw
    recording just to recover it — which is what makes resuming from a previous
    run work when the raw data isn't mounted (see ``read_duration_npz``).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    arrays: dict[str, Any] = {
        "channels": channels,
        "fs": np.array([fs]),
    }
    if duration_s is not None:
        arrays["duration_s"] = np.array([float(duration_s)])
    for ch_idx, methods in spike_times.items():
        for method, times in methods.items():
            arrays[f"spike_times_{ch_idx}_{method}"] = times

    np.savez(path, **arrays)

    if params is not None:
        params_path = path.with_name(path.stem + "_params.txt")
        with open(params_path, "w") as fh:
            for k, v in params.items():
                fh.write(f"{k}: {v}\n")


def count_raw_samples(path: str | Path, n_channels: int) -> int:
    """Number of samples in a raw recording, without reading the traces.

    ``n_channels`` disambiguates the axis order: raw files are usually
    (n_samples, n_channels), but v7.3 ``.mat`` stores them transposed and MCS
    always writes (n_channels, n_samples).
    """
    path = Path(path)

    if is_axion_raw(path):
        return read_axion_metadata(path).n_samples

    try:
        f = h5py.File(path, "r")
    except OSError:
        # v7 .mat — scipy has no lazy shape read, so load just this variable.
        return int(np.asarray(sio.loadmat(path, variable_names=("dat",))["dat"]).shape[0])

    with f:
        stream_name = _find_mcs_stream_name(f)
        if stream_name is not None:
            return int(f[f"{stream_name}/ChannelData"].shape[1])
        shape = f["dat"].shape

    n_samples = shape[0]
    if len(shape) > 1 and n_samples == n_channels:
        n_samples = shape[1]
    return int(n_samples)


def resolve_duration_s(
    spike_data: "np.lib.npyio.NpzFile",
    raw_path: str | Path | None,
    fs: float,
    n_channels: int,
) -> tuple[float | None, str]:
    """Recording duration in seconds, with the source it came from.

    Prefers the value Step 1 stored in the spike ``.npz``; falls back to the
    sample count in the raw recording for files written before that field
    existed (or by an external spike detector). Returns ``(None, "unavailable")``
    when neither is readable, so callers can decide whether to skip or warn
    rather than silently inventing a duration — every firing rate in Step 2 and
    every surrogate in Step 3 scales with this number.
    """
    if "duration_s" in spike_data.files:
        value = float(np.asarray(spike_data["duration_s"]).flatten()[0])
        if value > 0:
            return value, "spike file"

    if raw_path is None:
        return None, "unavailable"
    try:
        return count_raw_samples(raw_path, n_channels) / fs, "raw file"
    except Exception:
        return None, "unavailable"


def load_spike_times_npz(path: str | Path) -> dict[int, dict[str, np.ndarray]]:
    """Load spike times saved by ``save_spike_times_npz``."""
    data = np.load(path)
    result: dict[int, dict[str, np.ndarray]] = {}
    prefix = "spike_times_"
    for key in data.files:
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        parts = rest.split("_", 1)
        if len(parts) != 2:
            continue
        ch_idx = int(parts[0])
        method = parts[1]
        if ch_idx not in result:
            result[ch_idx] = {}
        result[ch_idx][method] = data[key]
    return result
