"""Test spike sorting as a step-1 alternative: units become the nodes.

Run from the repo root::

    uv run python python/test_spike_sorting.py

Needs the ``sorting`` extra (``uv sync --extra sorting``); without it the
sorter sections are reported as skipped, and the file-format and geometry
sections still run.

Sections:

- **Probe geometry** — every supported layout becomes a probe whose
  neighbours sit one pitch apart, and a channel the layout cannot place is
  left off rather than put somewhere.
- **File format** — a sorted ``_spikes.npz`` round-trips its unit arrays and
  reads back as sorted; a detected one reads back as not.
- **Curation** — labels follow the floors, and the violation fraction is a
  fraction of intervals.
- **Sorter on ground truth** — a short synthetic recording with known units
  is sorted and most units are recovered (a smoke-level floor; the full
  benchmark in ``benchmark_spike_sorting.py`` is what picks defaults).
- **Pipeline end to end** — steps 1–4 with ``spike_source="sort"`` on that
  recording: the spike file's nodes are units, several per electrode, the
  node-level CSVs carry a ``Unit`` column, the adjacency file carries node
  coordinates, and the network plots draw without an electrode lookup.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import scipy.io as sio  # noqa: E402

from meanap.params import SORTED_METHOD, Params, active_spike_method  # noqa: E402
from meanap.pipeline.io import load_spike_file, save_spike_times_npz  # noqa: E402
from meanap.pipeline.probes import (  # noqa: E402
    DEFAULT_PITCH_UM, build_probe, layout_coords_for_channels, layout_grid_step,
)
from meanap.pipeline.spike_sorting import (  # noqa: E402
    SpikeSortingParams, label_unit, rp_violation_fraction, sorting_available,
    unit_ring_coords,
)
from meanap.pipeline.channel_layout import get_coords_from_layout  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


# ── Probe geometry ────────────────────────────────────────────────────────────

def _probe_checks() -> list[Check]:
    checks: list[Check] = []
    for layout, pitch in DEFAULT_PITCH_UM.items():
        channels, _ = get_coords_from_layout(layout)
        probe, kept = build_probe(layout, channels)
        pos = probe.contact_positions
        d = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
        np.fill_diagonal(d, np.inf)
        nearest = d.min(axis=1)
        checks.append((f"{layout}: every channel on the probe",
                       len(kept) == len(channels), f"{len(kept)} of {len(channels)}"))
        checks.append((f"{layout}: nearest neighbour is one pitch ({pitch:g} µm)",
                       np.allclose(nearest, pitch, atol=1e-6),
                       f"{nearest.min():.1f}–{nearest.max():.1f}"))
        checks.append((f"{layout}: contact IDs are the channel IDs",
                       list(probe.contact_ids) == [str(int(c)) for c in channels], ""))

    # A full-grid file lists the four grounded corners MCS layouts drop.
    full = np.array([r * 10 + c for r in range(1, 9) for c in range(1, 9)])
    probe, kept = build_probe("MCS60", full)
    checks.append(("corner electrodes are left off the probe, not placed",
                   len(kept) == 60 and not any(full[kept] == 11), str(len(kept))))
    coords, known = layout_coords_for_channels("MCS60", full)
    checks.append(("unknown channels get NaN coordinates",
                   known.sum() == 60 and np.isnan(coords[~known]).all(), ""))
    checks.append(("custom pitch overrides the default",
                   abs(np.linalg.norm(np.diff(build_probe("MCS60", full, 123.0)[0]
                                              .contact_positions[:2], axis=0)) - 123.0) < 1e-6
                   or True, ""))  # spacing depends on order; the pitch is checked below
    p2, _ = build_probe("MCS60", full, 123.0)
    d2 = np.linalg.norm(p2.contact_positions[:, None] - p2.contact_positions[None], axis=-1)
    np.fill_diagonal(d2, np.inf)
    checks[-1] = ("custom pitch overrides the default",
                  np.allclose(d2.min(axis=1), 123.0), f"{d2.min():.1f}")

    step = layout_grid_step("MCS60")
    ring = unit_ring_coords(np.zeros((3, 2)), np.array([0, 0, 0]), step)
    checks.append(("three units on one electrode sit on a ring round it",
                   np.allclose(np.linalg.norm(ring, axis=1), 0.22 * step)
                   and len({tuple(np.round(r, 6)) for r in ring}) == 3, str(ring)))
    checks.append(("a lone unit stays on its electrode",
                   np.allclose(unit_ring_coords(np.ones((1, 2)), np.array([4]), step), 1.0), ""))
    return checks


# ── File format ───────────────────────────────────────────────────────────────

def _format_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rec_spikes.npz"
        spike_times = {0: {SORTED_METHOD: np.array([0.1, 0.5])},
                       1: {SORTED_METHOD: np.array([0.2])},
                       2: {SORTED_METHOD: np.array([0.3, 0.4, 0.9])}}
        units = {"id": np.array(["25-1", "25-2", "36-1"]),
                 "channel_index": np.array([3, 3, 7]),
                 "coords": np.array([[1.0, 2.0], [1.2, 2.0], [4.0, 4.0]]),
                 "label": np.array(["good", "mua", "good"]),
                 "snr": np.array([6.0, 4.5, 9.0])}
        save_spike_times_npz(path, spike_times, np.array([25, 25, 36]), 25000.0,
                             duration_s=1.0, units=units)
        sf = load_spike_file(path)
        checks.append(("a sorted file reads back as sorted", sf.sorted, ""))
        checks.append(("unit arrays round-trip",
                       list(sf.units["id"]) == ["25-1", "25-2", "36-1"]
                       and np.allclose(sf.units["coords"], units["coords"])
                       and list(sf.units["label"]) == ["good", "mua", "good"], str(sf.units.keys())))
        checks.append(("channels are the parent electrodes, repeated",
                       list(sf.channels) == [25, 25, 36], str(sf.channels)))
        checks.append(("spike trains are under the sorted method",
                       sf.methods == [SORTED_METHOD] and len(sf.spike_times[2][SORTED_METHOD]) == 3, ""))
        raw = np.load(path)
        checks.append(("unit arrays are stored under a unit_ prefix",
                       "unit_id" in raw.files and "unit_coords" in raw.files, str(raw.files)))

        det = Path(tmp) / "det_spikes.npz"
        save_spike_times_npz(det, {0: {"thr4": np.array([0.1])}}, np.array([25]), 25000.0)
        checks.append(("a detected file reads back as not sorted",
                       not load_spike_file(det).sorted, ""))

    checks.append(("active_spike_method is 'sorted' only when sorting",
                   active_spike_method(Params(spike_source="sort")) == SORTED_METHOD
                   and active_spike_method(Params(spikes_method="thr4")) == "thr4", ""))
    return checks


# ── Curation ──────────────────────────────────────────────────────────────────

def _curation_checks() -> list[Check]:
    checks: list[Check] = []
    p = SpikeSortingParams()
    checks.append(("violation fraction is over intervals",
                   abs(rp_violation_fraction(np.array([0.0, 0.001, 0.010, 0.030]), 1.5) - 1 / 3) < 1e-9, ""))
    checks.append(("fewer than two spikes: no violations",
                   rp_violation_fraction(np.array([0.5]), 1.5) == 0.0, ""))
    checks.append(("good: clears every floor", label_unit(6.0, 0.01, 1.0, p) == "good", ""))
    checks.append(("mua: real but contaminated", label_unit(6.0, 0.20, 1.0, p) == "mua", ""))
    checks.append(("noise: below SNR floor", label_unit(2.0, 0.0, 1.0, p) == "noise", ""))
    checks.append(("noise: too few spikes", label_unit(9.0, 0.0, 0.01, p) == "noise", ""))
    checks.append(("noise: SNR not a number", label_unit(float("nan"), 0.0, 1.0, p) == "noise", ""))
    return checks


# ── Sorter on ground truth ────────────────────────────────────────────────────

def _make_gt(duration_s: float, seed: int = 0):
    from meanap.pipeline.sorting_benchmark import GroundTruthSpec, make_ground_truth
    spec = GroundTruthSpec(duration_s=duration_s, seed=seed, n_active_electrodes=16,
                           noise_uv=4.0)
    return make_ground_truth(spec)


def _sorter_checks() -> list[Check]:
    checks: list[Check] = []
    from meanap.pipeline.sorting_benchmark import score_against_ground_truth
    from meanap.pipeline.spike_sorting import sort_spikes_recording
    import spikeinterface.full as si

    dat, channels, fs, gt, info = _make_gt(40.0)
    with tempfile.TemporaryDirectory() as tmp:
        params = SpikeSortingParams(sorter_name=Params().sorter_name, n_jobs=4, seed=0)
        result = sort_spikes_recording(dat, channels, fs, params, Path(tmp) / "work")
        checks.append(("the sorter's scratch folder is removed afterwards",
                       not (Path(tmp) / "work").exists(), ""))
    n_units = len(result.channels)
    checks.append((f"units came back ({n_units} for {info['n_units']} simulated)",
                   n_units >= 0.6 * info["n_units"], str(n_units)))
    checks.append(("every unit sits on an electrode of the recording",
                   set(result.channels).issubset(set(channels.tolist())), ""))
    checks.append(("units are numbered by electrode and rank",
                   all(uid.split("-")[0] == str(ch)
                       for uid, ch in zip(result.units["id"], result.channels)), ""))
    checks.append(("unit arrays and trains agree on the count",
                   len(result.units["label"]) == n_units == len(result.spike_times), ""))
    checks.append(("every unit has a template and example waveforms",
                   result.templates.shape[0] == n_units
                   and all(result.waveforms[i][SORTED_METHOD].ndim == 2 for i in range(n_units)), ""))
    checks.append(("a multi-unit electrode gives more than one node",
                   len(np.unique(result.channels)) < n_units, ""))
    trains = {u: (result.spike_times[i][SORTED_METHOD] * fs).astype(np.int64)
              for i, u in enumerate(result.units["id"])}
    score = score_against_ground_truth(gt, si.NumpySorting.from_unit_dict(trains, fs), fs)
    checks.append((f"most simulated neurons are recovered ({score['n_found']}/{score['n_gt']})",
                   score["n_found"] >= 0.6 * score["n_gt"], ""))
    checks.append((f"few nodes are not neurons (false positives {score['n_false_positive']})",
                   score["n_false_positive"] <= max(2, 0.15 * n_units), ""))
    return checks


# ── Pipeline end to end ───────────────────────────────────────────────────────

def _pipeline_checks() -> list[Check]:
    from meanap.pipeline.runner import run_pipeline

    checks: list[Check] = []
    dat, channels, fs, gt, info = _make_gt(40.0, seed=1)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "raw"
        raw.mkdir()
        # MATLAB's ``dat`` is samples × channels, which is ``dat`` as generated.
        sio.savemat(raw / "sim_DIV21.mat", {"dat": dat.astype(np.float32),
                                            "channels": channels.astype(float),
                                            "fs": float(fs)})
        pd.DataFrame([{"Recording Filename": "sim_DIV21", "DIV group": 21,
                       "Genotype": "WT"}]).to_csv(tmp / "recs.csv", index=False)
        params = Params(
            raw_data=str(raw), output_data_folder=str(tmp), output_data_folder_name="Sorted",
            spreadsheet_file_name=str(tmp / "recs.csv"), spreadsheet_range="2:100",
            start_analysis_step=1, stop_analysis_step=4, channel_layout="MCS60",
            spike_source="sort", func_con_lag_val=[10], prob_thresh_rep_num=20,
            min_number_of_nodes_to_cal_net_met=2, random_seed=3,
            spike_detection_channel_workers=4, recording_workers=1,
            compute_nmf=False, compute_eff_rank=False,
        )
        root = run_pipeline(params, log=lambda m: None)

        spike_path = root / "1_SpikeDetection" / "1A_SpikeDetectedData" / "sim_DIV21_spikes.npz"
        sf = load_spike_file(spike_path)
        n_units = len(sf.channels)
        checks.append(("step 1 wrote a sorted spike file", sf.sorted and n_units > 0, str(spike_path)))
        checks.append(("its nodes are units, several per electrode",
                       len(np.unique(sf.channels)) < n_units, f"{n_units} units"))
        checks.append(("the sorter's scratch folder is gone",
                       not (spike_path.parent / "sorting").exists(), ""))
        check_dir = root / "1_SpikeDetection" / "1B_SpikeDetectionChecks" / "WT" / "sim_DIV21"
        checks.append(("sorting checks: unit table and three figures",
                       (check_dir / "units.csv").exists()
                       and all((check_dir / f).exists() for f in
                               ("1_UnitsPerElectrode.png", "2_UnitTemplates.png", "3_UnitQuality.png")),
                       str(sorted(p.name for p in check_dir.iterdir()) if check_dir.exists() else "missing")))
        table = pd.read_csv(check_dir / "units.csv")
        checks.append(("the unit table lists every returned unit with a label",
                       len(table) >= n_units and set(table.label) <= {"good", "mua", "noise"}
                       and table.kept.sum() == n_units, str(len(table))))

        node_csv = pd.read_csv(root / "2_NeuronalActivity" / "NeuronalActivity_NodeLevel.csv")
        checks.append(("step 2 node-level CSV has one row per unit with a Unit column",
                       len(node_csv) == n_units and "Unit" in node_csv
                       and list(node_csv.Unit) == list(sf.units["id"]), str(node_csv.columns.tolist())))
        checks.append(("step 2 heatmaps drew (units pooled per electrode)",
                       (root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / "WT"
                        / "sim_DIV21" / "2_Heatmap.png").exists(), ""))

        adj = np.load(root / "ExperimentMatFiles" / "sim_DIV21_adjM.npz")
        checks.append(("step 3 carried the unit coordinates into the adjacency file",
                       "coords" in adj.files and adj["coords"].shape == (n_units, 2)
                       and adj["adjM10mslag"].shape == (n_units, n_units), str(adj.files)))

        net_csv = pd.read_csv(root / "4_NetworkActivity" / "NetworkActivity_NodeLevel.csv")
        checks.append(("step 4 node-level CSV names the units",
                       "Unit" in net_csv and net_csv.Unit.isin(sf.units["id"]).all(), ""))
        plots = list((root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis").rglob("*.png"))
        checks.append(("step 4 drew the network plots from the unit coordinates",
                       len(plots) > 0, str(len(plots))))

        # Distinct units on one electrode must not be perfectly correlated —
        # otherwise sorting split by amplitude, not by neuron.
        a = adj["adjM10mslag_raw"]
        same = [(i, j) for i in range(n_units) for j in range(i + 1, n_units)
                if sf.channels[i] == sf.channels[j]]
        if same:
            vals = np.array([a[i, j] for i, j in same])
            checks.append((f"units sharing an electrode are not perfectly correlated "
                           f"(max STTC {np.nanmax(vals):.2f})", np.nanmax(vals) < 0.95, ""))
    return checks


def main() -> int:
    passed = total = 0
    sections = [("Probe geometry", _probe_checks),
                ("File format", _format_checks),
                ("Curation", _curation_checks)]
    if sorting_available():
        sections += [("Sorter on ground truth", _sorter_checks),
                     ("Pipeline end to end", _pipeline_checks)]
    else:
        print("\n(SpikeInterface not installed — sorter sections skipped; "
              "run `uv sync --extra sorting`)")
    for title, build in sections:
        p, n = _report(title, build())
        passed += p
        total += n
    print(f"\n{'=' * 70}\nTotal: {passed}/{total} checks passed\n{'=' * 70}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
