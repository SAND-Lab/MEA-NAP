"""Does feeding bior1.5 wavelet spikes into Tridesclous2 find smaller spikes
than lowering Tridesclous2's own threshold?

    uv run python python/benchmark_hybrid_sorting.py --out local/spikesort_test/hybrid

Synthetic ground truth (``sorting_benchmark``) with a wide amplitude range,
so there are spikes near the noise floor to be won or lost; each condition
is a variant of TDC2's component chain (``sorting_components``):

- ``tdc2-stock``     the installed sorter, as the pipeline runs it (5 σ / 5 σ)
- ``thr5/peel5``     the rebuilt chain at the same settings — must match stock
- ``thr4/peel4``     threshold candidates at 4 σ, peeler at 4 σ
- ``thr3.5/peel3.5`` … and at 3.5 σ
- ``bior/peel5``     bior1.5 candidates, peeler at 5 σ (wavelet only shapes the templates)
- ``bior/peel3.5``   bior1.5 candidates, peeler at 3.5 σ
- ``bior/assign``    bior1.5 candidates, no peeler: every wavelet spike kept and
                     labelled by the clustering

Scores are against ground truth (accuracy, found, false positives, over-splits),
plus recall broken down by the true unit's amplitude, which is where the
conditions are expected to differ.
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
from meanap.pipeline.sorting_components import peaks_from_spike_times, run_tdc2_components
from meanap.pipeline.spike_detection import SpikeDetectionParams, detect_spikes_recording
from meanap.pipeline.spike_sorting import (
    SpikeSortingParams, build_recording, curate_sorting, preprocess, run_sorter_on,
    sorter_presets,
)


def _curated(sorting, rec_pre, channels, kept, fs, params):
    """MEA-NAP's curation (SNR, rate, refractory floors; good+mua kept) as a
    sorting, so a condition that makes noise clusters is judged on what
    would actually become nodes."""
    import spikeinterface.full as si
    from meanap.params import SORTED_METHOD
    res = curate_sorting(sorting, rec_pre, channels, kept, fs, params, "", {})
    trains = {str(res.units["id"][i]): (t[SORTED_METHOD] * fs).astype(np.int64)
              for i, t in res.spike_times.items()} or {"none": np.zeros(0, dtype=np.int64)}
    return si.NumpySorting.from_unit_dict(trains, sampling_frequency=fs), res

CONDITIONS = [
    ("tdc2-stock", None),
    ("thr5/peel5", dict(detect_threshold=5.0, peeler_threshold=5.0, assign="peeler")),
    ("thr4/peel4", dict(detect_threshold=4.0, peeler_threshold=4.0, assign="peeler")),
    ("thr3.5/peel3.5", dict(detect_threshold=3.5, peeler_threshold=3.5, assign="peeler")),
    ("bior/peel5", dict(peaks="bior", peeler_threshold=5.0, assign="peeler")),
    ("bior/peel3.5", dict(peaks="bior", peeler_threshold=3.5, assign="peeler")),
    ("bior/assign", dict(peaks="bior", assign="peaks")),
]

AMP_BINS = [(0, 25), (25, 40), (40, 70), (70, 1e9)]


def bior_peaks(dat, channels, fs, kept, recording_w, n_jobs):
    """MEA-NAP's bior1.5 detection, as the pipeline runs it, as candidate peaks."""
    p = SpikeDetectionParams(fs=fs, thresholds=[], wname_list=["bior1.5"], cost_list=[-0.12],
                             filter_low_pass=600, filter_high_pass=8000, ref_period_ms=2.0,
                             pos_peak_thr_mult=40.0, wavelet_ref_period_ms=0.5)
    r = detect_spikes_recording(dat, channels, fs, p, max_workers=n_jobs)
    by_col = {col: m["bior1p5"] for col, m in r.spike_times.items()}
    return peaks_from_spike_times(by_col, fs, kept, recording_w)


