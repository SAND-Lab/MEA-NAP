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
    table[["FileName", "Grp", "DIV", "Mediated", "Direct"]].assign(Lag="25mslag").to_csv(
        tmp / "run" / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv", index=False)
    # What the viewer's entry point needs of a run that is statistics only.
    (tmp / "run" / "4_NetworkActivity" / "netmet_results.json").write_text("{}")
    (tmp / "run" / "params.json").write_text('{"custom_grp_order": ["WT", "KO"]}')
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
    ds = load_dataset(tmp / "run").for_lag("25mslag")
    stored = load_results(folder, ds, lag="25mslag")
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
    viewer_render_checks(tmp / "run", folder.name)


def viewer_render_checks(run: Path, lag: str) -> None:
    import time

    from meanap.pipeline import render
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.render import load_context

    print("Refitting on demand (the viewer)")
    ctx = load_context(run)
    choices = render.adjustment_choices(ctx, lag)
    available = {name for name, _l, ok, _w in choices["presets"] if ok}
    check("the picker offers the presets this run can resolve, and the run's own sets",
          available == {"rate", "activity"} and choices["chosen"] == ["rate", "bursting"][:1]
          and ("Direct", "Direct") in [tuple(c) for c in choices["columns"]],
          str(choices["chosen"]) + str(available))

    def drawn(adjust_for):
        with capture_figures() as got:
            try:
                render.render_stats_figure(ctx, lag, "adjusted_effects", run / "_live",
                                           overrides={"adjust_for": adjust_for})
            except ValueError:
                if not got:
                    raise
        chart = getattr(got[-1].figure, "chart", got[-1].figure) if got else None
        return chart

    start = time.perf_counter()
    one = drawn("rate")
    first = time.perf_counter() - start
    two = drawn("rate,FRmean+numActiveElec")
    keys = render._adjusted_table(ctx, lag, ("rate", "FRmean+numActiveElec")).table
    check("a new choice of sets is refitted and drawn",
          one is not None and two is not None
          and set(keys["Adjustment"]) == {"none", "rate", "FRmean+numActiveElec"},
          str(set(keys["Adjustment"])))
    check("fast enough to follow the ticks (under 3 s here)", first < 3, f"{first:.1f}s")
    start = time.perf_counter()
    drawn("rate")
    check("and a choice made before comes back from memory",
          time.perf_counter() - start < first / 2, "")
    try:
        render.render_stats_figure(ctx, lag, "adjusted_effects", run / "_live",
                                   overrides={"adjust_for": ""})
        check("nothing ticked says to tick something", False)
    except ValueError as err:
        check("nothing ticked says to tick something", "tick" in str(err).lower(), str(err))

    with capture_figures() as got:
        render.render_stats_figure(ctx, lag, "adjusted_effects", run / "_live",
                                   overrides={"adjust_for": "rate", "adjust_term": "age",
                                              "adjust_show": "survives",
                                              "adjust_sort": "name"})
    chart = getattr(got[-1].figure, "scene", None) if got else None
    titles = [p.title for p in getattr(chart, "panels", [])]
    rows = [label for _v, label, *_ in (chart.panels[0].yticks if titles else [])]
    check("one effect alone draws one panel, with only the rows asked for, in order",
          titles == ["Age"] and rows == sorted(rows, key=str.lower, reverse=True)
          and "Direct" in rows and "Mediated" not in rows, f"{titles} {rows}")

    gui_viewer_checks(run)


def gui_viewer_checks(run: Path) -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from meanap.gui.results_viewer import ResultsViewer

    def wait(ms=30):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def settle(v):
        for _ in range(1500):
            wait()
            if not (v._drawing or v._queued or v._restyle.isActive()):
                break
        wait(100)

    viewer = ResultsViewer()
    viewer.resize(1400, 900)
    viewer.show()
    viewer.load_run(run)
    settle(viewer)
    viewer.set_scope("group")
    settle(viewer)
    row = next((label for label in viewer.figure_labels() if "held fixed" in label.lower()
                or "holding" in label.lower()), None)
    check("the viewer lists 5A4 under the comparisons", row is not None, str(viewer.figure_labels()))
    if row is None:
        return
    viewer.select_figure(row)
    settle(viewer)
    panel = viewer.adjust_panel
    check("selecting it opens the covariate picker beside it, with the run's sets ticked",
          viewer._right.isVisible() and panel.isVisible() and panel.sets() == ["rate"],
          str(panel.sets()))
    check("the bursting preset is greyed out, saying why",
          not panel.presets["bursting"].isEnabled()
          and "no" in panel.presets["bursting"].toolTip().lower())
    panel.presets["activity"].setChecked(True)
    panel.columns["Direct"].setChecked(True)
    settle(viewer)
    request = viewer._request()
    check("ticking refits: the figure is asked for with the new sets",
          request["overrides"]["adjust_for"] == "rate,activity,Direct"
          and "Direct" in panel.own_summary.text(), str(request))
    legend = [item.label for item in viewer.canvas.scene.legend.items
              if item.kind == "point"] \
        if getattr(viewer.canvas, "scene", None) is not None \
        and getattr(viewer.canvas.scene, "legend", None) is not None else []
    check("and the figure on screen has a line of dots per set",
          len(legend) == 4, str(legend))
    terms = [panel.term.itemData(i) for i in range(panel.term.count())]
    check("the View menu offers every effect, then each one alone",
          terms[0] == "all" and "age" in terms and len(terms) >= 3, str(terms))
    panel.term.setCurrentIndex(terms.index("age"))
    panel.show_rows.setCurrentIndex(panel.show_rows.findData("changed"))
    panel.sort.setCurrentIndex(panel.sort.findData("retained"))
    settle(viewer)
    request = viewer._request()["overrides"]
    check("choosing one effect, what changed, and an order redraws with them",
          request.get("adjust_term") == "age" and request.get("adjust_show") == "changed"
          and request.get("adjust_sort") == "retained"
          and getattr(getattr(viewer.canvas, "scene", None), "legend", None) is not None,
          str(request))
    viewer.select_figure(next(label for label in viewer.figure_labels()
                              if "age and genotype" in label.lower()))
    settle(viewer)
    check("another figure puts the picker away", not viewer._right.isVisible())
    viewer.close()
    del app


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


def verdict_checks() -> None:
    from meanap.stats.plots import LOST, PARTLY, SURVIVES, adjusted_verdicts

    print("What survives, per effect")
    rows = []
    for metric, base, under in (("kept", (0.8, 0.001), [(0.7, 0.01), (0.6, 0.02)]),
                                ("gone", (0.8, 0.001), [(0.1, 0.6), (0.05, 0.8)]),
                                ("half", (0.8, 0.001), [(0.7, 0.01), (0.1, 0.5)]),
                                ("flipped", (0.8, 0.001), [(-0.7, 0.01), (0.6, 0.01)]),
                                ("never", (0.1, 0.5), [(0.7, 0.01), (0.6, 0.01)])):
        rows.append((metric, "age", "none", *base, np.nan))
        for k, (effect, q) in enumerate(under):
            rows.append((metric, "age", f"set{k}", effect, q, effect / base[0]))
    table = pd.DataFrame(rows, columns=["Metric", "Term", "Adjustment", "EffectSize",
                                        "PValueFDR", "Retained"])
    got = adjusted_verdicts(table).set_index("Metric")
    check("significant under every set survives; under none is lost; else partly",
          got.loc["kept", "Verdict"] == SURVIVES and got.loc["gone", "Verdict"] == LOST
          and got.loc["half", "Verdict"] == PARTLY, str(got["Verdict"].to_dict()))
    check("a sign flip does not count as surviving",
          got.loc["flipped", "Verdict"] == PARTLY and got.loc["flipped", "Held"] == 1)
    check("an effect not significant unadjusted gets no verdict", "never" not in got.index)
    check("the count and the most lost are carried",
          got.loc["half", "Sets"] == 2 and abs(got.loc["gone", "Retained"] - 0.05 / 0.8) < 1e-9)


def unsigned_checks() -> None:
    import tempfile as _tf

    from meanap.native.chart import Points
    from meanap.pipeline.figure_output import capture_figures
    from meanap.stats.plots import plot_adjusted_effects

    print("Sizes only")
    rows = []
    for metric, base, under in (("up", 0.8, 0.7), ("down", -1.2, -1.0), ("flips", 0.9, -0.5)):
        rows.append((metric, "age", "none", "", base, 0.001))
        rows.append((metric, "age", "rate", "Firing rate", under, 0.01))
    table = pd.DataFrame(rows, columns=["Metric", "Term", "Adjustment", "AdjustmentLabel",
                                        "EffectSize", "PValueFDR"])
    table = table.assign(Family="mixed-model", MetricLabel=table["Metric"],
                         CovariateR2=0.2, Retained=np.nan)

    def points(**kw):
        with _tf.TemporaryDirectory() as tmp, capture_figures() as got:
            plot_adjusted_effects(table, Path(tmp) / "f.png", **kw)
        chart = got[-1].figure.scene
        return [m for m in chart.panels[0].marks if isinstance(m, Points)], chart

    signed, _ = points()
    sized, chart = points(unsigned="1", sort="effect")
    check("signed, effects keep their direction",
          min(float(m.x[0]) for m in signed) < 0)
    check("sizes only, every dot sits at |effect|",
          sorted(round(float(m.x[0]), 3) for m in sized)
          == sorted(round(abs(v), 3) for v in table["EffectSize"]))
    check("and the axis says so", chart.panels[0].xlabel.startswith("|"))
    ringed = [m for m in sized if m.edge_width >= 2.0]
    check("a sign that flipped under adjustment is ringed",
          len(ringed) == 1 and "opposite sign" in ringed[0].hover[0], str(len(ringed)))


def main() -> int:
    verdict_checks()
    unsigned_checks()
    model_checks()
    with tempfile.TemporaryDirectory() as tmp:
        run_checks(Path(tmp))
    gui_checks()
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
