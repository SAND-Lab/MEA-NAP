"""End-to-end CAT-NAP run with cell-type subnetwork analysis on the example data.

Run from the repo root::

    uv run python python/run_catnap_subnetwork_demo.py [--groups E/I|columns] [--out DIR]

Uses the gitignored ``local/example2pdataWCellTypes`` dataset (the same one
``python/test_pipeline_catnap.py`` checks parity against) and writes a full
output tree — including the new
``4A_IndividualNetworkAnalysis/.../cellTypeSubnetworks/`` figures and the three
``Subnetwork_*.csv`` batch tables — so the feature can be inspected on real
data. Skips with a clear message when the dataset is absent.

Denoising output is already cached in the dataset, but a single-lag run still
takes tens of minutes: probabilistic thresholding does 200 circular-shift
repeats, and the step-4 metric suite (null models, modularity, normalized
participation coefficient) then runs once for the whole network *and* once per
cell-type subnetwork. Add lags only if you want them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402

from meanap.catnap.pipeline import run_catnap_pipeline  # noqa: E402
from meanap.catnap.subnetwork import EXCITATORY_INHIBITORY_PRESET  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

DATASET_DIR = REPO_ROOT / "local" / "example2pdataWCellTypes"
RECORDING = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="E/I",
                    help="'E/I', 'columns' (one subnetwork per marker), or 'preset'")
    ap.add_argument("--groups-json", default=None,
                    help="JSON object (or path to one) of {group name: expression}, "
                         "as the GUI's custom-group editor produces. Overrides --groups.")
    ap.add_argument("--out", default=str(REPO_ROOT / "local" / "catnap_subnetwork_demo"))
    ap.add_argument("--lags", type=int, nargs="+", default=[1000],
                    help="lags in ms (default: just 1000 for a quick run)")
    args = ap.parse_args()

    if not (DATASET_DIR / RECORDING / "suite2p" / "plane0" / "stat.npy").exists():
        print(f"SKIP: example dataset not found at {DATASET_DIR}")
        return 0

    if args.groups_json:
        raw = args.groups_json
        if Path(raw).exists():
            raw = Path(raw).read_text()
        groups = json.loads(raw)
    else:
        groups = {"E/I": "E/I", "columns": None,
                  "preset": EXCITATORY_INHIBITORY_PRESET}[args.groups]
    print(f"Groups: {groups}")

    params = Params(
        raw_data=str(DATASET_DIR),
        suite2p_mode=True,
        twop_activity="peaks",
        func_con_lag_val=args.lags,
        min_activity_level=0.01,
        remove_nodes_with_no_peaks=True,
        prob_thresh_rep_num=200,
        prob_thresh_tail=0.05,
        min_number_of_nodes_to_cal_net_met=25,
        exclude_edges_below_threshold=True,
        num_2p_traces=0,          # trace figures are not what we're inspecting here
        twop_subnetwork_analysis=True,
        twop_subnetwork_groups=groups,
        random_seed=42,
    )

    recordings = [RecordingInfo(filename=RECORDING, div=21, group="HET")]
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    start = time.time()
    run_catnap_pipeline(
        params, recordings, out_root,
        log=lambda m: print(m, flush=True),
        rng=np.random.default_rng(params.random_seed),
    )
    print(f"\nDone in {time.time() - start:.0f}s → {out_root}")

    for path in sorted(out_root.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(out_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
