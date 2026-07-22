"""Parity test (Phase 3): reservoir matrices + shuffle observed trial proportion.

Validates the deterministic outputs against MATLAB:
  - FiringRateMatrix / latencyMatrix (Reservoir Computing Metrics/*.mat)
  - trialProp_obs (shuffleResults_pattern_1.mat)
The shuffle null itself is RNG-divergent (structural checks only).
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.pipeline.io import load_raw_recording, load_spike_times_mat  # noqa: E402
from meanap.stim.detection import detect_stim_times, get_stim_patterns  # noqa: E402
from meanap.stim.cleaning import clean_spikes_from_stim  # noqa: E402
from meanap.stim.reservoir import compute_reservoir_matrices  # noqa: E402
from meanap.stim.shuffle import stim_shuffle_test  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "local" / "testMEAstim"
OUT = RAW / "OutputData20Jul2026"
RECS = ["OWT220207_1H_DIV57_HUB45_3UA", "OWT220207_1H_DIV57_PER72_3UA"]
P = {
    "stimDetectionMethod": "longblank", "stimDetectionVal": 150,
    "stimRefractoryPeriod": 2.9, "stimDuration": 0.00012, "fs": 25000,
    "minBlankingDuration": 0.004, "stimTimeDiffThreshold": 0.005,
    "postStimWindowDur": 0.5, "SpikesMethod": "bior1p5",
    "stimAnalysisWindow": [-0.03, 0.03],
}


def _read_mat_matrix(path, key):
    with h5py.File(path, "r") as f:
        # MATLAB [trials x channels] -> h5py reads transposed
        return np.array(f[key]).T


def _resv_dir(name):
    return (OUT / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / "WT"
            / name / "Reservoir Computing Metrics")


def main() -> int:
    fails = 0
    for name in RECS:
        dat, ch, fs = load_raw_recording(RAW / f"{name}.mat")
        dat = dat.astype(np.float64)
        info = detect_stim_times(dat, {**P, "fs": fs}, ch, np.zeros((60, 2)))
        info, pats = get_stim_patterns(info, P)
        spikes = load_spike_times_mat(OUT / "ExperimentMatFiles" / f"{name}_OutputData20Jul2026.mat")
        spikes = clean_spikes_from_stim(spikes, info, P)

        # duration
        with h5py.File(RAW / f"{name}.mat", "r") as f:
            dur = f["dat"].shape[1] / float(f["fs"][()].ravel()[0])

        res = compute_reservoir_matrices(spikes, info, pats, P)

        fr_ml = _read_mat_matrix(_resv_dir(name) / "FiringRateMatrix_consolidated.mat", "FiringRateMatrix")
        lat_ml = _read_mat_matrix(_resv_dir(name) / "latencyMatrix_consolidated.mat", "latencyMatrix")

        def cmp(pyM, mlM, label):
            nonlocal fails
            both_nan = np.isnan(pyM) & np.isnan(mlM)
            ok = both_nan | np.isclose(pyM, mlM, rtol=1e-9, atol=1e-9)
            n_bad = int((~ok).sum())
            d = np.abs(pyM - mlM); d[both_nan] = 0
            print(f"  [{name}] {label:18s} shape{pyM.shape} {'OK' if not n_bad else f'FAIL({n_bad})'} "
                  f"max|Δ|={np.nanmax(d):.2e}  (nan match {int(both_nan.sum())})")
            fails += n_bad

        cmp(res["FiringRateMatrix"], fr_ml, "FiringRateMatrix")
        cmp(res["latencyMatrix"], lat_ml, "latencyMatrix")

        # trialProp_obs
        with h5py.File(_resv_dir(name).parent / "shuffleResults_pattern_1.mat", "r") as f:
            g = f["patternShuffleResults"]
            obs_ml = np.array(g["trialProp_obs"]).ravel()
        artifact_dur = res["analysis_window_s"][0]
        sh = stim_shuffle_test(spikes, pats[0],
                               {**P, "Nshuffles": 50, "artifactDuration_s": artifact_dur},
                               {"duration_s": dur}, 60, rng=np.random.default_rng(0))
        d = np.abs(sh.trial_prop_obs - obs_ml)
        n_bad = int((d > 1e-9).sum())
        print(f"  [{name}] trialProp_obs      shape{sh.trial_prop_obs.shape} "
              f"{'OK' if not n_bad else f'FAIL({n_bad})'} max|Δ|={d.max():.2e}")
        fails += n_bad
        # structural: null bounds sane
        assert sh.trial_prop_null.shape == (60, 50)
        assert np.all(sh.pctile_hi >= sh.pctile_lo - 1e-9)

    print(f"\n{'PASS' if not fails else f'FAIL ({fails} mismatches)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
