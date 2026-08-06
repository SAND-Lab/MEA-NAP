"""Parity test: reading an Axion .raw directly vs. MATLAB's own AxisFile toolbox.

Ground truth comes from Axion's bundled MATLAB reader driven exactly the way
``Functions/convertRawToMat/rawConvertFunc.m`` drives it::

    AllData  = AxisFile(raw).RawVoltageData.LoadData(well, [0 2]);
    dat      = [AllData{wellRow,wellCol,:,:}].GetVoltageVector;
    channels = ElectrodeColumn*10 + ElectrodeRow;

so agreement here means the pipeline sees exactly what it would have seen after
converting the plate to per-well ``.mat`` files.

The ``.raw`` itself is far too large for the repo, so the references live in
``python/test_fixtures/`` — regenerate them with
``matlab -batch "run('python/test_fixtures/gen_axion_reference.m')"``. The test
skips the parity checks when the recording isn't on this machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import h5py  # noqa: E402

from meanap.pipeline.axion_raw import (  # noqa: E402
    is_axion_raw,
    load_axion_well,
    read_axion_metadata,
    split_well_suffix,
)

RAW = Path.home() / "Downloads/Plate2_treated24hrs_DIV75.raw"
TRUTH_DIR = Path(__file__).resolve().parent / "test_fixtures"

# Values MATLAB reported for this recording (AxisFile → RawVoltageData).
EXPECTED_META = {
    "sampling_frequency": 12500.0,
    "voltage_scale": -5.8139534883720935e-08,
    "plate_type": 25165825,
    "data_start": 6398,
    "data_length": 2880000000,
    "n_data_columns": 384,
    "n_samples": 3750000,
}
EXPECTED_CHANNELS = [11, 21, 31, 41, 12, 22, 32, 42, 13, 23, 33, 43, 14, 24, 34, 44]
WELLS = ["A1", "B3", "D6", "C1", "A6"]


def check_metadata(meta) -> int:
    fail = 0
    for key, want in EXPECTED_META.items():
        got = getattr(meta, key)
        if got != want:
            print(f"FAIL {key}: got {got!r}, MATLAB says {want!r}"); fail += 1
    print(f"{'ok ' if not fail else 'FAIL'} metadata matches MATLAB "
          f"({meta.sampling_frequency:g} Hz, {meta.duration_s:g} s, "
          f"{meta.n_data_columns} channels)")

    wells = meta.wells()
    expected_wells = [f"{r}{c}" for r in "ABCD" for c in range(1, 7)]
    if wells != expected_wells:
        print(f"FAIL wells: got {wells}"); fail += 1
    else:
        print(f"ok  24-well plate detected: {wells[0]}..{wells[-1]}")
    return fail


def check_well(meta, well: str) -> int:
    truth_path = TRUTH_DIR / f"axion_well_{well}_reference.mat"
    if not truth_path.exists():
        print(f"skip {well} (no ground-truth fixture)")
        return 0

    with h5py.File(truth_path, "r") as t:
        dat_true = t["dat"][()]                        # (16, n) == MATLAB (n,16).T
        idx_true = t["idx"][()].ravel().astype(int)    # 1-based ChannelArray indices
        ch_true = t["channels"][()].ravel().astype(int)

    fail = 0
    cols = meta.columns_for_well(well)
    if [c + 1 for c in cols] != idx_true.tolist():
        print(f"FAIL {well}: electrode order {[c+1 for c in cols]} != {idx_true.tolist()}")
        fail += 1

    dat, channels, fs = load_axion_well(meta.path, well, metadata=meta)
    if channels.tolist() != ch_true.tolist():
        print(f"FAIL {well}: channels {channels.tolist()} != {ch_true.tolist()}"); fail += 1
    if channels.tolist() != EXPECTED_CHANNELS:
        print(f"FAIL {well}: channels don't match the Axion16 layout convention"); fail += 1

    n = dat_true.shape[1]
    # MATLAB returns double; the .mat load path casts to float32, so compare on
    # equal footing rather than crediting ourselves with spurious precision.
    diff = np.max(np.abs(dat[:n, :] - dat_true.T.astype(np.float32)))
    if diff != 0.0:
        print(f"FAIL {well}: traces differ by up to {diff:g} V"); fail += 1
    else:
        print(f"ok  {well}: {n} samples x {len(channels)} electrodes bit-exact, fs={fs:g}")
    return fail


def check_name_splitting() -> int:
    fail = 0
    cases = {
        "Plate2_treated24hrs_DIV75_A1": ("Plate2_treated24hrs_DIV75", "A1"),
        "Plate2_DIV75_D6": ("Plate2_DIV75", "D6"),
        "rec_B12": ("rec", "B12"),
        "NGN2_20230208_P1_DIV14": None,   # DIV14 must not read as well "V14"
        "recording": None,
    }
    for name, want in cases.items():
        got = split_well_suffix(name)
        if got != want:
            print(f"FAIL split_well_suffix({name!r}) = {got!r}, expected {want!r}"); fail += 1
    if not fail:
        print(f"ok  well-suffix splitting ({len(cases)} cases)")
    return fail


def main() -> int:
    fail = check_name_splitting()

    if not RAW.exists():
        print(f"\nNo Axion .raw at {RAW} — skipping the parity checks.")
        return 1 if fail else 0

    if not is_axion_raw(RAW):
        print(f"FAIL {RAW.name} not recognised as an Axion file")
        return 1

    meta = read_axion_metadata(RAW)
    fail += check_metadata(meta)
    for well in WELLS:
        fail += check_well(meta, well)

    print(f"\nFAILURES: {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