def run(args) -> pd.DataFrame:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, per_unit_rows = [], []
    for seed in args.seeds:
        spec = GroundTruthSpec(duration_s=args.duration, seed=seed,
                               n_active_electrodes=args.electrodes, noise_uv=args.noise,
                               amplitude_uv=(args.amp_min, args.amp_max))
        dat, channels, fs, gt, info = make_ground_truth(spec)
        amps = gt.get_property("gt_amplitude_uv")
        print(f"\n== seed {seed}: {info['n_units']} units, amplitudes "
              f"{amps.min():.0f}–{amps.max():.0f} µV (noise {args.noise} µV); "
              f"{(amps < 25).sum()} under 25 µV, {((amps >= 25) & (amps < 40)).sum()} at 25–40",
              flush=True)

        base = SpikeSortingParams(channel_layout=spec.channel_layout, n_jobs=args.jobs, seed=seed)
        work = out / f"seed{seed}"
        recording, kept = build_recording(dat, channels, fs, base)
        rec_pre = preprocess(recording, base, work / "preprocessed", args.jobs)
        presets = sorter_presets("tridesclous2", 200.0, len(kept))
        jobs = dict(n_jobs=args.jobs, chunk_duration="1s", progress_bar=False, mp_context="spawn")

        import spikeinterface.full as si
        rec_w = si.whiten(rec_pre, dtype="float32", mode="local", radius_um=100.0)
        peaks_b = bior_peaks(dat, channels, fs, kept, rec_w, args.jobs)
        print(f"  bior1.5 candidates: {len(peaks_b)}", flush=True)

        for name, cond in CONDITIONS:
            if args.only and name not in args.only:
                continue
            t0 = time.time()
            try:
                if cond is None:
                    p = SpikeSortingParams(channel_layout=spec.channel_layout,
                                           sorter_name="tridesclous2", n_jobs=args.jobs, seed=seed)
                    sorting, _, _ = run_sorter_on(rec_pre, len(kept), p, work / "stock")
                    cinfo = {}
                else:
                    kw = dict(cond)
                    peaks = peaks_b if kw.pop("peaks", None) == "bior" else None
                    sorting, cinfo = run_tdc2_components(
                        rec_pre, peaks=peaks, sorter_params=presets, job_kwargs=jobs,
                        seed=seed, **kw)
            except Exception as e:
                print(f"  {name:16s} FAILED {e!r}", flush=True)
                rows.append(dict(seed=seed, condition=name, error=repr(e)))
                continue
            dt = time.time() - t0
            curated, res = _curated(sorting, rec_pre, channels, kept, fs, base)
            labels = list(res.units.get("label", []))
            for stage, srt in (("raw", sorting), ("curated", curated)):
                sc = score_against_ground_truth(gt, srt, fs)
                perf = sc["per_unit"].copy()
                perf["amplitude_uv"] = amps
                perf["condition"] = name
                perf["stage"] = stage
                perf["seed"] = seed
                per_unit_rows.append(perf)
                row = dict(seed=seed, condition=name, stage=stage, seconds=round(dt, 1),
                           n_sorted=sc["n_sorted"], found=sc["n_found"], well=sc["n_well_detected"],
                           fp=sc["n_false_positive"], redund=sc["n_redundant"],
                           acc=round(sc["accuracy_mean"], 3), precision=round(sc["precision_mean"], 3),
                           recall=round(sc["recall_mean"], 3),
                           n_spikes=int(sum(srt.count_num_spikes_per_unit().values())),
                           n_good=labels.count("good"), n_mua=labels.count("mua"),
                           **{k: v for k, v in cinfo.items() if isinstance(v, (int, float))})
                for lo, hi in AMP_BINS:
                    m = (amps >= lo) & (amps < hi)
                    row[f"recall_{lo:g}-{hi if hi < 1e9 else 'max'}uV"] = (
                        round(float(perf.loc[m, "recall"].mean()), 3) if m.any() else np.nan)
                    row[f"found_{lo:g}-{hi if hi < 1e9 else 'max'}uV"] = (
                        f"{int((perf.loc[m, 'accuracy'] >= 0.5).sum())}/{int(m.sum())}")
                rows.append(row)
                print(f"  {name:15s} {stage:7s} found {sc['n_found']:2d}/{sc['n_gt']} (well {sc['n_well_detected']:2d}) "
                      f"nodes {sc['n_sorted']:3d} fp {sc['n_false_positive']:2d} redund {sc['n_redundant']:2d} "
                      f"acc {sc['accuracy_mean']:.2f} recall {sc['recall_mean']:.2f} "
                      f"precision {sc['precision_mean']:.2f} | <25µV found "
                      f"{row['found_0-25uV']} recall {row['recall_0-25uV']:.2f} | {dt:.0f}s", flush=True)
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)

    df = pd.DataFrame(rows)
    df.to_csv(out / "hybrid_benchmark.csv", index=False)
    if per_unit_rows:
        pd.concat(per_unit_rows).to_csv(out / "hybrid_per_unit.csv")
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="local/spikesort_test/hybrid")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--electrodes", type=int, default=30)
    ap.add_argument("--noise", type=float, default=5.0)
    ap.add_argument("--amp-min", type=float, default=10.0)
    ap.add_argument("--amp-max", type=float, default=120.0)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    df = run(args)
    ok = df[df["error"].isna()] if "error" in df else df
    cols = [c for c in ["found", "well", "fp", "redund", "n_sorted", "acc", "precision", "recall",
                        "recall_0-25uV", "recall_25-40uV", "recall_40-70uV", "recall_70-maxuV",
                        "n_spikes", "seconds"] if c in ok]
    summary = ok.groupby(["stage", "condition"])[cols].mean().round(3)
    order = [(st, n) for st in ("raw", "curated") for n, _ in CONDITIONS if (st, n) in summary.index]
    print("\n== mean over seeds ==")
    print(summary.loc[order].to_string())
    (Path(args.out) / "hybrid_summary.json").write_text(
        json.dumps(summary.loc[order].reset_index().to_dict("records"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
