#!/usr/bin/env python3
"""Generate the Python MEA-Stim figures into a MATLAB-mirroring output tree.

Runs the ported stim pipeline (detect -> patterns -> clean -> analysis) for each
test recording and writes every ported figure under

    <out-root>/2_NeuronalActivity/2A_IndividualNeuronalAnalysis/<Grp>/<recording>/

using the same filenames MATLAB produces, so ``plot_parity_report.py`` can pair
the two trees. Feeds MATLAB's own spikeTimes (ExperimentMatFiles) so the plots
reflect the parity-validated numeric core.

Usage:
    python python/gen_stim_plots.py \
        --out local/testMEAstim/PythonStimOutput20Jul2026
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np  # noqa: E402
import sys  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from meanap.pipeline.io import load_raw_recording, load_spike_times_mat  # noqa: E402
from meanap.pipeline.channel_layout import get_coords_from_layout  # noqa: E402
from meanap.stim.detection import detect_stim_times, get_stim_patterns, _matlab_mode  # noqa: E402
from meanap.stim.cleaning import clean_spikes_from_stim  # noqa: E402
from meanap.stim.psth import get_stim_artifact_duration  # noqa: E402
from meanap.stim.pipeline import write_stim_figures  # noqa: E402

RAW_DIR = REPO / "local" / "testMEAstim"
MAT_OUT = RAW_DIR / "OutputData20Jul2026"

RECORDINGS = [
    {"name": "OWT220207_1H_DIV57_HUB45_3UA", "grp": "WT", "div": 57},
    {"name": "OWT220207_1H_DIV57_PER72_3UA", "grp": "WT", "div": 57},
]

PARAMS = {
    "stimDetectionMethod": "longblank", "stimDetectionVal": 150,
    "stimRefractoryPeriod": 2.9, "stimDuration": 0.00012, "fs": 25000,
    "minBlankingDuration": 0.004, "stimTimeDiffThreshold": 0.005,
    "postStimWindowDur": 0.5, "SpikesMethod": "bior1p5",
    "stimAnalysisWindow": [-0.03, 0.03], "stimDurationForPlotting": 0.1,
    "rasterBinWidth": 0.01,
}



def generate_for_recording(rec: dict, out_root: Path) -> list[Path]:
    name, grp = rec["name"], rec["grp"]
    dest = out_root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / grp / name
    dest.mkdir(parents=True, exist_ok=True)

    dat, channels, fs = load_raw_recording(RAW_DIR / f"{name}.mat")
    dat = dat.astype(np.float64)
    lc, co = get_coords_from_layout("MCS60")
    coord_by_ch = {int(c): xy for c, xy in zip(lc, co)}
    coords = np.array([coord_by_ch[int(c)] for c in channels])

    stim_info = detect_stim_times(dat, {**PARAMS, "fs": fs}, channels, coords)
    stim_info, patterns = get_stim_patterns(stim_info, PARAMS)

    spikes = load_spike_times_mat(MAT_OUT / "ExperimentMatFiles" / f"{name}_OutputData20Jul2026.mat")
    spikes = clean_spikes_from_stim(spikes, stim_info, PARAMS)

    durs = [np.asarray(si.non_stim_blank_ends, float).ravel()
            - np.asarray(si.non_stim_blank_starts, float).ravel()
            for si in stim_info if si.non_stim_blank_starts is not None]
    durs = np.concatenate(durs) if durs else np.array([])
    blank_dur_mode = _matlab_mode(durs) if durs.size else 0.0
    params_full = {**PARAMS, "blankDurMode": blank_dur_mode}
    artifact_dur = get_stim_artifact_duration(params_full)

    info = {"FN": [name], "FileName": name, "Grp": grp, "DIV": rec["div"],
            "duration_s": dat.shape[0] / fs}

    write_stim_figures(dest, stim_info, patterns, spikes, params_full, dat,
                       artifact_dur, info, rng=np.random.default_rng(1))
    return sorted(dest.rglob("*.png"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RAW_DIR / "PythonStimOutput20Jul2026"),
                    help="output root (mirrors the MATLAB folder tree)")
    args = ap.parse_args()
    out_root = Path(args.out)
    total = 0
    for rec in RECORDINGS:
        files = generate_for_recording(rec, out_root)
        total += len(files)
        print(f"[{rec['name']}] wrote {len(files)} PNGs")
    print(f"Total {total} PNGs under {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
