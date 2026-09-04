"""CAT-NAP runs that analyse several measures of activity at once.

Run from the repo root::

    uv run python python/test_catnap_multi_activity.py

``Params.twop_activities`` lets one run build the network from detected calcium
events *and* from the deconvolved trace (and from raw fluorescence, and from
suite2p's spike estimate) over the same recordings, so the choice of measure
becomes an axis of the output instead of a decision buried in a settings file.
That is only worth having if three things hold, which is what this checks:

  - **layout** — the primary measure writes exactly what a one-measure run
    always wrote, byte-for-byte in name and place, and each extra measure gets a
    complete run folder of its own under ``ByActivityType/``; the pooled tables
    carry every measure with an ``ActivityType`` column;
  - **independence** — the measures do not contaminate each other: each gets
    its own cartography boundaries, its own metric ranges, and a generator
    seeded the same way it would be if it were the only measure in the run, so
    ``peaks`` alone and ``peaks`` beside ``denoised F`` give identical numbers;
  - **the comparison** — the statistics step analyses each measure separately
    and then compares them, and its verdicts say what they mean: agreement,
    paired shift, and whether the group conclusion survives a change of
    measure.

Sections A-C run on synthetic suite2p folders; section D runs the statistics
step on a synthetic multi-measure table. No MATLAB and no example dataset.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.params import Params                                   # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo              # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else f"   [{detail}]"
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── synthetic suite2p input ──────────────────────────────────────────────────

N_ROIS = 14
N_FRAMES = 1200
FS = 30.0


def _write_suite2p(plane0: Path, seed: int) -> None:
    """A minimal suite2p plane0 folder with correlated, event-like traces.

    Events rather than noise so ``peaks`` has something to detect and the two
    measures have a chance of agreeing; correlated rather than independent so
    the adjacency is not a matrix of zeros, which would make every metric
    constant and every comparison below vacuous.
    """
    rng = np.random.default_rng(seed)
    plane0.mkdir(parents=True, exist_ok=True)

    # Two latent event trains; each ROI follows one of them plus its own noise.
    latent = np.zeros((2, N_FRAMES))
    for k in range(2):
        onsets = rng.choice(N_FRAMES - 60, size=18, replace=False)
        for t in onsets:
            latent[k, t:t + 30] += np.exp(-np.arange(30) / 8.0)

    F = np.zeros((N_ROIS, N_FRAMES))
    for i in range(N_ROIS):
        F[i] = (300.0 + 60.0 * latent[i % 2]
                + rng.normal(0, 4.0, N_FRAMES)).astype(float)

    np.save(plane0 / "F.npy", F)
    np.save(plane0 / "Fneu.npy", np.full_like(F, 100.0))
    np.save(plane0 / "spks.npy", np.clip(rng.normal(0, 1, F.shape), 0, None))
    np.save(plane0 / "iscell.npy", np.column_stack(
        [np.ones(N_ROIS), np.full(N_ROIS, 0.9)]))
    stat = np.array([{"med": [int(rng.integers(0, 250)), int(rng.integers(0, 250))],
                      "ypix": np.array([0]), "xpix": np.array([0])}
                     for _ in range(N_ROIS)], dtype=object)
    np.save(plane0 / "stat.npy", stat, allow_pickle=True)
    np.save(plane0 / "ops.npy",
            np.array({"fs": FS, "meanImg": rng.random((250, 250))}, dtype=object),
            allow_pickle=True)


def _params(raw: Path, activities: tuple[str, ...]) -> Params:
    return Params(
        suite2p_mode=True, raw_data=str(raw),
        twop_activity="peaks", twop_activities=activities,
        func_con_lag_val=[500],
        prob_thresh_rep_num=8,          # the run's expensive half, kept tiny
        min_number_of_nodes_to_cal_net_met=4,
        num_2p_traces=0,                # no raw-data figures needed here
        twop_network_background=False,
        auto_set_cartography_boundaries=True,
        random_seed=7,
        recording_workers=1,
    )


def _run(root: Path, raw: Path, recordings, activities) -> list[str]:
    from meanap.catnap.pipeline import run_catnap_pipeline
    from meanap.pipeline.output_folders import create_output_folders

    out = create_output_folders(root.parent, root.name,
                                sorted({r.group for r in recordings}))
    logs: list[str] = []
    run_catnap_pipeline(_params(raw, activities), recordings, out, logs.append)
    return logs


def _dataset(n_recordings: int = 4):
    """A raw-data folder plus the roster describing it."""
    tmp = Path(tempfile.mkdtemp())
    raw = tmp / "raw"
    recordings = []
    for i in range(n_recordings):
        name = f"CULT{i:02d}_20240101_DIV{14 + 7 * (i % 2)}"
        _write_suite2p(raw / name / "suite2p" / "plane0", seed=100 + i)
        recordings.append(RecordingInfo(
            filename=name, div=float(14 + 7 * (i % 2)),
            group="WT" if i % 2 else "KO"))
    return tmp, raw, recordings


# ── Section A: layout ────────────────────────────────────────────────────────

def _layout_checks() -> list[Check]:
    from meanap.catnap.activities import (
        activity_output_root, activity_params, activity_types, is_multi_activity,
    )

    checks: list[Check] = []

    single = Params(suite2p_mode=True, twop_activity="spks")
    checks.append(("a run with no extra measures analyses just its own",
                   activity_types(single) == ["spks"], f"{activity_types(single)}"))
    checks.append(("…and is not a multi-measure run",
                   not is_multi_activity(single), ""))
    checks.append(("…and keeps the top-level output folder",
                   activity_output_root(Path("/out"), single, "spks") == Path("/out"),
                   ""))

    multi = Params(suite2p_mode=True, twop_activity="peaks",
                   twop_activities=("denoised F", "peaks"))
    checks.append(("the primary measure leads, however the extras are ordered",
                   activity_types(multi) == ["peaks", "denoised F"],
                   f"{activity_types(multi)}"))
    checks.append(("the primary measure still owns the run folder",
                   activity_output_root(Path("/out"), multi, "peaks") == Path("/out"),
                   ""))
    checks.append(("an extra measure gets a subtree named by its slug",
                   activity_output_root(Path("/out"), multi, "denoised F")
                   == Path("/out/ByActivityType/denoisedF"), ""))

    per_measure = activity_params(multi, "denoised F")
    checks.append(("a measure's own params name it and nothing else",
                   per_measure.twop_activity == "denoised F"
                   and not per_measure.twop_activities, ""))
    checks.append(("…so its folders are named for what it measures",
                   _folder(per_measure) == "500msbin", _folder(per_measure)))
    checks.append(("…while the event measure's are still lags",
                   _folder(activity_params(multi, "peaks")) == "500mslag", ""))
    return checks


def _folder(params) -> str:
    from meanap.timescale import timescale_folder

    return timescale_folder(500, params)


# ── Section B: a real two-measure run ────────────────────────────────────────

def _run_checks(tmp: Path, raw: Path, recordings) -> tuple[list[Check], Path]:
    checks: list[Check] = []
    root = tmp / "OutTwo"
    logs = _run(root, raw, recordings, ("denoised F",))
    text = "\n".join(logs)

    checks.append(("the run says which measures it analysed",
                   "Measures of activity: peaks, denoised F" in text,
                   text[:200]))

    net = root / "4_NetworkActivity"
    sub = root / "ByActivityType" / "denoisedF"
    checks.append(("the primary measure keeps the top-level results",
                   (net / "netmet_results.json").exists(), ""))
    checks.append(("the extra measure gets its own complete run folder",
                   (sub / "4_NetworkActivity" / "netmet_results.json").exists()
                   and (sub / "params.json").exists(), f"{sorted(p.name for p in sub.iterdir())}"))
    if (sub / "params.json").exists():
        with open(sub / "params.json") as fh:
            saved = json.load(fh)
        checks.append(("…whose params name that measure alone",
                       saved.get("twop_activity") == "denoised F"
                       and not saved.get("twop_activities"),
                       f"{saved.get('twop_activity')}"))

    rec_csv = net / "NetworkActivity_RecordingLevel.csv"
    table = pd.read_csv(rec_csv) if rec_csv.exists() else pd.DataFrame()
    checks.append(("the pooled table carries an ActivityType column",
                   "ActivityType" in table.columns, f"{list(table.columns)[:6]}"))
    if "ActivityType" in table.columns:
        found = sorted(table["ActivityType"].unique())
        checks.append(("…naming both measures",
                       found == ["denoised F", "peaks"], f"{found}"))
        checks.append(("…with a row per recording per measure",
                       len(table) == 2 * len(recordings), f"{len(table)}"))
        checks.append(("…and the same recordings under each",
                       set(table[table["ActivityType"] == "peaks"]["FileName"])
                       == set(table[table["ActivityType"] == "denoised F"]["FileName"]),
                       ""))

    per_measure = pd.read_csv(sub / "4_NetworkActivity"
                              / "NetworkActivity_RecordingLevel.csv")
    checks.append(("the subtree's own table holds only its measure",
                   "ActivityType" not in per_measure.columns
                   and len(per_measure) == len(recordings),
                   f"{len(per_measure)}"))

    act_csv = root / "2_NeuronalActivity" / "TwoPhotonActivity_RecordingLevel.csv"
    act = pd.read_csv(act_csv) if act_csv.exists() else pd.DataFrame()
    checks.append(("the activity stats are pooled the same way",
                   "ActivityType" in act.columns and len(act) == 2 * len(recordings),
                   f"{len(act)}"))

    # Each measure's state file, in its own ExperimentMatFiles.
    name = recordings[0].filename
    checks.append(("each measure stores its own adjacency for re-runs",
                   (root / "ExperimentMatFiles" / f"{name}_catnap.npz").exists()
                   and (sub / "ExperimentMatFiles" / f"{name}_catnap.npz").exists(),
                   ""))

    # Figure folders: a lag for the event measure, a bin for the correlation one.
    fig_root = net / "4A_IndividualNetworkAnalysis"
    lag_dirs = {p.name for p in fig_root.rglob("*mslag") if p.is_dir()}
    bin_dirs = {p.name for p in (sub / "4_NetworkActivity"
                                 / "4A_IndividualNetworkAnalysis").rglob("*msbin")
                if p.is_dir()}
    checks.append(("the event measure's figures are filed under a lag",
                   lag_dirs == {"500mslag"}, f"{lag_dirs}"))
    checks.append(("…and the correlation measure's under a bin",
                   bin_dirs == {"500msbin"}, f"{bin_dirs}"))
    return checks, root


# ── Section C: the measures do not contaminate each other ────────────────────

def _independence_checks(tmp: Path, raw: Path, recordings, two_root: Path) -> list[Check]:
    """Running ``peaks`` beside another measure must not change ``peaks``.

    The property that makes a multi-measure run usable as a comparison: if the
    numbers moved depending on which other measures were in the run, the
    comparison would be measuring the run's configuration rather than the
    measures. It holds because every measure draws from a generator seeded from
    the recording name alone, never from a stream shared down the run.
    """
    checks: list[Check] = []
    one_root = tmp / "OutOne"
    _run(one_root, raw, recordings, ())

    def load(root: Path) -> pd.DataFrame:
        frame = pd.read_csv(root / "4_NetworkActivity"
                            / "NetworkActivity_RecordingLevel.csv")
        if "ActivityType" in frame.columns:
            frame = frame[frame["ActivityType"] == "peaks"].drop(
                columns=["ActivityType"])
        return frame.sort_values("FileName").reset_index(drop=True)

    alone, beside = load(one_root), load(two_root)
    shared = [c for c in alone.columns if c in beside.columns]
    checks.append(("the same columns come out either way",
                   len(shared) == len(alone.columns) == len(beside.columns),
                   f"{sorted(set(alone.columns) ^ set(beside.columns))}"))

    numeric = [c for c in shared
               if pd.api.types.is_numeric_dtype(alone[c])
               and pd.api.types.is_numeric_dtype(beside[c])]
    mismatched = [c for c in numeric
                  if not np.allclose(alone[c].to_numpy(float),
                                     beside[c].to_numpy(float),
                                     rtol=1e-9, atol=1e-12, equal_nan=True)]
    checks.append(("peaks gives identical numbers alone and in company",
                   not mismatched, f"differs in {mismatched[:6]}"))

    # Cartography boundaries are derived per measure from that measure's own
    # pooled PC/Z, so the two subtrees must not be carrying the same ones.
    def boundaries(root: Path, activity: str) -> tuple:
        with open(root / "4_NetworkActivity" / "netmet_results.json") as fh:
            data = json.load(fh)
        first = next(iter(data.values()))
        return tuple(next(iter(first.values())).get("cartographyBoundaries") or ())

    peaks_bounds = boundaries(two_root, "peaks")
    other_bounds = boundaries(two_root / "ByActivityType" / "denoisedF", "denoised F")
    checks.append(("each measure got cartography boundaries of its own",
                   bool(peaks_bounds) and peaks_bounds != other_bounds,
                   f"{peaks_bounds} vs {other_bounds}"))
    return checks


# ── Section D: the statistics step's comparison ──────────────────────────────

def _make_multi_measure_run(root: Path) -> Path:
    """A run folder whose tables carry two measures of the same recordings.

    Built by hand rather than by running the pipeline: this section is about
    what the statistics step does with a measure axis, and a synthetic table
    lets the answer be known in advance. ``Q`` is given a genotype effect under
    ``peaks`` and none under ``denoised F``, which is exactly the situation the
    concordance table exists to surface; ``Dens`` gets the same effect under
    both, and should come out concordant.
    """
    rng = np.random.default_rng(3)
    rows = []
    for culture in range(28):
        group = "WT" if culture % 2 else "KO"
        for div in (14, 21, 28):
            name = f"CULT{culture:03d}_20240101_DIV{div}"
            base = 0.02 * div + rng.normal(0, 0.05)
            q_effect = 0.35 if group == "KO" else 0.0
            for activity in ("peaks", "denoised F"):
                # A measure-specific offset and scale, so agreement is high in
                # rank and poor in absolute value — the usual real case.
                scale = 1.0 if activity == "peaks" else 2.5
                rows.append({
                    "FileName": name, "Grp": group, "DIV": float(div),
                    "ActivityType": activity, "Lag": "500mslag",
                    "Dens": scale * (base + 0.05 * (group == "KO"))
                    + rng.normal(0, 0.01),
                    "Q": (0.4 + (q_effect if activity == "peaks" else 0.0)
                          + rng.normal(0, 0.06)),
                    "aN": float(rng.integers(20, 60)),
                    "Eglob": scale * base + rng.normal(0, 0.02),
                })
    net = root / "4_NetworkActivity"
    net.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(net / "NetworkActivity_RecordingLevel.csv", index=False)
    with open(net / "netmet_results.json", "w") as fh:
        json.dump({}, fh)
    with open(root / "params.json", "w") as fh:
        json.dump({"custom_grp_order": ["WT", "KO"], "suite2p_mode": True}, fh)
    return root


def _stats_checks(tmp: Path) -> list[Check]:
    from meanap.stats.dataset import load_dataset
    from meanap.stats.figures import load_results, stats_figures
    from meanap.stats.run import StatsSettings, run_stats

    checks: list[Check] = []
    root = _make_multi_measure_run(tmp / "StatsRun")

    ds = load_dataset(root)
    checks.append(("the dataset sees a measure axis",
                   ds.activities == ["peaks", "denoised F"], f"{ds.activities}"))
    checks.append(("…and subsetting by measure halves the rows",
                   len(ds.for_activity("peaks").table) == len(ds.table) // 2,
                   f"{len(ds.for_activity('peaks').table)} of {len(ds.table)}"))

    settings = StatsSettings(
        correlation=False, regression=False, n_repeats=1, n_permutations=0,
        importance_repeats=1, per_age_decoding=False, shapley_by_age=False,
        feature_families=False, models=("lda",))
    logs: list[str] = []
    result = run_stats(root, dest=root / "5_StatsAndML", settings=settings,
                       log=logs.append)

    dest = root / "5_StatsAndML"
    checks.append(("each measure is analysed in a folder of its own",
                   (dest / "peaks" / "500mslag" / "comparisons.csv").exists()
                   and (dest / "denoisedF" / "500mslag" / "comparisons.csv").exists(),
                   f"{sorted(p.name for p in dest.iterdir())}"))

    folder = dest / "MeasureComparison" / "500mslag"
    for name in ("measure_agreement", "measure_differences", "measure_effects",
                 "measure_concordance", "measure_decoding"):
        checks.append((f"{name}.csv written",
                       (folder / f"{name}.csv").exists(), ""))

    agree = pd.read_csv(folder / "measure_agreement.csv")
    dens = agree[agree["Metric"] == "Dens"].iloc[0]
    checks.append(("a metric that only changes scale still ranks alike",
                   dens["Spearman"] > 0.9, f"rho={dens['Spearman']:.3f}"))
    checks.append(("…but its agreement coefficient sees the scale change",
                   dens["CCC"] < dens["Spearman"],
                   f"CCC={dens['CCC']:.3f} vs rho={dens['Spearman']:.3f}"))
    checks.append(("…and the Bland-Altman bias is reported in the metric's units",
                   np.isfinite(dens["Bias"]) and dens["LoALower"] < dens["Bias"]
                   < dens["LoAUpper"], f"{dens['Bias']}"))

    diffs = pd.read_csv(folder / "measure_differences.csv")
    dens_diff = diffs[diffs["Metric"] == "Dens"].iloc[0]
    checks.append(("the paired shift in a rescaled metric is detected",
                   dens_diff["PValueFDR"] < 0.05 and abs(dens_diff["HedgesG"]) > 0.5,
                   f"p={dens_diff['PValueFDR']:.3g} g={dens_diff['HedgesG']:.2f}"))

    conc = pd.read_csv(folder / "measure_concordance.csv")
    q_rows = conc[(conc["Metric"] == "Q")
                  & (conc["Term"].astype(str).str.contains("vs"))]
    checks.append(("a genotype effect present under one measure only is flagged",
                   len(q_rows) and q_rows.iloc[0]["Verdict"].startswith("disagree"),
                   f"{q_rows['Verdict'].tolist() if len(q_rows) else 'no rows'}"))
    dens_rows = conc[(conc["Metric"] == "Dens")
                     & (conc["Term"].astype(str).str.contains("vs"))]
    checks.append(("…while an effect found under both is called concordant",
                   len(dens_rows)
                   and dens_rows.iloc[0]["Verdict"] == "agree (both significant)",
                   f"{dens_rows['Verdict'].tolist() if len(dens_rows) else 'no rows'}"))

    text = "\n".join(logs)
    checks.append(("the log says how many conclusions moved",
                   "conclusions:" in text and "agree across" in text,
                   text[-400:]))
    checks.append(("the summary records the comparison",
                   "measures" in result.summary
                   and result.summary["measures"]["500mslag"]["n_pairs"] == 1,
                   f"{list(result.summary)}"))

    # The figures, through the same catalogue the viewer and the report use.
    stored = load_results(folder, ds.for_lag("500mslag"), lag="500mslag")
    keys = {f.key for f in stats_figures(stored)}
    checks.append(("the comparison's figures are catalogued",
                   {"measure_agreement", "measure_differences",
                    "measure_concordance"} <= keys, f"{sorted(keys)}"))
    drawn = {p.name for p in folder.glob("5F*.png")}
    checks.append(("…and drawn",
                   len(drawn) >= 3, f"{sorted(drawn)}"))
    checks.append(("nothing was skipped",
                   not result.skipped, f"{result.skipped[:3]}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP: several measures of activity in one run")
    print("=" * 70)

    tmp, raw, recordings = _dataset()
    total_pass = total = 0
    try:
        sections: list[tuple[str, list[Check]]] = []
        sections.append(("A — what goes where:", _layout_checks()))
        run_checks, two_root = _run_checks(tmp, raw, recordings)
        sections.append(("B — a two-measure run's output folder:", run_checks))
        sections.append(("C — the measures stay independent:",
                         _independence_checks(tmp, raw, recordings, two_root)))
        sections.append(("D — the statistics step compares them:",
                         _stats_checks(tmp)))
        for title, checks in sections:
            p, n = _report(title, checks)
            total_pass += p
            total += n
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 70)
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
