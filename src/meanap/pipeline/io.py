"""I/O helpers for MEA-NAP pipeline files.

Handles HDF5/v7.3 .mat files produced by the Axion MEA system and by
the MATLAB MEA-NAP pipeline.  ``scipy.io.loadmat`` cannot read v7.3 files,
so we use ``h5py`` throughout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np


# ── Raw recording files ───────────────────────────────────────────────────────

def load_raw_recording(path: str | Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Load a raw MEA recording .mat file (HDF5/v7.3 format).

    Returns
    -------
    dat : (n_samples, n_channels) float32 array — raw voltage traces
    channels : (n_channels,) int array — channel IDs
    fs : float — sampling frequency in Hz
    """
    with h5py.File(path, "r") as f:
        dat = f["dat"][()].T.astype(np.float32)   # (n_channels, n_samples) → (n_samples, n_channels)
        channels = f["channels"][()].flatten().astype(int)
        fs = float(f["fs"][()].flatten()[0])
    return dat, channels, fs


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
                    k: group[k][()].flatten()
                    for k in group.keys()
                }
            else:
                result[ch_idx] = {"default": group[()].flatten()}
    return result


def save_spike_times_npz(
    path: str | Path,
    spike_times: dict[int, dict[str, np.ndarray]],
    channels: np.ndarray,
    fs: float,
    params: dict[str, Any] | None = None,
) -> None:
    """Save spike detection results to a ``.npz`` file.

    Saved arrays
    ------------
    ``channels`` — channel IDs
    ``fs`` — sampling frequency
    ``spike_times_{ch}_{method}`` — spike times in seconds for each channel/method

    Also saves a text file ``{stem}_params.txt`` alongside if ``params`` given.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    arrays: dict[str, Any] = {
        "channels": channels,
        "fs": np.array([fs]),
    }
    for ch_idx, methods in spike_times.items():
        for method, times in methods.items():
            arrays[f"spike_times_{ch_idx}_{method}"] = times

    np.savez(path, **arrays)

    if params is not None:
        params_path = path.with_name(path.stem + "_params.txt")
        with open(params_path, "w") as fh:
            for k, v in params.items():
                fh.write(f"{k}: {v}\n")


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
