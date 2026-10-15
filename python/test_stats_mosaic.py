"""Test the cell-level mosaic analysis (``src/meanap/stats/celltypes.py``).

Run from the repo root::

    uv run python python/test_stats_mosaic.py

A synthetic CAT-NAP run with three genotypes — WT (every cell Mecp2+), KO
(every cell Mecp2-) and a heterozygous mosaic — and three features whose answer
is known by construction:

  - ``FR`` is **cell-autonomous**: every Mecp2- cell has it raised, wherever it
    lives, so it must differ between mosaic neighbours and between genotypes;
  - ``ND`` is **network-level**: every cell of a culture shares it, rising with
    the culture's share of mutant cells, so it must differ between genotypes
    and environments but *not* between mosaic neighbours;
  - ``PC`` is noise and must differ nowhere.

The same run with the cell-autonomous effect switched off is the negative
control for the decoder and the mutant-likeness score — the checks that would
fail if anything shared by a recording leaked into a cell-level contrast.

:func:`write_mosaic_tables` is also used by ``test_stats_report.py`` so its
synthetic run exercises the 5G figures through the report, bundle and viewer.
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

warnings.simplefilter("ignore")

from meanap.stats.celltypes import load_cell_table, run_mosaic  # noqa: E402

Check = tuple[str, bool, str]

GROUPS = {"WT": 0.0, "HET": 0.5, "KO": 1.0}


def write_mosaic_tables(root: Path, *, autonomous: float = 1.0, n_cultures: int = 6,
                        n_cells: int = 50, ages=(14, 21, 28), lag="25mslag",
                        seed: int = 3) -> Path:
    """Node-level activity, network, calls and tracking for a synthetic run."""
    rng = np.random.default_rng(seed)
    act, net, calls, tracked = [], [], [], []
    for group, mutant_share in GROUPS.items():
        for c in range(n_cultures):
            culture = f"{group}{c:02d}_P1"
            offset = rng.normal(0, 0.3)
            # Each cell keeps its marker state and a stable trait across days,
            # as a tracked cell does.
            mutant = rng.random(n_cells) < mutant_share
            trait = rng.normal(0, 0.5, n_cells)
            for div in ages:
                name = f"{culture}_{group}_DIV{div}"
                for ch in range(1, n_cells + 1):
                    m = bool(mutant[ch - 1])
                    fr = np.exp(-3 + autonomous * m + trait[ch - 1] + offset
                                + rng.normal(0, 0.5))
                    act.append({"FileName": name, "Grp": group, "DIV": float(div),
                                "Channel": ch, "FR": fr})
                    net.append({"FileName": name, "Grp": group, "DIV": float(div),
                                "Lag": lag, "Channel": ch,
                                "ND": 10 + 8 * mutant_share + 2 * offset + rng.normal(0, 2),
                                "PC": rng.normal(0.5, 0.1), "Ci": 1.0})
                    # References are only partly labelled, and the analysis has
                    # to use their unlabelled cells too.
                    if group == "HET" or c % 2 == 0:
                        calls.append({"FileName": name, "Channel": ch,
                                      "celltype_Mecp2": "-" if m else "+",
                                      "celltype_NeuN": "+", "callSource": "label file"})
                    if ch <= n_cells // 2:
                        tracked.append({"chain": culture, "cluster": ch,
                                        "FileName": name, "Channel": ch})
    (root / "2_NeuronalActivity").mkdir(parents=True, exist_ok=True)
    (root / "4_NetworkActivity").mkdir(parents=True, exist_ok=True)
    (root / "CellTracking").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(act).to_csv(root / "2_NeuronalActivity/TwoPhotonActivity_NodeLevel.csv",
                             index=False)
    pd.DataFrame(net).to_csv(root / "4_NetworkActivity/NetworkActivity_NodeLevel.csv",
                             index=False)
    pd.DataFrame(calls).to_csv(root / "2_NeuronalActivity/CellTypeCalls.csv", index=False)
    pd.DataFrame(tracked).to_csv(root / "CellTracking/TrackedCellMetrics.csv", index=False)
    return root


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    passed = 0
    for name, ok, detail in checks:
        passed += bool(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail and not ok else ""))
    return passed, len(checks)


def _effect(res, version, feature, contrast, scope="pooled"):
    e = res.effects
    row = e[(e["Version"] == version) & (e["Scope"] == scope)
            & (e["Feature"] == feature) & (e["Contrast"] == contrast)]
    return row.iloc[0] if len(row) else None


def _planted_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = write_mosaic_tables(Path(tmp))
        cells = load_cell_table(root)
        res = run_mosaic(cells, lag="25mslag", n_repeats=1, n_permutations=19,
                         log=lambda _m: None)

    checks.append((
        "the mosaic and both references are identified from the calls",
        (cells.mosaic_group, cells.pos_group, cells.neg_group) == ("HET", "WT", "KO"),
        str((cells.mosaic_group, cells.pos_group, cells.neg_group))))
    n_wt = int((cells.table["Grp"] == "WT").sum())
    traj = res.trajectories
    checks.append((
        "reference cultures contribute their unlabelled cells too",
        traj[(traj["Version"] == "all") & (traj["Class"] == "pos")]["NCultures"].max() == 6,
        f"{n_wt} WT cell-days"))
    checks.append(("both versions ran", set(res.effects["Version"]) == {"all", "tracked"},
                   str(set(res.effects["Version"]))))

    for version in ("all", "tracked"):
        auto = _effect(res, version, "FR", "cell-autonomous")
        checks.append((
            f"[{version}] a cell-autonomous feature differs between mosaic neighbours",
            auto is not None and auto["PValueFDR"] < 0.01 and auto["Estimate"] > 0.3,
            str(None if auto is None else (auto["Estimate"], auto["PValueFDR"]))))
        net_auto = _effect(res, version, "ND", "cell-autonomous")
        checks.append((
            f"[{version}] a network-level feature does not",
            net_auto is not None and net_auto["PValue"] > 0.05
            and abs(net_auto["Estimate"]) < 0.15,
            str(None if net_auto is None else (net_auto["Estimate"], net_auto["PValue"]))))
        env = _effect(res, version, "ND", "environment-pos")
        geno = _effect(res, version, "ND", "genotype")
        checks.append((
            f"[{version}] the network-level feature moves with the environment and genotype",
            env is not None and geno is not None and env["Estimate"] > 0
            and geno["PValueFDR"] < 0.05 and geno["Estimate"] > env["Estimate"],
            str(None if geno is None else (env["Estimate"], geno["Estimate"]))))
        noise = res.effects[(res.effects["Version"] == version)
                            & (res.effects["Feature"] == "PC")
                            & (res.effects["Scope"] == "pooled")]
        checks.append((
            f"[{version}] a noise feature differs in no contrast",
            (noise["PValueFDR"] > 0.05).all(), noise[["Contrast", "PValueFDR"]].to_string()))

    summary = res.score_summary
    stat = dict(zip(summary.loc[summary["Version"] == "all", "Statistic"],
                    summary.loc[summary["Version"] == "all", "Value"]))
    checks.append(("the references separate on held-out cultures",
                   stat.get("ReferenceAUC", 0) > 0.75, str(stat.get("ReferenceAUC"))))
    checks.append((
        "mosaic Mecp2- cells score more mutant-like than their neighbours",
        stat.get("ModelGap", 0) > 0 and stat.get("WilcoxonP", 1) < 0.05,
        str({k: stat.get(k) for k in ("ModelGap", "WilcoxonP")})))
    pooled = res.decoding[(res.decoding["Version"] == "all")
                          & (res.decoding["Scope"] == "pooled")].iloc[0]
    checks.append((
        "marker state is decodable from a cell-autonomous feature",
        pooled["BalancedAccuracy"] > pooled["NullP95"] and pooled["PValue"] <= 0.05,
        str(pooled[["BalancedAccuracy", "NullP95", "PValue"]].to_dict())))
    checks.append((
        "the per-age effects are FDR-corrected within an age",
        res.effects["PValueFDR"].notna().any()
        and (res.effects["PValueFDR"] >= res.effects["PValue"] - 1e-12).all(), ""))
    checks.append((
        "within-recording pairs are written for the mosaic only",
        not res.paired.empty and res.paired["FileName"].str.startswith("HET").all(), ""))
    return checks


def _null_checks() -> list[Check]:
    """No cell-autonomous effect planted: nothing cell-level may be found."""
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = write_mosaic_tables(Path(tmp), autonomous=0.0)
        res = run_mosaic(load_cell_table(root), lag="25mslag", n_repeats=1,
                         n_permutations=19, log=lambda _m: None)
    auto = res.effects[(res.effects["Contrast"] == "cell-autonomous")
                       & (res.effects["Scope"] == "pooled")]
    checks.append(("no feature is cell-autonomous when none was planted",
                   (auto["PValueFDR"] > 0.05).all(),
                   auto[["Version", "Feature", "PValueFDR"]].to_string()))
    pooled = res.decoding[res.decoding["Scope"] == "pooled"]
    checks.append(("marker state is not decodable when nothing marks it",
                   (pooled["PValue"] > 0.05).all(),
                   pooled[["Version", "BalancedAccuracy", "PValue"]].to_string()))
    stat = res.score_summary.set_index(["Version", "Statistic"])["Value"]
    checks.append(("mutant-likeness does not separate mosaic neighbours",
                   abs(stat[("all", "ModelGap")]) < 2 * stat[("all", "ModelGapSE")] + 0.05,
                   f"{stat[('all', 'ModelGap')]:.3f} ± {stat[('all', 'ModelGapSE')]:.3f}"))
    return checks


def _skip_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = write_mosaic_tables(Path(tmp))
        (root / "2_NeuronalActivity/CellTypeCalls.csv").unlink()
        checks.append(("a run without cell-type calls is not a mosaic run",
                       load_cell_table(root) is None, ""))
    with tempfile.TemporaryDirectory() as tmp:
        root = write_mosaic_tables(Path(tmp))
        path = root / "2_NeuronalActivity/CellTypeCalls.csv"
        calls = pd.read_csv(path)
        calls = calls[~calls["FileName"].str.startswith("HET")]
        calls.to_csv(path, index=False)
        cells = load_cell_table(root)
        res = run_mosaic(cells, lag="25mslag", log=lambda _m: None)
        checks.append((
            "calls without a mosaic group skip the analysis but keep the inventory",
            cells.mosaic_group is None and bool(cells.reason) and not res.ran
            and not res.inventory.empty, cells.reason))
    return checks


def _real_checks() -> list[Check]:
    bundle = REPO_ROOT / "local" / "yin-tracked-final-oct-8.meanap"
    if not bundle.exists():
        print("\n(Yin tracked bundle not present — real-data checks skipped)")
        return []
    cells = load_cell_table(bundle)
    return [("the Yin tracked run is read as a Mecp2 mosaic",
             (cells.mosaic_group, cells.pos_group, cells.neg_group) == ("HET", "WT", "KO")
             and cells.has_tracking, str((cells.mosaic_group, cells.pos_group,
                                          cells.neg_group)))]


def main() -> int:
    total_pass = total = 0
    for title, fn in (("A. planted cell-autonomous and network effects", _planted_checks),
                      ("B. negative control: nothing cell-autonomous", _null_checks),
                      ("C. runs that cannot be analysed", _skip_checks),
                      ("D. real data", _real_checks)):
        p, n = _report(title, fn())
        total_pass += p
        total += n
    print(f"\n{total_pass}/{total} checks passed")
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
