"""Run the Python pipeline's steps 2-4 on MATLAB's OWN spike times.

The straight MATLAB-vs-Python comparison conflates two things: (a) spike
detection is not bitwise identical between the two ports (wavelet CWT), and
(b) whatever the network-metric code itself does. Because a small firing-rate
difference changes which nodes pass the active-node filter, the two runs end
up computing metrics on *different graphs*, which makes every downstream
number look worse than the arithmetic actually is.

This script removes (a): it converts MATLAB's `_spikes.mat` files into the
`.npz` layout the Python runner expects, drops them where step 2 looks, and
runs steps 2-4 only. Any remaining difference is then attributable to the
step 2/3/4 code (plus the genuinely stochastic pieces), not to spike detection.

    uv run python parityRun/run_python_from_matlab_spikes.py
"""

import shutil
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "parityRun"))

from meanap.pipeline.io import load_spike_times_mat, save_spike_times_npz
from meanap.pipeline.runner import run_pipeline
from run_python_parity import build_params

MATLAB_SPIKES = (REPO_ROOT / "parityRun" / "OutputData_MATLAB_parity"
                 / "1_SpikeDetection" / "1A_SpikeDetectedData")
OUT_NAME = "OutputData_Python_fromMatlabSpikes"
OUT_ROOT = REPO_ROOT / "parityRun" / OUT_NAME
DEST = OUT_ROOT / "1_SpikeDetection" / "1A_SpikeDetectedData"

RECORDINGS = ["NGN2_20230208_P1_DIV14_A2", "NGN2_20230208_P1_DIV14_A3"]


def convert() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for rec in RECORDINGS:
        mat = MATLAB_SPIKES / f"{rec}_spikes.mat"
        spike_times = load_spike_times_mat(mat)

        # Channel list + fs come from the raw recording (the .mat's own
        # `channels` field is what MATLAB itself used).
        import h5py
        with h5py.File(REPO_ROOT / "ExampleData" / f"{rec}.mat", "r") as f:
            channels = np.array(f["channels"]).ravel().astype(int)
            fs = float(np.array(f["fs"]).ravel()[0])

        out = DEST / f"{rec}_spikes.npz"
        save_spike_times_npz(out, spike_times, channels, fs)
        methods = sorted({m for v in spike_times.values() for m in v})
        n = sum(len(v.get("bior1p5", [])) for v in spike_times.values())
        print(f"{rec}: {len(spike_times)} channels, methods={methods}, "
              f"{n} bior1p5 spikes -> {out.name}")


if __name__ == "__main__":
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    convert()

    p = build_params()
    p.output_data_folder_name = OUT_NAME
    p.start_analysis_step = 2   # reuse the converted MATLAB spikes
    p.stop_analysis_step = 4
    print(run_pipeline(p, log=print))
