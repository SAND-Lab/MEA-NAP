"""Synthetic spike-sorted recording with light stimulation, for the import tests.

Writes, for one recording, everything a real MaxWell + SpyKING CIRCUS/phy
dataset has that the import reads — and nothing it does not (no voltage):

* ``<name>.raw.h5`` — MaxWell legacy layout: routed channels, frame numbers,
  electrode mapping, sampling rate, and a TTL ``bits`` log with a 60 Hz frame
  sync on bit 5 and a flash marker on bit 7 (word drops to 0 for one frame),
  like the retinal-organoid recording.
* ``<name>.raw.result-merged.hdf5`` / ``.templates-merged.hdf5`` — SpyKING
  CIRCUS output for the units below.
* ``<name>_phy/`` — the same units as a phy folder, one of them labelled noise.

Units fire Poisson at a base rate; :data:`ON_RESPONDERS` add a burst 20–120 ms
after every ON event and :data:`OFF_RESPONDERS` after every OFF event, so a
correct stim analysis finds exactly those and nothing else. Everything is
seeded, and kept small (12 electrodes, 15 units, 40 s) so a test runs in
seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

NAME = "SynthMxw_DIV10_A"
FS = 10000.0
DURATION_S = 40.0
FIRST_FRAME = 5_000_000
#: Electrode IDs and positions (µm, MaxWell's y-down): a 4×3 patch of a
#: 17.5 µm grid, with the routed channel order deliberately not the ID order.
ELECTRODES = np.array([2210, 2211, 2212, 2213, 2430, 2431, 2432, 2433, 2650, 2651, 2652, 2653])
CHANNELS = np.array([7, 3, 11, 0, 5, 9, 1, 10, 2, 8, 4, 6])
#: Peak electrode (row of the routed array) of each unit: rows 2, 5 and 9
#: carry two units each.
UNIT_PEAK_ROW = np.array([0, 1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 9, 9, 10, 11])
N_UNITS = len(UNIT_PEAK_ROW)
BASE_RATE_HZ = 4.0
ON_RESPONDERS = (0, 3, 7)
OFF_RESPONDERS = (10, 12)
RESPONSE_WINDOW_S = (0.02, 0.12)
RESPONSE_SPIKES = 6          # extra spikes per event in the window
#: The unit phy's curation calls noise.
NOISE_UNIT = 14
#: Flash: ON at each even marker, OFF 1 s later; first marker at 1.0 s.
EVENT_TIMES_S = np.round(np.arange(1.0, DURATION_S - 1.0, 1.0), 4)
EVENT_LABELS = np.array(["ON" if i % 2 == 0 else "OFF" for i in range(len(EVENT_TIMES_S))])
N_T = 31                     # template samples


def electrode_xy_um() -> np.ndarray:
    rows = np.arange(len(ELECTRODES))
    return np.column_stack([1000 + 17.5 * (rows % 4), 500 + 17.5 * (rows // 4)])


@dataclass
class Fixture:
    folder: Path
    raw: Path
    sc_result: Path
    phy: Path
    #: Ground-truth spike *samples* per unit (sorter order).
    samples: list[np.ndarray]


def _trains(rng: np.random.Generator) -> list[np.ndarray]:
    trains = []
    for u in range(N_UNITS):
        n = rng.poisson(BASE_RATE_HZ * DURATION_S)
        t = rng.uniform(0, DURATION_S, n)
        for labels, units in (("ON", ON_RESPONDERS), ("OFF", OFF_RESPONDERS)):
            if u in units:
                ev = EVENT_TIMES_S[EVENT_LABELS == labels]
                extra = (ev[:, None] + rng.uniform(*RESPONSE_WINDOW_S, (len(ev), RESPONSE_SPIKES))).ravel()
                t = np.r_[t, extra]
        s = np.unique(np.floor(np.sort(t) * FS).astype(np.int64))
        trains.append(s[s < int(DURATION_S * FS)])
    return trains


def _write_raw(path: Path) -> None:
    import h5py

    n_frames = int(DURATION_S * FS)
    with h5py.File(path, "w") as f:
        f["mxw_version"] = np.array([b"24.1.3"])
        f["version"] = np.array([b"20190530"])
        g = f.create_group("data_store/data0000")
        g["groups/routed/channels"] = CHANNELS.astype(np.uint16)
        g["groups/routed/frame_nos"] = np.arange(FIRST_FRAME, FIRST_FRAME + n_frames, dtype=np.uint64)
        mapping = np.zeros(len(ELECTRODES), dtype=[("channel", "<i4"), ("electrode", "<i4"),
                                                   ("x", "<f8"), ("y", "<f8")])
        # Mapping rows in channel order, not routed order: the reader must join.
        order = np.argsort(CHANNELS)
        xy = electrode_xy_um()
        mapping["channel"], mapping["electrode"] = CHANNELS[order], ELECTRODES[order]
        mapping["x"], mapping["y"] = xy[order, 0], xy[order, 1]
        g["settings/mapping"] = mapping
        g["settings/sampling"] = np.array([FS])
        g["settings/lsb"] = np.array([6.29e-6])
        g["settings/gain"] = np.array([512.0])
        f["bits/0000"] = _ttl_log()


def _ttl_log() -> np.ndarray:
    """Frame sync toggling bit 5 at 60 Hz over a bit-7-high baseline (word
    128 ↔ 160), and the word dropping to 0 for 3 frames at each marker."""
    rows = []
    sync = np.arange(0.5, DURATION_S - 0.5, 1 / 60)
    for i, t in enumerate(sync):
        rows.append((t, 160))
        rows.append((t + 0.002, 128))
    for t in EVENT_TIMES_S:
        rows.append((t, 0))
        rows.append((t + 3 / FS, 128))
    rows.sort()
    out = np.zeros(len(rows), dtype=[("frameno", "<i8"), ("bits", "<i4")])
    out["frameno"] = [FIRST_FRAME + int(round(t * FS)) for t, _ in rows]
    out["bits"] = [w for _, w in rows]
    return out


def _templates(rng: np.random.Generator) -> np.ndarray:
    """``(n_units, N_T, n_electrodes)``: a spike on the peak row, half as big
    on its neighbours in the routed array."""
    shape = -np.exp(-0.5 * ((np.arange(N_T) - N_T // 2) / 2.0) ** 2)
    tmpl = np.zeros((N_UNITS, N_T, len(ELECTRODES)), dtype=np.float32)
    for u, row in enumerate(UNIT_PEAK_ROW):
        amp = 1.0 + 0.1 * rng.random()
        tmpl[u, :, row] = amp * shape
        for nb in (row - 1, row + 1):
            if 0 <= nb < len(ELECTRODES):
                tmpl[u, :, nb] = 0.4 * amp * shape
    return tmpl


def _write_spykingcircus(base: Path, samples: list[np.ndarray], tmpl: np.ndarray) -> Path:
    import h5py

    result = base.with_name(base.name + ".result-merged.hdf5")
    with h5py.File(result, "w") as f:
        for u, s in enumerate(samples):
            f[f"spiketimes/temp_{u}"] = s.astype(np.uint32)
            f[f"amplitudes/temp_{u}"] = np.ones((len(s), 2), np.float32)
    n_e = len(ELECTRODES)
    # SpyKING CIRCUS stores templates as a sparse (n_e * N_T, 2 * n_units)
    # matrix; row = electrode * N_T + t. The second half (orthogonal
    # components) is left empty here.
    rows, cols, vals = [], [], []
    for u in range(N_UNITS):
        flat = tmpl[u].T.reshape(-1)                 # (n_e, N_T) row-major
        nz = np.flatnonzero(flat)
        rows += nz.tolist(); cols += [u] * len(nz); vals += flat[nz].tolist()
    with h5py.File(base.with_name(base.name + ".templates-merged.hdf5"), "w") as f:
        f["temp_shape"] = np.array([n_e, N_T, 2 * N_UNITS], dtype=np.int32)
        f["temp_x"] = np.array(rows, dtype=np.int32)
        f["temp_y"] = np.array(cols, dtype=np.int32)
        f["temp_data"] = np.array(vals, dtype=np.float32)
    return result


def _write_phy(folder: Path, samples: list[np.ndarray], tmpl: np.ndarray) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    st = np.concatenate(samples)
    cl = np.concatenate([np.full(len(s), u) for u, s in enumerate(samples)])
    order = np.argsort(st, kind="stable")
    np.save(folder / "spike_times.npy", st[order].astype(np.uint64))
    np.save(folder / "spike_clusters.npy", cl[order].astype(np.int32))
    np.save(folder / "spike_templates.npy", cl[order].astype(np.int32))
    np.save(folder / "templates.npy", tmpl)
    np.save(folder / "channel_map.npy", np.arange(len(ELECTRODES), dtype=np.int32))
    np.save(folder / "channel_positions.npy", electrode_xy_um())
    (folder / "params.py").write_text(
        f"dat_path = 'missing.dat'\nn_channels_dat = {len(ELECTRODES)}\n"
        f"dtype = 'int16'\noffset = 0\nsample_rate = {FS}\nhp_filtered = True\n")
    (folder / "cluster_group.tsv").write_text(
        "cluster_id\tgroup\n" + "".join(
            f"{u}\t{'noise' if u == NOISE_UNIT else 'good'}\n" for u in range(N_UNITS)))
    return folder


def make_fixture(folder: str | Path, seed: int = 0) -> Fixture:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    samples = _trains(rng)
    tmpl = _templates(rng)
    raw = folder / f"{NAME}.raw.h5"
    _write_raw(raw)
    result = _write_spykingcircus(folder / f"{NAME}.raw", samples, tmpl)
    phy = _write_phy(folder / "phy" / f"{NAME}_phy", samples, tmpl)
    return Fixture(folder=folder, raw=raw, sc_result=result, phy=phy, samples=samples)
