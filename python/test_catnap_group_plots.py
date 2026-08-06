"""Test the CAT-NAP batch (group × age) comparison figures.

Run from the repo root::

    uv run python python/test_catnap_group_plots.py

These are the figures the ephys pipeline draws at the end of steps 2 and 4
(``2B_``/``4B_GroupComparisons``) and that the CAT-NAP path was missing. There
is no MATLAB ground truth to compare against numerically — MATLAB's suite2p
branch calls the same ``PlotEphysStats``/``PlotNetMet`` routines the ephys
branch does — so these are structural checks:

  - the pooled frames carry every recording, every unit, and the real suite2p
    ROI ids, with the 2P-specific metrics dropped rather than faked when the
    activity type never produced them;
  - each figure family writes the expected file names into the expected
    folders, matching the ephys layout;
  - a CAT-NAP results dict feeds the *shared* step-4 comparison plotter
    unchanged;
  - cell-type group names that are not filename-safe (``NeuN+ & ~GAD+``) still
    produce one file per (metric, cell type) per lag.

Section A runs on synthetic data and always executes. Section B runs the real
example dataset in the gitignored ``local/`` folder through the two CAT-NAP
plotters and **skips gracefully** when it is absent.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap import group_plots as gp  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

DATASET_DIR = REPO_ROOT / "local" / "example2pdataWCellTypes"
RECORDING = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"
SUITE2P_DIR = DATASET_DIR / RECORDING / "suite2p" / "plane0"

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── Synthetic fixtures ────────────────────────────────────────────────────────

N_UNITS = 12
LAGS = ["1000mslag", "2500mslag"]


def _recordings() -> list[RecordingInfo]:
    """Two groups × two ages × two replicates — the smallest batch that gives
    every comparison axis something to separate."""
    return [
        RecordingInfo(filename=f"rec_{grp}_{div}_{rep}", div=float(div), group=grp)
        for grp in ("WT", "KO")
        for div in (14, 21)
        for rep in (1, 2)
    ]


def _stats(seed: int, peaks: bool = True) -> dict:
    """A ``calc_twop_activity_stats``-shaped dict.

    ``peaks=False`` mimics an ``F``/``spks`` run, where the routine returns
    ``None`` for every 2P-specific field because ``activityProperties`` only
    exists on the peaks path.
    """
    rng = np.random.default_rng(seed)
    fr = rng.uniform(0.01, 0.3, N_UNITS)
    active = fr >= 0.05
    fr_active = np.where(active, fr, np.nan)
    stats = {
        "FR": fr,
        "FRactive": fr_active,
        "FRmean": float(np.nanmean(fr_active)),
        "FRmedian": float(np.nanmedian(fr_active)),
        "FRiqr": float(np.subtract(*np.nanpercentile(fr_active, [75, 25]))),
        "FRstd": float(np.nanstd(fr_active)),
        "numActiveElec": int(active.sum()),
        "ISI": rng.uniform(3, 40, N_UNITS),
        "ISImean": float(rng.uniform(3, 40)),
    }
    twop = {
        "unitHeightMean": rng.uniform(0.01, 0.5, N_UNITS),
        "unitPeakDurMean": rng.uniform(0.5, 4.0, N_UNITS),
        "unitEventAreaMean": rng.uniform(0.05, 2.0, N_UNITS),
        "unitEventAreaSum": rng.uniform(0.5, 20.0, N_UNITS),
        "recHeightMean": float(rng.uniform(0.01, 0.5)),
        "recPeakDurMean": float(rng.uniform(0.5, 4.0)),
        "recEventAreaMean": float(rng.uniform(0.05, 2.0)),
    }
    stats.update(twop if peaks else {k: None for k in twop})
    return stats


def _netmet(seed: int) -> dict:
    """A step-4 ``compute_network_metrics``-shaped dict (the subset the shared
    comparison plotter reads)."""
    rng = np.random.default_rng(seed)
    return {
        "aN": N_UNITS,
        "activeChannelIndex": np.arange(N_UNITS),
        "Dens": float(rng.uniform(0.1, 0.6)),
        "Eglob": float(rng.uniform(0.1, 0.9)),
        "Q": float(rng.uniform(0.1, 0.8)),
        "nMod": int(rng.integers(2, 6)),
        "SW": float(rng.uniform(0.5, 3.0)),
        "NDmean": float(rng.uniform(1, 8)),
        "ND": rng.uniform(0, 10, N_UNITS),
        "NS": rng.uniform(0, 5, N_UNITS),
        "MEW": rng.uniform(0, 1, N_UNITS),
        "Eloc": rng.uniform(0, 1, N_UNITS),
        "BC": rng.uniform(0, 1, N_UNITS),
        "PC": rng.uniform(0, 1, N_UNITS),
        "adjMsub": rng.uniform(0, 1, (N_UNITS, N_UNITS)),
    }


def _subnetwork_rows(recordings: list[RecordingInfo]) -> tuple[list[dict], list[dict]]:
    """Rows shaped like the runner's ``Subnetwork_RecordingLevel`` /
    ``Subnetwork_NodeLevel`` tables, including a cell-type name that is not
    filename-safe."""
    cell_types = ["Whole network", "NeuN+ & ~GAD+", "GAD+ | PV+"]
    summary, node = [], []
    for i, rec in enumerate(recordings):
        for lag in LAGS:
            base = {"FileName": rec.filename, "Grp": rec.group,
                    "DIV": rec.div, "Lag": lag}
            rng = np.random.default_rng(i)
            for ct in cell_types:
                summary.append(dict(base, Group=ct, aN=N_UNITS,
                                    Dens=float(rng.uniform(0.1, 0.6)),
                                    Eglob=float(rng.uniform(0.1, 0.9)),
                                    Q=float(rng.uniform(0.1, 0.8))))
                for n in range(4):
                    node.append(dict(base, Group=ct, Channel=n + 1,
                                     ND=float(rng.uniform(0, 10)),
                                     PC=float(rng.uniform(0, 1)),
                                     WithinGroupStrengthFrac=float(rng.uniform(0, 1))))
    return summary, node


# ── Section A1 — pooled frames ────────────────────────────────────────────────

def _frame_checks() -> list[Check]:
    checks: list[Check] = []
    recordings = _recordings()
    stats = {r.filename: _stats(i) for i, r in enumerate(recordings)}
    # Distinct, non-contiguous ROI ids: the whole point of Channel is that it
    # is the suite2p ROI number, not the node's position.
    channels = {r.filename: np.arange(N_UNITS) * 3 + 5 for r in recordings}

    df_rec, df_node = gp.twop_stats_frames(recordings, stats, channels)

    checks.append(("recording frame has one row per recording",
                   len(df_rec) == len(recordings), f"{len(df_rec)}"))
    checks.append(("node frame has one row per unit per recording",
                   len(df_node) == len(recordings) * N_UNITS, f"{len(df_node)}"))

    expected_rec = set(gp.TWOP_REC_METRICS) | {"FileName", "Grp", "DIV"}
    checks.append(("recording frame columns are the labelled metrics",
                   set(df_rec.columns) == expected_rec,
                   f"{sorted(set(df_rec.columns) ^ expected_rec)}"))

    expected_node = set(gp.TWOP_NODE_METRICS) | {"FileName", "Grp", "DIV", "Channel"}
    checks.append(("node frame columns are the labelled metrics",
                   set(df_node.columns) == expected_node,
                   f"{sorted(set(df_node.columns) ^ expected_node)}"))

    first = df_node[df_node["FileName"] == recordings[0].filename]
    checks.append(("Channel holds the suite2p ROI ids, not node positions",
                   np.array_equal(first["Channel"].to_numpy(), channels[recordings[0].filename]),
                   f"{first['Channel'].to_numpy()[:4]}"))
    checks.append(("per-unit values survive pooling unchanged",
                   np.allclose(first["FR"].to_numpy(), stats[recordings[0].filename]["FR"]),
                   ""))
    checks.append(("FRactive keeps its NaNs (inactive units)",
                   int(first["FRactive"].isna().sum())
                   == int(np.isnan(stats[recordings[0].filename]["FRactive"]).sum()), ""))
    checks.append(("DIV is stringified for the plotter",
                   df_rec["DIV"].map(type).eq(str).all(), ""))
    checks.append(("both experimental groups and both ages are represented",
                   set(df_rec["Grp"]) == {"WT", "KO"} and set(df_rec["DIV"]) == {"14.0", "21.0"},
                   f"{sorted(set(df_rec['Grp']))} {sorted(set(df_rec['DIV']))}"))

    # Non-peaks activity type: 2P-specific fields are None, not arrays.
    stats_f = {r.filename: _stats(i, peaks=False) for i, r in enumerate(recordings)}
    df_rec_f, df_node_f = gp.twop_stats_frames(recordings, stats_f, channels)
    checks.append(("None-valued 2P fields are dropped, not coerced (node)",
                   "unitHeightMean" not in df_node_f.columns and "FR" in df_node_f.columns,
                   f"{sorted(df_node_f.columns)}"))
    checks.append(("None-valued 2P fields are dropped, not coerced (recording)",
                   "recHeightMean" not in df_rec_f.columns and "FRmean" in df_rec_f.columns,
                   f"{sorted(df_rec_f.columns)}"))

    # A recording with no stats entry is skipped rather than emitting an empty row.
    partial = {recordings[0].filename: stats[recordings[0].filename]}
    df_rec_p, _ = gp.twop_stats_frames(recordings, partial, channels)
    checks.append(("recordings without stats are skipped", len(df_rec_p) == 1, f"{len(df_rec_p)}"))

    checks.append(("empty input yields empty frames, not an error",
                   all(df.empty for df in gp.twop_stats_frames([], {}, None)), ""))
    return checks


# ── Section A2 — figure families ──────────────────────────────────────────────

def _pngs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.png") if p.stat().st_size > 0)


def _figure_checks() -> list[Check]:
    from meanap.pipeline.plotting_step4 import plot_step4_group_comparisons

    checks: list[Check] = []
    recordings = _recordings()
    stats = {r.filename: _stats(i) for i, r in enumerate(recordings)}
    channels = {r.filename: np.arange(N_UNITS) + 1 for r in recordings}
    results = {r.filename: {lag: _netmet(i * 10 + j) for j, lag in enumerate(LAGS)}
               for i, r in enumerate(recordings)}
    summary, node = _subnetwork_rows(recordings)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        twop_dir = root / "2_NeuronalActivity"
        net_dir = root / "4_NetworkActivity"

        gp.plot_twop_group_comparisons(recordings, stats, twop_dir,
                                       custom_grp_order=["WT", "KO"],
                                       channels_by_rec=channels)

        base = twop_dir / "2B_GroupComparisons"
        expected_dirs = {
            base / "3_RecordingsByGroup" / "HalfViolinPlots": "FRmean_byGroup.png",
            base / "4_RecordingsByAge" / "HalfViolinPlots": "FRmean_byDIV.png",
            base / "1_NodeByGroup": "FR_byGroup_node.png",
            base / "2_NodeByAge": "FR_byDIV_node.png",
        }
        for directory, sample in expected_dirs.items():
            checks.append((f"2P activity: {directory.name}/{sample}",
                           (directory / sample).exists()
                           and (directory / sample).stat().st_size > 0, ""))

        n_twop = len(_pngs(base))
        expected_twop = 2 * len(gp.TWOP_REC_METRICS) + 2 * len(gp.TWOP_NODE_METRICS)
        checks.append(("2P activity: one figure per metric per axis",
                       n_twop == expected_twop, f"{n_twop} vs {expected_twop}"))

        # The shared step-4 plotter, fed a CAT-NAP results dict unchanged.
        plot_step4_group_comparisons(recordings, results, net_dir, ["WT", "KO"])
        net_base = net_dir / "4B_GroupComparisons"
        for rel in ("3_RecordingsByGroup/HalfViolinPlots/Lag1000ms/Dens_byGroup.png",
                    "4_RecordingsByAge/HalfViolinPlots/Lag2500ms/Dens_byDIV.png",
                    "1_NodeByGroup/Lag1000ms/ND_byGroup_node.png",
                    "2_NodeByAge/Lag2500ms/ND_byDIV_node.png"):
            checks.append((f"network: {rel}", (net_base / rel).exists(), ""))
        checks.append(("network: per-lag folders for every lag",
                       {p.name for p in (net_base / "1_NodeByGroup").iterdir()}
                       == {"Lag1000ms", "Lag2500ms"}, ""))

        # Cell-type subnetworks.
        gp.plot_subnetwork_group_comparisons(summary, node, net_dir, ["WT", "KO"])
        ct_base = net_base / "8_CellTypeSubnetworks"
        checks.append(("subnetworks: one folder per lag",
                       {p.name for p in ct_base.iterdir()} == {"Lag1000ms", "Lag2500ms"},
                       f"{[p.name for p in ct_base.iterdir()]}"))

        lag_dir = ct_base / "Lag1000ms"
        checks.append(("subnetworks: recording and node folders",
                       {p.name for p in lag_dir.iterdir()}
                       == {"RecordingsByGroup", "RecordingsByAge",
                           "NodeByGroup", "NodeByAge"},
                       f"{[p.name for p in lag_dir.iterdir()]}"))

        rec_group = lag_dir / "RecordingsByGroup"
        names = {p.name for p in rec_group.glob("*.png")}
        checks.append(("subnetworks: whole-network reference sits beside each cell type",
                       "Dens_Whole_network_byGroup.png" in names, f"{sorted(names)}"))
        checks.append(("subnetworks: unsafe cell-type names are sanitised",
                       "Dens_NeuN+_GAD+_byGroup.png" in names, f"{sorted(names)}"))
        checks.append(("subnetworks: one file per (metric, cell type)",
                       len(names) == 3 * 3, f"{len(names)}"))  # Dens/Eglob/Q × 3 types

        node_group = lag_dir / "NodeByGroup"
        node_names = {p.name for p in node_group.glob("*.png")}
        checks.append(("subnetworks: node metrics include the within-group fraction",
                       "WithinGroupStrengthFrac_GAD+_PV+_byGroup_node.png" in node_names,
                       f"{sorted(node_names)}"))

        checks.append(("every figure written is a non-empty PNG",
                       len(_pngs(root)) == len(list(root.rglob("*.png"))), ""))

    return checks


# ── Section A3 — degenerate inputs ────────────────────────────────────────────

def _robustness_checks() -> list[Check]:
    checks: list[Check] = []
    recordings = _recordings()[:1]  # single recording, one group, one age
    stats = {recordings[0].filename: _stats(0)}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            gp.plot_twop_group_comparisons(recordings, stats, root / "2_NeuronalActivity")
            ok, detail = len(_pngs(root)) > 0, ""
        except Exception as e:  # noqa: BLE001 — the check is that it doesn't raise
            ok, detail = False, str(e)
        checks.append(("a single-recording batch still plots", ok, detail))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            gp.plot_twop_group_comparisons([], {}, root / "2_NeuronalActivity")
            gp.plot_subnetwork_group_comparisons([], [], root / "4_NetworkActivity")
            ok, detail = len(list(root.rglob("*.png"))) == 0, ""
        except Exception as e:  # noqa: BLE001
            ok, detail = False, str(e)
        checks.append(("empty batch writes nothing and does not raise", ok, detail))

    # A metric that is all-NaN across the batch (e.g. ISI on a run with no
    # multi-event cells) must not produce a subnetwork figure with no data.
    summary = [{"FileName": "a", "Grp": "WT", "DIV": 14.0, "Lag": "1000mslag",
                "Group": "Excitatory", "Dens": 0.4, "Q": float("nan")}]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gp.plot_subnetwork_group_comparisons(summary, [], root)
        made = {p.name for p in root.rglob("*.png")}
        checks.append(("all-NaN subnetwork metrics are skipped",
                       made == {"Dens_Excitatory_byGroup.png", "Dens_Excitatory_byDIV.png"},
                       f"{sorted(made)}"))

    checks.append(("filename sanitiser keeps markers readable",
                   gp._safe_name("NeuN+ & ~GAD+") == "NeuN+_GAD+"
                   and gp._safe_name("E/I") == "E_I",
                   f"{gp._safe_name('NeuN+ & ~GAD+')!r} {gp._safe_name('E/I')!r}"))
    checks.append(("lag folder naming matches the ephys layout",
                   gp._lag_folder("1000mslag") == "Lag1000ms"
                   and gp._lag_folder(1000) == "Lag1000ms",
                   f"{gp._lag_folder('1000mslag')!r} {gp._lag_folder(1000)!r}"))
    return checks


# ── Section A4 — runner tail ──────────────────────────────────────────────────

def _runner_tail_checks() -> list[Check]:
    """Drive the runner's save + plot tail with exactly the structures
    ``run_catnap_pipeline`` holds in memory.

    A full CAT-NAP run takes tens of minutes (probabilistic thresholding + null
    models), so this exercises the wiring — the pieces that break when a
    signature or a folder name drifts — without recomputing any of it.
    """
    from meanap.catnap.pipeline import _plot_group_comparisons, _save_catnap_results
    from meanap.catnap.store import RecordingState
    from meanap.catnap.subnetwork import CellTypeGroups
    from meanap.params import Params
    from meanap.pipeline.output_folders import create_output_folders

    checks: list[Check] = []
    recordings = _recordings()
    stats = {r.filename: _stats(i) for i, r in enumerate(recordings)}
    channels = {r.filename: np.arange(N_UNITS) * 2 + 1 for r in recordings}
    results = {r.filename: {lag: _netmet(i) for lag in LAGS}
               for i, r in enumerate(recordings)}
    summary, node = _subnetwork_rows(recordings)
    tables = {"summary": summary, "node": node, "mix": []}
    params = Params(custom_grp_order=["WT", "KO"])

    # Per-recording state carrying cell-type groups, so the tail's
    # by-cell-type activity comparisons run too rather than silently skipping.
    exc = np.zeros(N_UNITS, bool)
    exc[: N_UNITS // 2] = True
    masks = np.column_stack([exc, ~exc])
    states = {
        r.filename: RecordingState(
            adjMs={}, coords=np.zeros((N_UNITS, 2)), channels=channels[r.filename],
            spike_counts=np.ones(N_UNITS), duration_s=600.0, plane0=Path("."),
            groups=CellTypeGroups(["Excitatory", "Inhibitory"], masks,
                                  ["NeuN+", "GAD+"], masks),
        )
        for r in recordings
    }

    with tempfile.TemporaryDirectory() as tmp:
        root = create_output_folders(tmp, "OutputTest", ["WT", "KO"])
        logs: list[str] = []

        _save_catnap_results(recordings, results, stats, channels,
                             root / "4_NetworkActivity", logs.append)
        _plot_group_comparisons(params, recordings, results, stats, channels,
                                tables, states, root, logs.append)

        warnings = [line for line in logs if "Warning" in line]
        checks.append(("runner tail logs no warnings", not warnings, "; ".join(warnings)))

        twop = root / "2_NeuronalActivity"
        node_csv = twop / "TwoPhotonActivity_NodeLevel.csv"
        checks.append(("per-unit activity stats reach a CSV", node_csv.exists(), ""))
        if node_csv.exists():
            df = pd.read_csv(node_csv)
            checks.append(("node CSV has a row per unit per recording",
                           len(df) == len(recordings) * N_UNITS, f"{len(df)}"))
            checks.append(("node CSV carries the ROI ids",
                           df["Channel"].iloc[:3].tolist() == [1, 3, 5],
                           f"{df['Channel'].iloc[:3].tolist()}"))
        checks.append(("recording-level activity CSV still written",
                       (twop / "TwoPhotonActivity_RecordingLevel.csv").exists(), ""))
        checks.append(("cell-type composition CSV written",
                       (twop / "CellTypeComposition.csv").exists(), ""))

        for label, rel in (
            ("two-photon activity", "2_NeuronalActivity/2B_GroupComparisons/"
                                    "3_RecordingsByGroup/HalfViolinPlots/FRmean_byGroup.png"),
            ("activity split by cell type", "2_NeuronalActivity/2B_GroupComparisons/"
                                            "1_NodeByGroup/ByCellType/FR_byGroup_node.png"),
            ("cell-type composition", "2_NeuronalActivity/2B_GroupComparisons/"
                                      "5_CellTypeComposition/nCells_byGroup.png"),
            ("network metrics", "4_NetworkActivity/4B_GroupComparisons/"
                                "3_RecordingsByGroup/HalfViolinPlots/Lag1000ms/Dens_byGroup.png"),
            ("cell-type subnetworks", "4_NetworkActivity/4B_GroupComparisons/"
                                      "8_CellTypeSubnetworks/Lag1000ms/RecordingsByGroup/"
                                      "Dens_Whole_network_byGroup.png"),
        ):
            checks.append((f"runner writes {label} comparisons", (root / rel).exists(), rel))

        # Subnetwork figures must not be attempted when the analysis was off.
        with tempfile.TemporaryDirectory() as tmp2:
            root2 = create_output_folders(tmp2, "OutputTest", ["WT", "KO"])
            logs2: list[str] = []
            _plot_group_comparisons(params, recordings, results, stats, channels,
                                    {"summary": [], "node": [], "mix": []}, states,
                                    root2, logs2.append)
            made = (root2 / "4_NetworkActivity" / "4B_GroupComparisons"
                    / "8_CellTypeSubnetworks").exists()
            checks.append(("no subnetwork folder when the analysis is off", not made, ""))

    return checks


# ── Section B — real dataset ──────────────────────────────────────────────────

def _dataset_checks() -> list[Check]:
    """Run the real recording's stats through the pooling + plotting path.

    One recording is not a batch, so this checks plumbing (real suite2p ROI
    ids, real stat values, figures actually rendering) rather than group
    separation.
    """
    from meanap.catnap.adjacency import suite2p_to_adjm
    from meanap.catnap.loader import load_suite2p
    from meanap.catnap.stats import calc_twop_activity_stats

    checks: list[Check] = []
    data = load_suite2p(SUITE2P_DIR)
    res = suite2p_to_adjm(data, "peaks", [1000], remove_nodes_with_no_peaks=True,
                          rng=np.random.default_rng(0))
    ap = res.activity_properties
    stats = calc_twop_activity_stats(
        "peaks", duration_s=res.F.shape[0] / res.fs, fs=res.fs,
        min_activity_level=0.01, spike_times=res.spike_times,
        peak_heights=ap.get("peakHeights"),
        peak_duration_frames=ap.get("peakDurationFrames"),
        event_areas=ap.get("eventAreas"),
    )

    rec = RecordingInfo(filename=RECORDING, div=21.0, group="HET")
    df_rec, df_node = gp.twop_stats_frames([rec], {RECORDING: stats},
                                           {RECORDING: res.channels})

    checks.append(("node frame covers every retained cell",
                   len(df_node) == len(res.channels), f"{len(df_node)} vs {len(res.channels)}"))
    checks.append(("Channel column matches the recording's ROI ids",
                   np.array_equal(df_node["Channel"].to_numpy(), res.channels), ""))
    checks.append(("event rates are finite and positive",
                   bool(np.all(np.isfinite(df_node["FR"])) and (df_node["FR"] > 0).all()), ""))
    checks.append(("recording-level active-cell count matches the stats dict",
                   int(df_rec["numActiveElec"].iloc[0]) == int(stats["numActiveElec"]), ""))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gp.plot_twop_group_comparisons([rec], {RECORDING: stats},
                                       root / "2_NeuronalActivity",
                                       channels_by_rec={RECORDING: res.channels})
        made = _pngs(root)
        checks.append(("real-data figures render",
                       len(made) == 2 * len(gp.TWOP_REC_METRICS) + 2 * len(gp.TWOP_NODE_METRICS),
                       f"{len(made)}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP group / DIV comparison plots")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A1 — pooled two-photon activity frames:", _frame_checks),
        ("Section A2 — figure families and folder layout:", _figure_checks),
        ("Section A3 — degenerate inputs:", _robustness_checks),
        ("Section A4 — runner save + plot tail:", _runner_tail_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    if SUITE2P_DIR.exists():
        p, n = _report("Section B — real example dataset:", _dataset_checks())
        total_pass += p
        total += n
    else:
        print(f"\nSection B — SKIPPED (dataset not found at {DATASET_DIR})")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
