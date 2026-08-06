"""Parity test: reading MCS .h5 directly vs. the .mat MEA-NAP used to require.

Each recording below exists twice on disk — as the raw Multi Channel Systems
export, and as the file ``convertMCSh5toMat.m`` produced from it. If the direct
reader is correct the two must agree exactly, since both are the same integer
ADC counts scaled by the same per-channel constants.

The data lives outside the repo (it is several GB); the test skips when absent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from meanap.pipeline.io import (  # noqa: E402
    count_raw_samples,
    find_raw_file,
    is_mcs_h5,
    load_mcs_h5,
    load_raw_recording,
)

# (MCS .h5, the .mat converted from it by MEA-NAP)
PAIRS = [
    (
        Path.home() / "Downloads/testConversion/TEST_DIV4.h5",
        Path.home() / "Downloads/testConversion/TEST_DIV4.mat",
    ),
    (   # 10 kHz, converted to a pre-v7.3 .mat (scipy path)
        Path.home() / "Downloads/recordings/N102512_39070_WT_div6.h5",
        Path.home() / "Downloads/recordings/lowFreqFiles/N102512_39070_WT_div6.mat",
    ),
    (   # 25 kHz, converted to a v7.3 .mat (h5py path)
        Path.home() / "Downloads/recordings/N103262_39207_E4_PS1KI_div11.h5",
        Path.home() / "Downloads/recordings/highFreqFiles/N103262_39207_E4_PS1KI_div11.mat",
    ),
]

# Comparing every sample of every pair means holding ~10 GB of float64; the
# scaling is per-channel and time-invariant, so a prefix over all channels
# exercises every distinct constant in the file.
N_SAMPLES = 200_000


def _compare(h5_path: Path, mat_path: Path) -> None:
    print(f"\n=== {h5_path.name} vs {mat_path.name}")
    assert is_mcs_h5(h5_path), f"{h5_path.name} not recognised as MCS HDF5"
    assert not is_mcs_h5(mat_path), f"{mat_path.name} wrongly recognised as MCS HDF5"

    dat_h5, ch_h5, fs_h5 = load_mcs_h5(h5_path)
    dat_mat, ch_mat, fs_mat = load_raw_recording(mat_path)

    assert fs_h5 == fs_mat, f"fs mismatch: {fs_h5} vs {fs_mat}"
    assert np.array_equal(ch_h5, ch_mat), "channel IDs differ"
    assert dat_h5.shape == dat_mat.shape, f"shape {dat_h5.shape} vs {dat_mat.shape}"
    assert dat_h5.dtype == dat_mat.dtype == np.float32

    diff = np.max(np.abs(dat_h5[:N_SAMPLES] - dat_mat[:N_SAMPLES]))
    print(f"  fs={fs_h5:g}  shape={dat_h5.shape}  channels[:6]={ch_h5[:6]}")
    print(f"  max |h5 - mat| over {N_SAMPLES} samples x {dat_h5.shape[1]} channels: {diff}")
    assert diff == 0.0, f"traces differ by up to {diff} µV"

    # Dispatch by content: load_raw_recording must handle the .h5 too.
    dat_disp, ch_disp, fs_disp = load_raw_recording(h5_path)
    assert np.array_equal(dat_disp[:N_SAMPLES], dat_h5[:N_SAMPLES])
    assert np.array_equal(ch_disp, ch_h5) and fs_disp == fs_h5
    print("  load_raw_recording dispatches to the MCS reader: ok")

    n_ch = len(ch_h5)
    assert count_raw_samples(h5_path, n_ch) == dat_h5.shape[0]
    assert count_raw_samples(mat_path, n_ch) == dat_mat.shape[0]
    print(f"  count_raw_samples agrees on both ({dat_h5.shape[0]} samples,"
          f" {dat_h5.shape[0] / fs_h5:.1f} s): ok")


def _check_find(tmp_h5: Path) -> None:
    """A folder holding only .h5 must still resolve, and .mat must win ties."""
    folder = tmp_h5.parent
    stem = tmp_h5.stem
    found = find_raw_file(folder, stem)
    assert found is not None, f"find_raw_file missed {stem} in {folder}"
    print(f"\n=== find_raw_file({folder.name}, {stem}) -> {found.path.name}")
    if (folder / f"{stem}.mat").exists():
        assert found.path.suffix == ".mat", "a co-located .mat should be preferred"
    else:
        assert found.path.suffix == ".h5"
    assert find_raw_file(folder, "no_such_recording") is None
    assert find_raw_file("", stem) is None


def main() -> int:
    pairs = [(h, m) for h, m in PAIRS if h.exists() and m.exists()]
    if not pairs:
        print("No MCS .h5/.mat pairs found on this machine — skipping.")
        return 0

    for h5_path, mat_path in pairs:
        _compare(h5_path, mat_path)

    # testConversion holds both formats; Downloads/recordings holds only .h5.
    for h5_path, _ in pairs:
        _check_find(h5_path)

    print(f"\nAll {len(pairs)} pair(s) match exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
