"""Score spike sorters against synthetic ground truth on a low-density MEA.

This is what picks MEA-NAP's default sorter and validates its presets and
curation floors — see python/SPIKE_SORTING_PLAN.md §5. Run it after touching
``pipeline/spike_sorting.py``::

    uv run python python/benchmark_spike_sorting.py --out local/spikesort_test/bench

For each seed it makes a recording with known units (``sorting_benchmark``),
runs every sorter on it once, and scores (a) the raw sorter output and (b)
what MEA-NAP's curation keeps as nodes, with auto-merge off and on. The
numbers that matter for a network analysis:

- ``found``: ground-truth neurons that became a node (accuracy ≥ 0.5)
- ``well``: … with accuracy ≥ 0.8
- ``fp``: nodes that are not a neuron (false-positive units)
- ``redund``: nodes that duplicate another node's neuron (over-split)
- ``acc``: mean per-neuron accuracy (0 for a neuron never found)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from meanap.pipeline.sorting_benchmark import (
    GroundTruthSpec, make_ground_truth, score_against_ground_truth,
)
from meanap.pipeline.spike_sorting import (
    SpikeSortingParams, build_recording, curate_sorting, preprocess, run_sorter_on,
)


def _numpy_sorting_from_result(result, fs):
    import spikeinterface.full as si
    from meanap.params import SORTED_METHOD
    trains = {str(result.units["id"][i]): (t[SORTED_METHOD] * fs).astype(np.int64)
              for i, t in result.spike_times.items()}
    if not trains:
        trains = {"none": np.zeros(0, dtype=np.int64)}
    return si.NumpySorting.from_unit_dict(trains, sampling_frequency=fs)


def run(args) -> pd.DataFrame:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in args.seeds:
        spec = GroundTruthSpec(duration_s=args.duration, seed=seed,
                               n_active_electrodes=args.electrodes,
                               noise_uv=args.noise)
        dat, channels, fs, gt, info = make_ground_truth(spec)
        print(f"\n== seed {seed}: {info['n_units']} units on {info['n_active_electrodes']} "
              f"electrodes (1/2/3 per electrode: {info['units_per_electrode']}), "
              f"{info['n_bursts']} bursts, amplitudes "
              f"{info['amplitudes_uv'].min():.0f}–{info['amplitudes_uv'].max():.0f} µV",
              flush=True)

        base = SpikeSortingParams(channel_layout=spec.channel_layout, n_jobs=args.jobs, seed=seed)
        work = out / f"seed{seed}"
        recording, kept = build_recording(dat, channels, fs, base)
        rec_pre = preprocess(recording, base, work / "preprocessed", args.jobs)

        for sorter in args.sorters:
            params = SpikeSortingParams(channel_layout=spec.channel_layout,
                                        sorter_name=sorter, n_jobs=args.jobs, seed=seed)
            t0 = time.time()
            try:
                sorting, version, sparams = run_sorter_on(
                    rec_pre, len(kept), params, work / sorter, log=lambda m: None)
            except Exception as e:  # a sorter that fails is a result too
                print(f"  {sorter}: FAILED {e!r}")
                rows.append(dict(seed=seed, sorter=sorter, stage="raw", error=repr(e)))
                continue
            dt = time.time() - t0
            raw = score_against_ground_truth(gt, sorting, fs)
            rows.append(_row(seed, sorter, "raw", False, raw, dt, info))
            print(f"  {sorter:15s} raw          {_fmt(raw)}  ({dt:.0f}s)", flush=True)

            for merge in ([False, True] if args.merge else [False]):
                p = SpikeSortingParams(channel_layout=spec.channel_layout, sorter_name=sorter,
                                       n_jobs=args.jobs, seed=seed, auto_merge=merge,
                                       curation_keep_labels=("good", "mua"))
                t1 = time.time()
                result = curate_sorting(sorting, rec_pre, channels, kept, fs, p,
                                        version, sparams, log=lambda m: None)
                curated = score_against_ground_truth(gt, _numpy_sorting_from_result(result, fs), fs)
                labels = list(result.units.get("label", []))
                stage = "curated+merge" if merge else "curated"
                row = _row(seed, sorter, stage, merge, curated, time.time() - t1, info)
                row["n_good"] = labels.count("good")
                row["n_mua"] = labels.count("mua")
                row["n_noise_dropped"] = sum(r["label"] == "noise" for r in result.all_units)
                rows.append(row)
                print(f"  {sorter:15s} {stage:12s} {_fmt(curated)}  "
                      f"[good {row['n_good']}, mua {row['n_mua']}, "
                      f"noise dropped {row['n_noise_dropped']}]", flush=True)

                # Where the misses are: per ground-truth unit, accuracy vs amplitude
                # and whether it shared its electrode.
                perf = curated["per_unit"].copy()
                perf["amplitude_uv"] = gt.get_property("gt_amplitude_uv")
                perf["channel_id"] = gt.get_property("gt_channel_id")
                perf["units_on_electrode"] = perf.groupby("channel_id")["channel_id"].transform("size")
                perf.to_csv(out / f"per_unit_seed{seed}_{sorter}_{stage}.csv")

        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)

    df = pd.DataFrame(rows)
    df.to_csv(out / "benchmark.csv", index=False)
    return df


def _row(seed, sorter, stage, merge, score, seconds, info):
    return dict(
        seed=seed, sorter=sorter, stage=stage, auto_merge=merge, seconds=round(seconds, 1),
        n_gt=score["n_gt"], n_sorted=score["n_sorted"], found=score["n_found"],
        well=score["n_well_detected"], fp=score["n_false_positive"],
        redund=score["n_redundant"], overmerged=score["n_overmerged"],
        acc=round(score["accuracy_mean"], 3), acc_median=round(score["accuracy_median"], 3),
        precision=round(score["precision_mean"], 3), recall=round(score["recall_mean"], 3),
    )


def _fmt(score):
    return (f"found {score['n_found']:2d}/{score['n_gt']} (well {score['n_well_detected']:2d})  "
            f"nodes {score['n_sorted']:3d}  fp {score['n_false_positive']:2d}  "
            f"redund {score['n_redundant']:2d}  acc {score['accuracy_mean']:.2f}")


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    ok = df[df.get("error").isna()] if "error" in df else df
    cols = ["found", "well", "fp", "redund", "n_sorted", "acc", "precision", "recall", "seconds"]
    return ok.groupby(["sorter", "stage"])[cols].mean().round(2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="local/spikesort_test/bench")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--sorters", nargs="+", default=["mountainsort5", "tridesclous2"])
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--electrodes", type=int, default=30)
    ap.add_argument("--noise", type=float, default=5.0)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--no-merge", dest="merge", action="store_false")
    ap.add_argument("--keep", action="store_true", help="keep sorter working folders")
    args = ap.parse_args(argv)
    df = run(args)
    print("\n== mean over seeds ==")
    summary = summarise(df)
    print(summary.to_string())
    (Path(args.out) / "summary.json").write_text(json.dumps(summary.reset_index().to_dict("records"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
