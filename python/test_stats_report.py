"""Test that step-5 results reach the HTML report and the bundle viewer.

Run from the repo root::

    uv run python python/test_stats_report.py

The statistics step writes both tables and figures into ``5_StatsAndML/``. A
bundle carries only the tables — every figure there is a pure function of the
CSVs beside it — so the figures have to be reproducible from those tables alone,
and three separate consumers (the step, the exporter, the viewer) have to agree
on what figures exist. Both of those are drift-prone in a way tests catch and
review does not, so this checks them directly:

Section A, on a synthetic run built from scratch, asserts that

  - the figure catalogue and the files actually written are the same set — a
    figure the catalogue does not list is one the viewer will never offer, and
    one it lists but nothing writes is a broken thumbnail;
  - every figure the step writes is matched by an HTML-report caption pattern,
    so nothing lands in the report unlabelled;
  - results read back from the CSVs redraw **byte-identical** figures, which is
    what makes it safe for a bundle to drop the pictures;
  - a bundle keeps the tables and drops the figures, and claims the family;
  - the figures survive the round trip through a real bundle.

Section B runs the same checks against the real Yin timecourse bundle and
**skips gracefully** when the gitignored ``local/`` folder is absent.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

warnings.simplefilter("ignore")

Check = tuple[str, bool, str]

BUNDLE = REPO_ROOT / "local" / "YinThesisRun.meanap"


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


def _md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


# ── A synthetic run folder ───────────────────────────────────────────────────

def _make_run(root: Path) -> Path:
    """The smallest output folder the statistics step will read.

    Only the recording-level network CSV and a params file: ``load_dataset``
    needs nothing else, and building a full run here would test the pipeline
    rather than this.
    """
    rng = np.random.default_rng(11)
    rows = []
    for culture in range(24):
        group = "WT" if culture % 2 else "KO"
        offset = rng.normal(0, 0.3)
        for div in (14, 21, 28):
            rows.append({
                "FileName": f"CULT{culture:03d}_20240101_DIV{div}",
                "Grp": group, "DIV": float(div), "Lag": "25mslag",
                "Dens": 0.02 * div + offset + rng.normal(0, 0.1),
                "Eglob": 0.01 * div + rng.normal(0, 0.1),
                "Q": (0.6 if group == "KO" else 0.4) + rng.normal(0, 0.1),
                "aN": rng.integers(20, 60),
                "CC": rng.normal(0, 1),
            })
    net = root / "4_NetworkActivity"
    net.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(net / "NetworkActivity_RecordingLevel.csv", index=False)
    # ``load_context`` — the viewer's and exporter's entry point — refuses a run
    # with no step-4 metrics file, so the synthetic run needs one even though
    # nothing here reads it. Empty is honest: this folder has no per-recording
    # network figures to draw, only statistics.
    with open(net / "netmet_results.json", "w") as fh:
        json.dump({}, fh)
    with open(root / "params.json", "w") as fh:
        json.dump({"custom_grp_order": ["WT", "KO"], "suite2p_mode": True}, fh)
    return root


def _run_stats(root: Path) -> object:
    from meanap.stats.run import StatsSettings, run_stats

    settings = StatsSettings(
        n_repeats=1, n_permutations=0, n_orderings=20, importance_repeats=2,
        per_age_decoding=True, models=("logistic", "lda"),
        regression_models=("ridge",))
    return run_stats(root, dest=root / "5_StatsAndML", settings=settings,
                     log=lambda _m: None)


# ── Section A ────────────────────────────────────────────────────────────────

def _catalogue_checks(root: Path, lag: str) -> list[Check]:
    from meanap.stats.dataset import load_dataset
    from meanap.stats.figures import load_results, stats_figures

    checks: list[Check] = []
    folder = root / "5_StatsAndML" / lag
    ds = load_dataset(root)
    results = load_results(folder, ds.for_lag(ds.lags[0]), lag=lag)
    figures = stats_figures(results)

    written = {p.stem for p in folder.glob("*.png")}
    catalogued = {f.filename for f in figures}
    checks.append((
        "the catalogue lists exactly the figures the step wrote",
        written == catalogued,
        f"only written {sorted(written - catalogued)}, "
        f"only catalogued {sorted(catalogued - written)}"))
    checks.append((
        "every figure has a distinct key and filename",
        len({f.key for f in figures}) == len(figures)
        and len(catalogued) == len(figures), ""))
    checks.append((
        "every figure carries a caption and a group",
        all(f.caption and f.group for f in figures),
        str([f.key for f in figures if not (f.caption and f.group)])))

    from meanap.stats.figures import FIGURE_GROUPS

    known = {key for key, _label, _prefix in FIGURE_GROUPS}
    checks.append((
        "every figure's group is one of the four analyses",
        all(f.group in known for f in figures),
        str(sorted({f.group for f in figures} - known))))

    # Filenames must sort into the order the analyses are meant to be read.
    order = [f.filename for f in figures]
    checks.append((
        "filenames sort into the catalogue's own order",
        order == sorted(order), str(order)))
    return checks


def _caption_checks(root: Path, lag: str) -> list[Check]:
    from meanap.pipeline.report import describe_data_file, describe_folder, describe_plot
    from meanap.stats.figures import report_patterns

    checks: list[Check] = []
    folder = root / "5_StatsAndML" / lag
    patterns = [re.compile(rx) for rx, _t, _c in report_patterns()]

    images = sorted(p.name for p in folder.glob("*.png"))
    unmatched = [n for n in images if not any(rx.match(n) for rx in patterns)]
    checks.append((
        "every figure the step writes has a report caption pattern",
        not unmatched, str(unmatched)))

    described = [n for n in images if describe_plot(n, lag) is not None]
    checks.append((
        "the report gives each of them a title and a caption",
        len(described) == len(images),
        str(sorted(set(images) - set(described)))))

    tables = sorted(p.name for p in folder.glob("*.csv"))
    undescribed = [n for n in tables if describe_data_file(n) is None]
    checks.append((
        "every table the step writes is described in the report",
        not undescribed, str(undescribed)))

    checks.append((
        "the 5_StatsAndML folder itself is described",
        bool(describe_folder("5_StatsAndML")), ""))

    # The per-age heatmaps are the one templated caption; check the age is
    # actually substituted rather than left as a literal placeholder.
    per_age = [n for n in images if n.startswith("5A2_effects_group-at-age-")]
    if per_age:
        title, _caption = describe_plot(per_age[0], lag)
        checks.append((
            "the per-age caption substitutes the age into its title",
            "{" not in title and any(ch.isdigit() for ch in title), title))
    return checks


def _redraw_checks(root: Path, lag: str) -> list[Check]:
    from meanap.stats.dataset import load_dataset
    from meanap.stats.figures import draw_stats_figure, load_results, stats_figures

    checks: list[Check] = []
    folder = root / "5_StatsAndML" / lag
    ds = load_dataset(root)
    results = load_results(folder, ds.for_lag(ds.lags[0]), lag=lag)

    with tempfile.TemporaryDirectory() as tmp:
        identical, drawn = 0, 0
        differing = []
        for figure in stats_figures(results):
            path = draw_stats_figure(results, figure.key,
                                     Path(tmp) / f"{figure.filename}.png")
            if path is None:
                continue
            drawn += 1
            if _md5(path) == _md5(folder / f"{figure.filename}.png"):
                identical += 1
            else:
                differing.append(figure.key)
        checks.append((
            "every figure redraws byte-identically from the stored tables",
            drawn > 0 and identical == drawn,
            f"{identical}/{drawn} identical; differing: {differing}"))

    from meanap.stats.figures import StatsResults

    empty = StatsResults(dataset=ds)
    checks.append((
        "results with no analyses offer no figures",
        stats_figures(empty) == [], ""))
    try:
        draw_stats_figure(results, "no_such_figure", Path(tempfile.gettempdir()) / "x.png")
        ok, detail = False, "no error raised"
    except ValueError as exc:
        ok, detail = "Unknown statistics figure" in str(exc), str(exc)
    checks.append(("an unknown figure key is refused by name", ok, detail))
    return checks


def _bundle_checks(root: Path, lag: str) -> list[Check]:
    import zipfile

    from meanap.pipeline.bundle import open_bundle, write_bundle
    from meanap.pipeline.render import (
        available_stats_figures, available_stats_lags, load_context,
        render_stats_figure,
    )

    checks: list[Check] = []
    folder = root / "5_StatsAndML" / lag
    manifest = {"format": 1, "mode": "catnap", "express": True, "lags": [25],
                "recordings": [], "reconstructable": [], "not_reconstructable": [],
                "embedded_figures": []}
    dest = root.parent / "synthetic.meanap"
    write_bundle(root, manifest, dest)

    with zipfile.ZipFile(dest) as zf:
        members = [n for n in zf.namelist() if n.startswith("5_StatsAndML")]
    pngs = [n for n in members if n.endswith(".png")]
    tables = [n for n in members if n.endswith((".csv", ".json"))]
    checks.append((
        "the bundle carries the statistics tables",
        len(tables) >= 5, f"{len(tables)} tables"))
    checks.append((
        "and drops the statistics figures",
        not pngs, f"{len(pngs)} figures packed"))

    bundle = open_bundle(dest)
    try:
        checks.append((
            "the manifest claims the statistics family",
            "5_stats" in bundle.manifest.get("reconstructable", []),
            str(bundle.manifest.get("reconstructable"))))
        ctx = load_context(bundle)
        lags = available_stats_lags(ctx)
        checks.append((
            "the viewer finds the statistics results in the bundle",
            lags == [lag], str(lags)))
        figures = available_stats_figures(ctx, lag)
        checks.append((
            "and offers the same figures the folder held",
            {f.filename for f in figures} == {p.stem for p in folder.glob("*.png")},
            f"{len(figures)} offered"))

        with tempfile.TemporaryDirectory() as tmp:
            same = 0
            for figure in figures:
                path = render_stats_figure(ctx, lag, figure.key, Path(tmp))
                same += _md5(path) == _md5(folder / f"{figure.filename}.png")
            checks.append((
                "rendering from the bundle reproduces the folder's figures exactly",
                same == len(figures), f"{same}/{len(figures)}"))

        try:
            render_stats_figure(ctx, "no-such-lag", "correlation", Path(tempfile.gettempdir()))
            ok, detail = False, "no error raised"
        except ValueError as exc:
            ok, detail = "no statistics results" in str(exc), str(exc)
        checks.append((
            "a lag with no results says so, actionably", ok, detail))
    finally:
        bundle.close()

    # The other half of the round trip: turning the bundle back into an
    # ordinary output folder has to put the figures back beside their tables,
    # since that folder is what gets sent to someone without MEA-NAP.
    from meanap.pipeline.export import export_output_folder

    exported = root.parent / "exported"
    result = export_output_folder(dest, dest=exported, report=True,
                                  log=lambda _m: None)
    out = exported / "5_StatsAndML" / lag
    checks.append((
        "exporting the bundle redraws the statistics figures into the folder",
        {p.stem for p in out.glob("*.png")} == {p.stem for p in folder.glob("*.png")},
        f"{len(list(out.glob('*.png')))} drawn, {len(result.skipped)} skipped"))
    checks.append((
        "and copies the tables they were drawn from",
        len(list(out.glob("*.csv"))) == len(list(folder.glob("*.csv"))), ""))
    checks.append((
        "the exported report captions them",
        result.report is not None
        and "Variance decomposition" in Path(result.report).read_text(),
        str(result.report)))
    return checks


def _viewer_checks(root: Path, lag: str) -> list[Check]:
    """The viewer's manifest section and its figure route."""
    from meanap.pipeline.bundle import open_bundle
    from meanap.viewer.server import ViewerService

    checks: list[Check] = []
    bundle_path = root.parent / "synthetic.meanap"
    bundle = open_bundle(bundle_path)
    try:
        service = ViewerService(bundle_path)
        manifest = service.manifest()
        stats = manifest.get("stats") or []
        checks.append((
            "the viewer manifest carries a statistics section",
            len(stats) == 1 and stats[0]["lag"] == lag, str(stats)[:120]))
        groups = stats[0]["groups"] if stats else []
        checks.append((
            "grouped by analysis, in the catalogue's order",
            [g["key"] for g in groups] == [
                k for k in ("comparisons", "correlation", "decoding", "regression")
                if any(g["key"] == k for g in groups)],
            str([g["key"] for g in groups])))
        checks.append((
            "each offered figure carries its caption for the viewer to show",
            all(f.get("caption") for g in groups for f in g["figures"]), ""))

        key = groups[0]["figures"][0]["key"] if groups and groups[0]["figures"] else None
        if key:
            path = service.stats_figure(lag, key, fmt="png", thumbnail=False,
                                        overrides={})
            checks.append((
                "the figure route renders and caches a PNG",
                Path(path).exists() and Path(path).stat().st_size > 1000, str(path)))
            again = service.stats_figure(lag, key, fmt="png", thumbnail=False,
                                         overrides={})
            checks.append((
                "asking again returns the same cached file",
                Path(again) == Path(path), f"{path} vs {again}"))
    finally:
        bundle.close()
    return checks


