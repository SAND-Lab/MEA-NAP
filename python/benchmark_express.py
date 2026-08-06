"""Time and size a full ephys run against the same run in express mode.

Run from the repo root::

    uv run python python/benchmark_express.py --out /path/for/outputs

Runs the Test Pipeline dataset (``local/testBurstDetection``) through steps 1-4
twice — once producing every figure, once producing only the data plus the
spike-detection checks — and reports the per-step durations and the size of
what each leaves behind. Both runs use the same seed, so the numbers they
compute are identical and only the drawing differs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402

#: The dataset the documented MATLAB-vs-Python comparison used
#: (PIPELINE_PORT_STATUS.md, "MATLAB vs Python speed comparison"): two Axion64
#: recordings, three lags, 200 thresholding shuffles. Kept identical here so
#: these numbers sit alongside those, rather than beside them on a different
#: dataset — a smaller recording would flatter express mode, since the figure
#: count barely shrinks while the compute does.
DATASET = REPO_ROOT / "ExampleData"
SPREADSHEET = DATASET / "exampleData.csv"
#: Only the two recordings the published benchmark timed; the spreadsheet also
#: lists B2/B3 etc.
SPREADSHEET_RANGE = "2:3"


def _params(out_dir: Path, name: str, *, express: bool) -> Params:
    return Params(
        raw_data=str(DATASET),
        spreadsheet_file_name=str(SPREADSHEET),
        spreadsheet_range=SPREADSHEET_RANGE,
        output_data_folder=str(out_dir),
        output_data_folder_name=name,
        start_analysis_step=1,
        stop_analysis_step=4,
        func_con_lag_val=[10, 25, 50],
        prob_thresh_rep_num=200,
        channel_layout="Axion64",
        time_processes=True,
        random_seed=1,
        express_mode=express,
    )


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _count(path: Path, pattern: str) -> int:
    return sum(1 for _ in path.rglob(pattern))


def _run(out_dir: Path, name: str, *, express: bool) -> dict:
    print(f"\n{'=' * 70}\n{name} (express={express})\n{'=' * 70}", flush=True)
    t0 = time.perf_counter()
    root = run_pipeline(_params(out_dir, name, express=express),
                        log=lambda m: print(m, flush=True))
    wall = time.perf_counter() - t0

    durations = {}
    durations_path = root / "step_durations.json"
    if durations_path.exists():
        durations = json.loads(durations_path.read_text())

    bundle = root.with_suffix(".meanap")
    return {
        "name": name, "root": root, "wall": wall, "durations": durations,
        "bytes": _dir_size(root),
        "figures": _count(root, "*.png"),
        "bundle_bytes": bundle.stat().st_size if bundle.exists() else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not SPREADSHEET.exists():
        print(f"SKIP: dataset not found at {DATASET}")
        return 0

    results = [
        _run(out_dir, "BenchFull", express=False),
        _run(out_dir, "BenchExpress", express=True),
    ]

    print(f"\n{'=' * 70}\nRESULTS\n{'=' * 70}")
    steps = sorted({k for r in results for k in r["durations"] if k != "total"})
    header = f"{'':<14}" + "".join(f"{s:>12}" for s in steps) + f"{'total':>12}{'wall':>12}"
    print(header)
    for r in results:
        row = f"{r['name']:<14}"
        for s in steps:
            row += f"{r['durations'].get(s, float('nan')):>12.1f}"
        row += f"{r['durations'].get('total', float('nan')):>12.1f}{r['wall']:>12.1f}"
        print(row)

    print()
    print(f"{'':<14}{'figures':>12}{'folder MB':>12}{'bundle MB':>12}")
    for r in results:
        b = "-" if r["bundle_bytes"] is None else f"{r['bundle_bytes'] / 1e6:.1f}"
        print(f"{r['name']:<14}{r['figures']:>12}{r['bytes'] / 1e6:>12.1f}{b:>12}")

    full, exp = results
    if full["durations"].get("total") and exp["durations"].get("total"):
        saved = full["durations"]["total"] - exp["durations"]["total"]
        pct = saved / full["durations"]["total"] * 100
        print(f"\ntime saved: {saved:.1f}s ({pct:.0f}%)")
    print(f"folder size: {full['bytes'] / 1e6:.1f} MB → {exp['bytes'] / 1e6:.1f} MB "
          f"({full['bytes'] / max(exp['bytes'], 1):.1f}x smaller)")
    if exp["bundle_bytes"]:
        print(f"bundle:      {exp['bundle_bytes'] / 1e6:.1f} MB "
              f"({full['bytes'] / exp['bundle_bytes']:.0f}x smaller than the full folder)")

    # Per-folder breakdown of where the bytes go.
    print()
    for r in results:
        print(f"{r['name']}:")
        for sub in sorted(p for p in r["root"].iterdir() if p.is_dir()):
            print(f"    {sub.name:<28}{_dir_size(sub) / 1e6:>8.1f} MB"
                  f"{_count(sub, '*.png'):>7} png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
