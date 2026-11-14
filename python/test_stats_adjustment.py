"""Step 5's adjusted effects: does an age or genotype effect survive a covariate?

    uv run python test_stats_adjustment.py

A synthetic timecourse with a known answer. Firing rate rises with age; one
metric depends on age *only through* rate (it should collapse once rate is
held fixed), another on age directly (it should survive), and a genotype
difference sits on the direct one. Then the same through ``run_stats`` on a
run folder: the CSV, the 5A4 figure, and the figure redrawn from the CSV.
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
warnings.filterwarnings("ignore")

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok or not detail else f"  — {detail}"))
    if not ok:
        fails.append(name)


def timecourse(seed: int = 0) -> pd.DataFrame:
    """30 cultures per genotype, recorded at DIV 7-35."""
    rng = np.random.default_rng(seed)
    rows = []
    for grp in ("WT", "KO"):
        for c in range(30):
            culture_rate = rng.normal(0, 0.4)
            culture_level = rng.normal(0, 0.3)
            for div in (7, 14, 21, 28, 35):
                age = (div - 21) / 14
                log_rate = 1.2 * age + culture_rate + rng.normal(0, 0.5)
                rows.append({
                    "FileName": f"MPT{grp}{c:02d}_A1_DIV{div}",
                    "Grp": grp, "DIV": div,
                    "FRmean": float(np.exp(log_rate)),
                    "numActiveElec": float(np.clip(30 + 10 * age + rng.normal(0, 6), 2, 60)),
                    # Age reaches it only through rate.
                    "Mediated": 0.9 * log_rate + culture_level + rng.normal(0, 0.4),
                    # Age reaches it directly; KO sits higher.
                    "Direct": 0.8 * age + 0.5 * (grp == "KO") + culture_level
                              + rng.normal(0, 0.4),
                    "Plate": f"P{c % 3}",
                })
    return pd.DataFrame(rows)


def dataset(table: pd.DataFrame):
    from meanap.stats.dataset import StatsDataset, derive_culture_ids

    table = table.copy()
    table["Culture"] = derive_culture_ids(table["FileName"])
    metrics = ["Mediated", "Direct", "FRmean", "numActiveElec"]
    return StatsDataset(table=table, metrics=metrics)


def model_checks() -> None:
    from meanap.stats.adjustment import adjusted_effects

    print("The model")
    ds = dataset(timecourse())
    res = adjusted_effects(ds, ["rate", "activity", "size", "FRmean+Plate"])
    t = res.table

    def row(metric, adjustment, term="age"):
        hit = t[(t.Metric == metric) & (t.Adjustment == adjustment) & (t.Term == term)]
        return hit.iloc[0] if len(hit) else None

    check("presets resolve against the run's columns; a set the run lacks is skipped, saying why",
          [s.name for s in res.sets] == ["rate", "activity", "FRmean+Plate"]
          and any(s.startswith("size:") and "aN" in s for s in res.skipped), str(res.skipped))
    a, b = row("Mediated", "none"), row("Mediated", "rate")
    check("an age effect carried by rate is significant unadjusted …",
          a.PValueFDR < 1e-6, f"q = {a.PValueFDR:.2g}")
    check("… and collapses once rate is held fixed",
          abs(b.Retained) < 0.3 and b.PValueFDR > 0.05,
          f"retained {b.Retained:.2f}, q = {b.PValueFDR:.2g}")
    c, d = row("Direct", "none"), row("Direct", "rate")
    check("an age effect of its own survives rate", d.PValueFDR < 1e-3 and 0.6 < d.Retained < 1.4,
          f"retained {d.Retained:.2f}, q = {d.PValueFDR:.2g}")
    g = row("Direct", "rate", "WT vs KO")
    check("and so does a genotype difference rate does not explain",
          g is not None and g.PValueFDR < 0.05 and g.EffectSize < 0, str(g))
    unadjusted = row("Mediated", "none")
    from meanap.stats.comparisons import compare_metrics
    five_a = compare_metrics(ds).table
    ref = five_a[(five_a.Metric == "Mediated") & (five_a.Term == "age")].iloc[0]
    check("the unadjusted row is the 5A model's (same cohort, same numbers)",
          np.isclose(unadjusted.EffectSize, ref.EffectSize), f"{unadjusted.EffectSize} vs {ref.EffectSize}")
    cov = t[(t.Metric == "Mediated") & (t.Adjustment == "rate") & (t.Term == "covariate FRmean")]
    check("the covariate's own coefficient is reported, outside the effects' FDR family",
          len(cov) == 1 and cov.iloc[0].Family == "covariate" and cov.iloc[0].EffectSize > 0.5)
    check("each set says how much of its covariates the design explains",
          0.3 < b.CovariateR2 < 0.9 and "FRmean (R²" in b.Covariates, f"{b.CovariateR2} {b.Covariates}")
    copy = row("FRmean", "rate")
    check("a metric is never adjusted for itself",
          copy is not None and "not adjusted" in str(copy.Note) and pd.isna(copy.PValue))
    plate = row("Direct", "FRmean+Plate")
    check("a column that is not a number enters as a factor",
          plate is not None and pd.notna(plate.EffectSize), str(plate))
    holes = ds.table.copy()
    holes.loc[:9, "numActiveElec"] = np.nan
    res2 = adjusted_effects(dataset(holes), ["rate", "activity"])
    n = res2.table.groupby("Adjustment").N.max()
    check("every set is fitted on the same recordings", n.nunique() == 1 and n.iloc[0] == 290,
          str(n.to_dict()))


def run_checks(tmp: Path) -> None:
    from meanap.stats.dataset import load_dataset
    from meanap.stats.figures import draw_stats_figure, load_results, stats_figures
    from meanap.stats.run import StatsSettings, run_stats

    print("Through step 5")
    table = timecourse(1)
    (tmp / "run" / "4_NetworkActivity").mkdir(parents=True)
    (tmp / "run" / "2_NeuronalActivity").mkdir(parents=True)
    table[["FileName", "Grp", "DIV", "Mediated", "Direct"]].assign(Lag=25).to_csv(
        tmp / "run" / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv", index=False)
    table[["FileName", "Grp", "DIV", "FRmean", "numActiveElec"]].to_csv(
        tmp / "run" / "2_NeuronalActivity" / "NeuronalActivity_RecordingLevel.csv", index=False)
    logs: list[str] = []
    settings = StatsSettings(correlation=False, decoding=False, regression=False,
                             celltype_mosaic=False, adjust_for=("rate", "bursting"))
    result = run_stats(tmp / "run", settings=settings, log=logs.append)
    text = "\n".join(map(str, logs))
    folder = next(p.parent for p in (tmp / "run" / "5_StatsAndML").rglob("adjusted_effects.csv"))
    check("step 5 writes adjusted_effects.csv beside comparisons.csv",
          (folder / "comparisons.csv").exists(), str(folder))
    check("and logs what it held fixed, what it skipped, and what lost significance",
          "Firing rate" in text and "bursting" in text and "no longer significant" in text, text)
    figure = list(folder.glob("5A4_adjusted_effects.*"))
    check("and draws 5A4", len(figure) == 1 and figure[0].stat().st_size > 5000, str(figure))
    ds = load_dataset(tmp / "run").for_lag(25)
    stored = load_results(folder, ds, lag=25)
    keys = [f.key for f in stats_figures(stored)]
    check("read back from the folder, the viewer is offered 5A4", "adjusted_effects" in keys, str(keys))
    redrawn = draw_stats_figure(stored, "adjusted_effects", tmp / "redrawn.png")
    check("and can redraw it from the CSV", redrawn is not None and Path(redrawn).exists())
    off = run_stats(tmp / "run", dest=tmp / "off",
                    settings=StatsSettings(correlation=False, decoding=False, regression=False,
                                           celltype_mosaic=False, adjustment=False),
                    log=lambda m: None)
    check("switched off, nothing is written", not list(Path(off.dest).rglob("adjusted_effects.csv")))
    assert result.dest


def gui_checks() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from meanap.gui.panels.stats import StatsPanel

    print("The Stats tab")
    panel = StatsPanel()
    settings = panel.settings()
    check("rate and rate + active units are ticked by default",
          settings.adjustment and settings.adjust_for == ("rate", "activity"),
          str(settings.adjust_for))
    panel.adjust_sets["size"].setChecked(True)
    panel.adjust_custom.setText("FRmean+numActiveElec, Plate")
    check("presets and typed sets both reach the settings",
          panel.settings().adjust_for == ("rate", "activity", "size",
                                          "FRmean+numActiveElec", "Plate"),
          str(panel.settings().adjust_for))
    panel.adjustment_cb.setChecked(False)
    check("unticked, it is off and its sets grey out",
          not panel.settings().adjustment and not panel.adjust_custom.isEnabled())
    del app


def main() -> int:
    model_checks()
    with tempfile.TemporaryDirectory() as tmp:
        run_checks(Path(tmp))
    gui_checks()
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
