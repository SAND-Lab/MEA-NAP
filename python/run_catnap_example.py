"""Full end-to-end CAT-NAP example run, to inspect what the port produces.

Run from the repo root::

    uv run python python/run_catnap_example.py [--out DIR] [--lags 1000 2500]

Uses the gitignored ``local/example2pdataWCellTypes`` dataset and writes a
complete output tree — every per-recording figure, the cell-type subnetwork
analysis, the batch comparison figures, every CSV, and ``report.html`` — so the
whole surface of the CAT-NAP path can be browsed in one place. Skips with a
clear message when the dataset is absent.

Unlike ``run_catnap_subnetwork_demo.py`` (which is scoped to the subnetwork
feature and runs one lag for speed), this runs the pipeline the way a user
would: through ``run_pipeline`` with ``suite2p_mode`` set, reading the
recording list from the dataset's own metadata spreadsheet.

**The dataset holds a single recording.** Everything per-recording is real and
complete, but the group-comparison figures are necessarily single-panel — there
is no second group or age to compare against. They are still generated, because
seeing their shape is the point of this run.

Expect tens of minutes: probabilistic thresholding does 200 circular-shift
repeats per lag, and the step-4 metric suite (null models, modularity,
normalized participation coefficient) then runs once for the whole network and
once per cell-type subnetwork, per lag.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params  # noqa: E402
from meanap.pipeline.report import generate_report  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402

DATASET_DIR = REPO_ROOT / "local" / "example2pdataWCellTypes"
RECORDING = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"
SPREADSHEET = DATASET_DIR / ("Metadata_OPME230825_full_20241031BatchSuite2p_"
                             "SingleTest20241121.csv")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO_ROOT / "local"),
                    help="parent folder for the output tree")
    ap.add_argument("--name", default="CATNAP_ExampleRun",
                    help="output folder name inside --out")
    ap.add_argument("--lags", type=int, nargs="+", default=[1000, 2500],
                    help="STTC lags in ms")
    ap.add_argument("--groups", default="E/I",
                    help="'E/I' or 'columns' (one subnetwork per marker)")
    ap.add_argument("--traces", type=int, default=6,
                    help="how many per-cell trace figures to draw")
    args = ap.parse_args()

    if not (DATASET_DIR / RECORDING / "suite2p" / "plane0" / "stat.npy").exists():
        print(f"SKIP: example dataset not found at {DATASET_DIR}")
        return 0
    if not SPREADSHEET.exists():
        print(f"SKIP: recording-list spreadsheet not found at {SPREADSHEET}")
        return 0

    params = Params(
        # ── inputs ──
        raw_data=str(DATASET_DIR),
        spreadsheet_file_name=str(SPREADSHEET),
        spreadsheet_range="2:1000",
        output_data_folder=args.out,
        output_data_folder_name=args.name,
        # ── CAT-NAP ──
        suite2p_mode=True,
        twop_activity="peaks",
        remove_nodes_with_no_peaks=True,
        num_2p_traces=args.traces,
        twop_subnetwork_analysis=True,
        twop_subnetwork_groups=(None if args.groups == "columns" else args.groups),
        # ── analysis config (matches the MATLAB parity run) ──
        func_con_lag_val=args.lags,
        min_activity_level=0.01,
        prob_thresh_rep_num=200,
        prob_thresh_tail=0.05,
        min_number_of_nodes_to_cal_net_met=25,
        exclude_edges_below_threshold=True,
        # Data-driven node-cartography boundaries (pooled PC/Z), as MATLAB's
        # autoSetCartographyBoundaries does.
        auto_set_cartography_boundaries=True,
        # Reproducible: the STTC threshold, modularity and null models are all
        # stochastic, so pin the seed or two runs will not match.
        random_seed=1,
    )

    print("=" * 70)
    print("CAT-NAP example run")
    print("=" * 70)
    print(f"  dataset : {DATASET_DIR}")
    print(f"  output  : {Path(args.out) / args.name}")
    print(f"  lags    : {args.lags} ms")
    print(f"  groups  : {params.twop_subnetwork_groups}")
    print()

    t0 = time.perf_counter()
    output_root = run_pipeline(params, log=lambda m: print(m, flush=True))
    elapsed = time.perf_counter() - t0

    report = generate_report(output_root)
    print(f"\nReport: {report}")

    n_png = len(list(output_root.rglob("*.png")))
    n_csv = len(list(output_root.rglob("*.csv")))
    print(f"Wrote {n_png} figures and {n_csv} CSVs in {elapsed / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