# ── Section B ────────────────────────────────────────────────────────────────

def _real_bundle_checks() -> list[Check]:
    from meanap.pipeline.bundle import open_bundle
    from meanap.pipeline.render import (
        available_stats_figures, available_stats_lags, load_context,
    )

    checks: list[Check] = []
    bundle = open_bundle(BUNDLE)
    try:
        ctx = load_context(bundle)
        checks.append((
            "a run that never went through step 5 offers no statistics",
            available_stats_lags(ctx) == [], str(available_stats_lags(ctx))))
        checks.append((
            "and asking for its figures returns nothing rather than raising",
            available_stats_figures(ctx, "1000mslag") == [], ""))
    finally:
        bundle.close()
    return checks


def main() -> int:
    print("=" * 70)
    print("Statistics results in the report and the viewer")
    print("=" * 70)

    total_pass = total = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = _make_run(Path(tmp) / "run")
        result = _run_stats(root)
        lag = "25mslag"
        built = [
            ("Section A0 — the step produced a results folder:", [(
                "tables and figures written, nothing skipped",
                len(result.tables) > 5 and len(result.figures) > 5
                and not result.skipped,
                f"{len(result.tables)} tables, {len(result.figures)} figures, "
                f"skipped {result.skipped}")]),
            ("Section A1 — the figure catalogue:", _catalogue_checks(root, lag)),
            ("Section A2 — report captions:", _caption_checks(root, lag)),
            ("Section A3 — redrawing from the tables:", _redraw_checks(root, lag)),
            ("Section A4 — the bundle round trip:", _bundle_checks(root, lag)),
            ("Section A5 — the viewer:", _viewer_checks(root, lag)),
        ]
        for title, checks in built:
            p, n = _report(title, checks)
            total_pass += p
            total += n
        shutil.rmtree(root, ignore_errors=True)

    if BUNDLE.exists():
        p, n = _report("Section B — a run without statistics:", _real_bundle_checks())
        total_pass += p
        total += n
    else:
        print(f"\nSection B — SKIPPED (bundle not found at {BUNDLE})")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
