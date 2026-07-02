"""Test pipeline Step 2 — neuronal activity / burst detection parity with MATLAB.

Run from the repo root::

    uv run python python/test_pipeline_step2.py

Unlike ``test_pipeline_step1.py``, this test feeds Step 2 the *MATLAB reference
spike times* (not Python's own Step 1 output) before comparing against MATLAB's
``NeuronalActivity_RecordingLevel.csv`` / ``NeuronalActivity_NodeLevel.csv``.
That isolates Step 2 (firing rates + burst detection) from Step 1's known
bior1.5 wavelet approximation gap (F1 ~0.82-0.84) — a mismatch here means the
Step 2 arithmetic/algorithm itself disagrees with MATLAB, not that upstream
spike times differed.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params
from meanap.pipeline.example_data import download_example_data
from meanap.pipeline.io import load_raw_recording, load_spike_times_mat
from meanap.pipeline.firing_rates import firing_rates_bursts


EXAMPLE_DIR = REPO_ROOT / "ExampleData"
MATLAB_OUTPUT_ROOT = REPO_ROOT / "OutputData03Mar2026"
MATLAB_SPIKE_DIR = MATLAB_OUTPUT_ROOT / "1_SpikeDetection" / "1A_SpikeDetectedData"

RECORDINGS = [
    "NGN2_20230208_P1_DIV14_A2",
    "NGN2_20230208_P1_DIV14_A3",
]

# Params.spikes_method used for the OutputData03Mar2026 reference run
# (see Parameters_OutputData03Mar2026.csv: SpikesMethod=bior1p5)
SPIKES_METHOD = "bior1p5"

# Recording-level CSV column -> ephys dict key
RECORDING_LEVEL_FIELDS = {
    "numActiveElec": "numActiveElec",
    "FRmean": "FRmean",
    "FRmedian": "FRmedian",
    "NBurstRate": "NBurstRate",
    "meanNumChansInvolvedInNbursts": "meanNumChansInvolvedInNbursts",
    "meanNBstLengthS": "meanNBstLengthS",
    "meanISIWithinNbursts_ms": "meanISIWithinNbursts_ms",
    "meanISIoutsideNbursts_ms": "meanISIoutsideNbursts_ms",
    "CVofINBI": "CVofINBI",
    "fracInNburst": "fracInNburst",
    "channelAveBurstDur": "channelAveBurstDur",
    "channelAveISIwithinBurst": "channelAveISIwithinBurst",
    "channelAveISIoutsideBurst": "channelAveISIoutsideBurst",
    "channelAveFracSpikesInBursts": "channelAveFracSpikesInBursts",
}

# Node-level CSV column -> ephys dict key (both indexed by channel)
NODE_LEVEL_FIELDS = {
    "FR": "FR",
    "FRactive": "FRactive",
    "channelBurstRate": "channelBurstRate",
    "channelWithinBurstFr": "channelWithinBurstFr",
    "channelBurstDur": "channelBurstDur",
    "channelISIwithinBurst": "channelISIwithinBurst",
    "channeISIoutsideBurst": "channeISIoutsideBurst",
    "channelFracSpikesInBursts": "channelFracSpikesInBursts",
}


# ── Params matching the MATLAB OutputData03Mar2026 run ────────────────────────
# Source: OutputData03Mar2026/Parameters_OutputData03Mar2026.csv

def build_params() -> Params:
    p = Params()
    p.spikes_method = SPIKES_METHOD
    p.min_activity_level = 0.01
    p.network_burst_detection_method = "Bakkum"
    p.min_spike_network_burst = 10
    p.min_channel_network_burst = 3
    p.bakkum_network_burst_isi_n_threshold = "automatic"
    p.single_channel_burst_detection_method = "Bakkum"
    p.single_channel_burst_min_spike = 10
    p.single_channel_isi_threshold = "automatic"
    return p


# ── CSV ground truth loading ───────────────────────────────────────────────────

def load_recording_level_csv(path: Path) -> dict[str, dict[str, float]]:
    """Returns {recording_name: {column: value}}."""
    out: dict[str, dict[str, float]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out[row["FileName"]] = row
    return out


def load_node_level_csv(path: Path) -> dict[str, dict[int, dict[str, float]]]:
    """Returns {recording_name: {channel: {column: value}}}."""
    out: dict[str, dict[int, dict[str, float]]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rec = row["FileName"]
            ch = int(row["Channel"])
            out.setdefault(rec, {})[ch] = row
    return out


def _to_float(v) -> float:
    if v is None or v == "" or str(v).strip().upper() == "NaN".upper():
        return float("nan")
    return float(v)


# ── Comparison ──────────────────────────────────────────────────────────────

def values_match(a: float, b: float, abs_tol: float = 5e-3, rel_tol: float = 1e-2) -> bool:
    a_nan, b_nan = math.isnan(a), math.isnan(b)
    if a_nan or b_nan:
        return a_nan and b_nan
    return math.isclose(a, b, abs_tol=abs_tol, rel_tol=rel_tol)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("MEA-NAP Python  ▸  Step 2: Neuronal Activity / Burst Detection Parity Test")
    print("=" * 70)

    print("\n[0] Checking example data …")
    download_example_data(REPO_ROOT, log=print)

    rec_level_csv = load_recording_level_csv(MATLAB_OUTPUT_ROOT / "NeuronalActivity_RecordingLevel.csv")
    node_level_csv = load_node_level_csv(MATLAB_OUTPUT_ROOT / "NeuronalActivity_NodeLevel.csv")

    params = build_params()

    total_checks = 0
    total_matches = 0
    mismatches: list[str] = []

    for rec_name in RECORDINGS:
        print(f"\n{'─' * 60}")
        print(f"Recording: {rec_name}")
        print(f"{'─' * 60}")

        raw_path = EXAMPLE_DIR / f"{rec_name}.mat"
        dat, channels, fs = load_raw_recording(raw_path)
        duration_s = dat.shape[0] / fs
        n_channels = len(channels)
        print(f"  fs={fs:.0f} Hz, duration={duration_s:.1f} s, {n_channels} channels")

        matlab_spike_path = MATLAB_SPIKE_DIR / f"{rec_name}_spikes.mat"
        matlab_spikes = load_spike_times_mat(matlab_spike_path)
        spike_times_dict = {
            ch_idx: matlab_spikes.get(ch_idx, {}).get(SPIKES_METHOD, np.array([]))
            for ch_idx in range(n_channels)
        }
        total_spikes = sum(len(t) for t in spike_times_dict.values())
        print(f"  Loaded {total_spikes} MATLAB reference spikes (method={SPIKES_METHOD})")

        ephys = firing_rates_bursts(spike_times_dict, n_channels, fs, duration_s, params)

        # ── Recording-level comparison ──
        if rec_name not in rec_level_csv:
            print(f"  ! No recording-level MATLAB row for {rec_name}, skipping.")
            continue
        ml_row = rec_level_csv[rec_name]

        print(f"\n  Recording-level fields:")
        print(f"  {'Field':<32} {'Python':>14} {'MATLAB':>14}  Match")
        for csv_col, ephys_key in RECORDING_LEVEL_FIELDS.items():
            py_val = _to_float(ephys.get(ephys_key))
            ml_val = _to_float(ml_row.get(csv_col))
            match = values_match(py_val, ml_val)
            total_checks += 1
            total_matches += match
            flag = "✓" if match else "✗"
            print(f"  {csv_col:<32} {py_val:>14.4f} {ml_val:>14.4f}  {flag}")
            if not match:
                mismatches.append(f"{rec_name} / recording-level / {csv_col}: py={py_val} ml={ml_val}")

        # ── Node-level comparison ──
        if rec_name not in node_level_csv:
            print(f"  ! No node-level MATLAB rows for {rec_name}, skipping.")
            continue
        ml_nodes = node_level_csv[rec_name]

        print(f"\n  Node-level fields (aggregated over {n_channels} channels):")
        print(f"  {'Field':<32} {'#match':>8} {'#total':>8} {'max |diff|':>12}")
        for csv_col, ephys_key in NODE_LEVEL_FIELDS.items():
            py_arr = np.asarray(ephys.get(ephys_key), dtype=float)
            n_match = 0
            n_total = 0
            max_diff = 0.0
            for ch_idx, channel_id in enumerate(channels):
                if channel_id not in ml_nodes:
                    continue
                py_val = float(py_arr[ch_idx]) if ch_idx < len(py_arr) else float("nan")
                ml_val = _to_float(ml_nodes[channel_id].get(csv_col))
                n_total += 1
                total_checks += 1
                match = values_match(py_val, ml_val)
                if match:
                    n_match += 1
                    total_matches += 1
                else:
                    mismatches.append(
                        f"{rec_name} / node-level / {csv_col} / ch={channel_id}: py={py_val} ml={ml_val}"
                    )
                    if not (math.isnan(py_val) or math.isnan(ml_val)):
                        max_diff = max(max_diff, abs(py_val - ml_val))
            flag = "✓" if n_match == n_total else "~"
            print(f"  {flag} {csv_col:<30} {n_match:>8} {n_total:>8} {max_diff:>12.4f}")

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print("Summary")
    print(f"{'─' * 70}")
    print(f"Total checks: {total_checks}   Matches: {total_matches}   "
          f"({100 * total_matches / total_checks:.1f}% if total_checks else 0)")

    if mismatches:
        print(f"\nFirst {min(20, len(mismatches))} mismatches:")
        for m in mismatches[:20]:
            print(f"  ✗ {m}")

    print(f"\n{'=' * 70}")
    if total_matches == total_checks:
        print("  → Perfect parity with MATLAB")
    elif total_matches / total_checks > 0.9:
        print("  → Good parity — minor discrepancies, see mismatches above")
    else:
        print("  → Low parity — implementation differences need investigation")


if __name__ == "__main__":
    main()
