"""Test switching step 4's dimensionality metrics off.

Run from the repo root::

    uv run python python/test_step4_optional_metrics.py

NMF and effective rank are, between them, most of what step 4 computes on an
ephys batch — measured on the benchmark dataset (two 64-channel 10-minute
recordings, three lags): 63s of 70s, against 6.6s for every network metric
beside them. ``Params.compute_nmf`` / ``compute_eff_rank`` switch them off,
the way ``ExtractNetMet.m`` skips a metric that is not in ``netMetToCal``.

What this checks:
  - by default both are computed, so nothing about an existing run changes;
  - switched off, their fields are *absent* rather than NaN — NaN is what a
    failed computation writes, and the two must stay distinguishable;
  - the expensive call is genuinely not made, not merely discarded;
  - **every other metric is bit-for-bit what it was**. That is the whole
    claim: a metric you switch off must not move the metrics you kept, which
    is why NMF draws from its own RNG stream rather than the one the network
    metrics use;
  - the recording-level CSV loses exactly those columns and keeps the rest.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from meanap.params import Params  # noqa: E402
from meanap.pipeline import step4  # noqa: E402
from meanap.pipeline.atomic import atomic_savez  # noqa: E402
from meanap.pipeline.io import save_spike_times_npz  # noqa: E402
from meanap.pipeline.output_folders import create_output_folders  # noqa: E402
from meanap.pipeline.runner import run_pipeline  # noqa: E402

Check = tuple[str, bool, str]

RECS = ["rec_A", "rec_B"]
N_CH = 12
FS = 12500.0
LAG = 25

#: What ``cal_nmf`` contributes to a recording's metrics.
NMF_FIELDS = ("num_nnmf_components", "nComponentsRelNS", "nnmf_residuals",
              "nnmf_var_explained", "randResidualPerComponent")


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _seed_inputs(root: Path) -> None:
    """Spike times and an adjacency matrix — the two things step 4 reads."""
    for i, rec in enumerate(RECS):
        rng = np.random.default_rng(i)
        spikes = {ch: {"bior1p5": np.sort(rng.uniform(0, 60, 60 + ch))}
                  for ch in range(N_CH)}
        save_spike_times_npz(
            root / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz",
            spikes, np.arange(1, N_CH + 1), FS, duration_s=60.0)
        adj = np.abs(rng.normal(0, 0.3, (N_CH, N_CH)))
        adj = (adj + adj.T) / 2
        np.fill_diagonal(adj, 0)
        atomic_savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz",
                     channels=np.arange(1, N_CH + 1),
                     **{f"adjM{LAG}mslag": adj, f"adjM{LAG}mslag_raw": adj})


def _params(tmp: Path, name: str, **kw) -> Params:
    p = Params(output_data_folder=str(tmp), output_data_folder_name=name,
               spreadsheet_file_name=str(tmp / "recs.csv"),
               spreadsheet_range="2:100", raw_data=str(tmp / "no-raw"),
               start_analysis_step=4, stop_analysis_step=4,
               func_con_lag_val=[LAG], channel_layout="MCS60",
               min_number_of_nodes_to_cal_net_met=2, random_seed=5,
               # Serial, so the counting stubs below are in this process.
               recording_workers=1)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _run(tmp: Path, name: str, **kw) -> dict:
    root = create_output_folders(tmp, name, ["WT"])
    _seed_inputs(root)
    out = run_pipeline(_params(tmp, name, **kw), log=lambda m: None)
    return json.load(open(out / "4_NetworkActivity" / "netmet_results.json"))


def _metrics(results: dict, rec: str = RECS[0]) -> dict:
    return results[rec][f"{LAG}mslag"]


def _without(metrics: dict, dropped) -> dict:
    return {k: v for k, v in metrics.items() if k not in dropped}


def _same_numbers(a: dict, b: dict) -> bool:
    """Every shared field identical, arrays included."""
    if set(a) != set(b):
        return False
    for key, left in a.items():
        right = b[key]
        if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
            if not np.array_equal(np.asarray(left, dtype=float),
                                  np.asarray(right, dtype=float),
                                  equal_nan=True):
                return False
        elif isinstance(left, float) or isinstance(right, float):
            if not (left == right or (np.isnan(left) and np.isnan(right))):
                return False
        elif left != right:
            return False
    return True


def _checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pd.DataFrame([{"Recording Filename": r, "DIV group": 21, "Genotype": "WT"}
                      for r in RECS]).to_csv(tmp / "recs.csv", index=False)

        # ── Default: both computed, as every run before this did ─────────────
        full = _run(tmp, "Full")
        full_metrics = _metrics(full)
        checks.append(("by default the effective rank is computed",
                       "effRank" in full_metrics and
                       not np.isnan(full_metrics["effRank"]),
                       str(full_metrics.get("effRank"))))
        checks.append(("by default the NMF fields are computed",
                       all(f in full_metrics for f in NMF_FIELDS),
                       str([f for f in NMF_FIELDS if f not in full_metrics])))

        # ── Switched off: absent, and genuinely not computed ──────────────────
        real_cal_nmf, real_eff_rank = step4.cal_nmf, step4.nm.effective_rank
        calls = {"nmf": 0, "eff_rank": 0}
        step4.cal_nmf = lambda *a, **k: (calls.__setitem__("nmf", calls["nmf"] + 1)
                                         or real_cal_nmf(*a, **k))
        step4.nm.effective_rank = lambda *a, **k: (
            calls.__setitem__("eff_rank", calls["eff_rank"] + 1)
            or real_eff_rank(*a, **k))
        try:
            off = _run(tmp, "Off", compute_nmf=False, compute_eff_rank=False)
        finally:
            step4.cal_nmf, step4.nm.effective_rank = real_cal_nmf, real_eff_rank

        off_metrics = _metrics(off)
        checks.append(("switched off, the expensive call is never made",
                       calls == {"nmf": 0, "eff_rank": 0}, str(calls)))
        checks.append(("switched off, effRank is absent rather than NaN",
                       "effRank" not in off_metrics,
                       str(off_metrics.get("effRank"))))
        checks.append(("switched off, the NMF fields are absent",
                       not any(f in off_metrics for f in NMF_FIELDS),
                       str([f for f in NMF_FIELDS if f in off_metrics])))

        # The claim the whole change rests on.
        dropped = {"effRank", *NMF_FIELDS}
        checks.append(("every other metric is bit-for-bit unchanged",
                       _same_numbers(_without(full_metrics, dropped), off_metrics),
                       str(sorted(set(_without(full_metrics, dropped)) ^ set(off_metrics)))))
        checks.append(("...for every recording in the batch, not just the first",
                       all(_same_numbers(_without(_metrics(full, r), dropped),
                                         _metrics(off, r)) for r in RECS), ""))

        # ── One at a time ────────────────────────────────────────────────────
        no_nmf = _metrics(_run(tmp, "NoNMF", compute_nmf=False))
        checks.append(("NMF alone can go, keeping the effective rank",
                       "effRank" in no_nmf
                       and not any(f in no_nmf for f in NMF_FIELDS),
                       str([f for f in NMF_FIELDS if f in no_nmf])))
        no_er = _metrics(_run(tmp, "NoER", compute_eff_rank=False))
        checks.append(("the effective rank alone can go, keeping NMF",
                       "effRank" not in no_er
                       and all(f in no_er for f in NMF_FIELDS),
                       str([f for f in NMF_FIELDS if f not in no_er])))

        # ── The CSV a reader actually opens ──────────────────────────────────
        full_csv = pd.read_csv(
            tmp / "Full" / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv")
        off_csv = pd.read_csv(
            tmp / "Off" / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv")
        checks.append(("the CSV loses exactly the switched-off columns",
                       set(full_csv.columns) - set(off_csv.columns)
                       == {"effRank", "num_nnmf_components", "nComponentsRelNS"},
                       str(sorted(set(full_csv.columns) - set(off_csv.columns)))))
        checks.append(("and keeps a row per recording either way",
                       len(off_csv) == len(full_csv) == len(RECS),
                       f"{len(off_csv)} vs {len(full_csv)}"))
    return checks


def _params_checks() -> list[Check]:
    """The defaults, and that they survive a round trip through params.json."""
    import json

    from meanap.params import load_params, save_params

    checks: list[Check] = []
    checks.append(("both default to on, so an existing run is unchanged",
                   Params().compute_nmf and Params().compute_eff_rank, ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = save_params(Params(compute_nmf=False, compute_eff_rank=False), tmp)
        loaded, unknown = load_params(path)
        checks.append(("the choice round-trips through params.json",
                       not loaded.compute_nmf and not loaded.compute_eff_rank
                       and not unknown, str(unknown)))

        # A params.json written before these existed must still mean "compute
        # them" — which is why they are their own fields rather than entries in
        # net_met_to_cal, whose old default lists neither metric.
        raw = json.load(open(path))
        del raw["compute_nmf"], raw["compute_eff_rank"]
        raw["net_met_to_cal"] = ["aN", "Dens", "CC"]  # an older, shorter list
        (tmp / "old.json").write_text(json.dumps(raw))
        revived, _ = load_params(tmp / "old.json")
        checks.append(("a params.json from before this still computes both",
                       revived.compute_nmf and revived.compute_eff_rank, ""))
    return checks


def _gui_checks() -> list[Check]:
    from meanap.gui.panels.connectivity import ConnectivityPanel

    checks: list[Check] = []
    panel = ConnectivityPanel()

    panel.load(Params(compute_nmf=False, compute_eff_rank=True))
    checks.append(("the panel shows what the params say",
                   not panel.compute_nmf.isChecked()
                   and panel.compute_eff_rank.isChecked(), ""))

    panel.compute_nmf.setChecked(True)
    panel.compute_eff_rank.setChecked(False)
    out = Params()
    panel.save(out)
    checks.append(("and writes back what was ticked",
                   out.compute_nmf and not out.compute_eff_rank, ""))

    # CAT-NAP reads its own NMF switch, so these must not look live there.
    panel.set_pipeline("catnap")
    checks.append(("in CAT-NAP mode the box is disabled, not silently ignored",
                   not panel._metrics_box.isEnabled()
                   and "CAT-NAP tab" in panel._metrics_box.title(),
                   panel._metrics_box.title()))
    panel.set_pipeline("meanap")
    checks.append(("and live again for an ephys run",
                   panel._metrics_box.isEnabled()
                   and panel._metrics_box.title() == "Network metrics",
                   panel._metrics_box.title()))
    return checks


def main() -> int:
    print("=" * 70)
    print("Step 4: switching the dimensionality metrics off")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [("Params:", _params_checks), ("Step 4:", _checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        print(f"\nGUI checks SKIPPED — PyQt6 not available ({e})")
    else:
        # Kept in a name: a QApplication that is only ever a temporary is
        # collected on the spot, and the first QWidget after that aborts.
        app = QApplication.instance() or QApplication([])  # noqa: F841
        p, n = _report("GUI:", _gui_checks())
        total_pass += p
        total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
