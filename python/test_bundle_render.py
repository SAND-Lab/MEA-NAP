"""Test express mode, the ``.meanap`` bundle, and redrawing figures from it.

Run from the repo root::

    uv run python python/test_bundle_render.py

The claim express mode makes is strong: *the figures it doesn't draw can be
drawn later, identically.* If that is off by so much as an axis limit, the
bundle is worse than useless — it looks right and isn't. So the load-bearing
check here is pixel equality between a figure the pipeline drew and the same
figure redrawn from the bundle alone.

Sections:

  A. bundle round-trip — write, open, and read back the manifest and params,
     including rejection of things that aren't bundles;
  B. reconstruction — ``adjMsub`` rebuilt from stored adjacency + active index
     matches what ``compute_network_metrics`` produced;
  C. **pixel parity** — full-mode run vs. render-from-bundle, byte-for-byte;
  D. vector output and styling overrides.

Everything runs on a small synthetic run; no example dataset or MATLAB needed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.store import (  # noqa: E402
    RecordingState, quantize_background, save_recording_state,
)
from meanap.params import PARAMS_FILENAME, Params  # noqa: E402
from meanap.pipeline.bundle import (  # noqa: E402
    BUNDLE_SUFFIX, build_manifest, open_bundle,
)
from meanap.pipeline.resume import CATNAP_SUFFIX  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

Check = tuple[str, bool, str]

N_UNITS = 24
LAG = 25


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


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _recordings() -> list[RecordingInfo]:
    return [RecordingInfo(filename="recA", div=21.0, group="WT"),
            RecordingInfo(filename="recB", div=21.0, group="KO")]


def _adjacency(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = rng.random((N_UNITS, N_UNITS))
    a = (a + a.T) / 2
    np.fill_diagonal(a, 0)
    return a


def _params(out_dir: Path, **kw) -> Params:
    p = Params(
        suite2p_mode=True, func_con_lag_val=[LAG], min_activity_level=0.0,
        min_number_of_nodes_to_cal_net_met=2, twop_subnetwork_analysis=False,
        num_2p_traces=0, twop_network_background=False,
        auto_set_cartography_boundaries=False, random_seed=11,
        output_data_folder=str(out_dir), start_analysis_step=4,
        prior_analysis=True,
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _seed_prior(tmp: Path, name: str = "Prior", lags: tuple[int, ...] = (LAG,)) -> Path:
    """A prior run holding just the step-2 state, ready to resume from.

    ``lags`` seeds one adjacency per STTC lag. More than one is what the
    across-lag figures need — a curve through a single point says nothing, so
    those sets aren't offered on a one-lag run.
    """
    from meanap.pipeline.output_folders import create_output_folders

    from meanap.catnap.subnetwork import CellTypeGroups

    prior = create_output_folders(tmp, name, ["WT", "KO"])
    # Half the cells excitatory, half inhibitory — enough for the by-cell-type
    # comparisons to have two series to separate.
    exc = np.zeros(N_UNITS, bool)
    exc[: N_UNITS // 2] = True
    masks = np.column_stack([exc, ~exc])
    markers = np.eye(N_UNITS, 2)
    for i, rec in enumerate(_recordings()):
        state = RecordingState(
            adjMs={f"adjM{lag}mslag": _adjacency(20 + i + 7 * j)
                   for j, lag in enumerate(lags)},
            coords=np.random.default_rng(i).random((N_UNITS, 2)) * 8.0,
            channels=np.arange(1, N_UNITS + 1),
            spike_counts=np.full(N_UNITS, 100.0),
            duration_s=600.0, plane0=Path("/nonexistent"),
            markers=(markers, ["NeuN+", "GAD+"]),
            groups=CellTypeGroups(
                names=["Excitatory", "Inhibitory"], masks=masks,
                marker_names=["NeuN+", "GAD+"], marker_matrix=markers,
                definitions={"Excitatory": "NeuN+ & ~GAD+", "Inhibitory": "GAD+"},
            ),
            coord_norm=(0.0, 511.0),
        )
        stats = {"FR": np.full(N_UNITS, 1.0), "FRactive": np.full(N_UNITS, 1.0),
                 "FRmean": 1.0, "numActiveElec": N_UNITS, "unitHeightMean": None}
        save_recording_state(
            prior / "ExperimentMatFiles" / f"{rec.filename}{CATNAP_SUFFIX}",
            state, stats)
    return prior


def _run(tmp: Path, name: str, *, express: bool,
         lags: tuple[int, ...] = (LAG,)) -> Path:
    """Resume a run from the seeded prior, in express or full mode."""
    from meanap.pipeline.runner import run_pipeline
    import pandas as pd

    prior = _seed_prior(tmp, f"{name}Prior", lags)
    sheet = tmp / f"{name}.csv"
    pd.DataFrame([{"Recording filename": r.filename, "DIV": r.div, "Group": r.group}
                  for r in _recordings()]).to_csv(sheet, index=False)

    p = _params(tmp, output_data_folder_name=name, express_mode=express,
                prior_analysis_path=str(prior),
                spreadsheet_file_name=str(sheet), spreadsheet_range="2:100",
                raw_data=str(tmp / "no-raw"), func_con_lag_val=list(lags))
    return run_pipeline(p, log=lambda m: None)


# ── Section A: bundle round-trip ──────────────────────────────────────────────


def _bundle_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = _run(tmp, "Express", express=True)
        bundle_path = root.with_suffix(BUNDLE_SUFFIX)

        checks.append(("express run writes a bundle", bundle_path.exists(), ""))
        checks.append(("bundle is a zip", zipfile.is_zipfile(bundle_path), ""))

        pngs = list(root.rglob("*.png"))
        checks.append(("express run drew no reconstructable figures",
                       not pngs, f"{[p.name for p in pngs]}"))

        with open_bundle(bundle_path) as b:
            checks.append(("manifest records the mode", b.mode == "catnap", b.mode))
            checks.append(("manifest records express", b.manifest["express"] is True, ""))
            checks.append(("manifest lists both recordings",
                           {r["filename"] for r in b.recordings} == {"recA", "recB"},
                           f"{b.recordings}"))
            checks.append(("manifest records the lag", b.lags == [LAG], f"{b.lags}"))
            checks.append(("params round-trip", b.params.random_seed == 11
                           and b.params.suite2p_mode, ""))
            checks.append(("no unknown param keys", b.unknown_param_keys == [],
                           f"{b.unknown_param_keys}"))
            checks.append(("bundle carries the resume state",
                           (b.root / "ExperimentMatFiles"
                            / f"recA{CATNAP_SUFFIX}").exists(), ""))
            checks.append(("bundle carries the metrics",
                           (b.root / "4_NetworkActivity"
                            / "netmet_results.json").exists(), ""))
            checks.append(("bundle carries params.json",
                           (b.root / PARAMS_FILENAME).exists(), ""))
            extracted = b.root

        checks.append(("closing cleans up the extracted copy",
                       not extracted.exists(), f"{extracted}"))

        # Not-a-bundle inputs must say so plainly.
        junk = tmp / f"junk{BUNDLE_SUFFIX}"
        junk.write_text("not a zip")
        try:
            open_bundle(junk)
            msg = ""
        except ValueError as e:
            msg = str(e)
        checks.append(("a non-zip is rejected clearly", "not a zip archive" in msg, msg[:60]))

        # A zip with no manifest is a zip, but not a bundle.
        plain = tmp / f"plain{BUNDLE_SUFFIX}"
        with zipfile.ZipFile(plain, "w") as zf:
            zf.writestr("hello.txt", "hi")
        try:
            open_bundle(plain)
            msg2 = ""
        except ValueError as e:
            msg2 = str(e)
        checks.append(("a zip without a manifest is rejected",
                       "not a" in msg2 and "bundle" in msg2, msg2[:60]))

        # A newer format must be refused, not half-read.
        newer = tmp / f"newer{BUNDLE_SUFFIX}"
        manifest = build_manifest(Params(), _recordings(), mode="catnap", lags=[LAG])
        manifest["format"] = 999
        with zipfile.ZipFile(newer, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
        try:
            open_bundle(newer)
            msg3 = ""
        except ValueError as e:
            msg3 = str(e)
        checks.append(("a newer format is refused with an upgrade hint",
                       "Update MEA-NAP" in msg3, msg3[:70]))

    return checks


def _zip_slip_checks() -> list[Check]:
    """A bundle is a file people email each other; it must not escape its dir."""
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        evil = Path(tmp) / f"evil{BUNDLE_SUFFIX}"
        manifest = build_manifest(Params(), [], mode="catnap", lags=[])
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("../escaped.txt", "pwned")
        try:
            open_bundle(evil)
            msg = ""
        except ValueError as e:
            msg = str(e)
        checks.append(("a traversal entry is refused", "outside" in msg, msg[:70]))
        checks.append(("nothing was written outside the temp dir",
                       not (Path(tmp).parent / "escaped.txt").exists(), ""))
    return checks


# ── Section B: reconstruction ─────────────────────────────────────────────────


def _reconstruction_checks() -> list[Check]:
    from meanap.pipeline.render import load_context
    from meanap.pipeline.step4 import compute_network_metrics

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = _run(tmp, "Express", express=True)
        with open_bundle(root.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)

            checks.append(("context finds both recordings",
                           set(ctx.recordings) == {"recA", "recB"},
                           f"{sorted(ctx.recordings)}"))
            checks.append(("context finds the lag", ctx.lags("recA") == [LAG],
                           f"{ctx.lags('recA')}"))

            # adjMsub must match what the pipeline computed, not merely exist.
            adj = _adjacency(20)
            expected = compute_network_metrics(
                adj, np.full(N_UNITS, 100.0), 600.0, 0.0, 2,
                exclude_edges_below_threshold=False,
                params=ctx.params, rng=np.random.default_rng(0),
            )["adjMsub"]
            got = ctx.results["recA"][f"{LAG}mslag"]["adjMsub"]
            checks.append(("adjMsub rebuilt exactly from stored adjacency",
                           np.array_equal(got, expected),
                           f"max diff {np.abs(got - expected).max() if got.shape == expected.shape else 'shape'}"))

            # Numeric metrics must come back as arrays, names as lists.
            nd = ctx.results["recA"][f"{LAG}mslag"]["ND"]
            checks.append(("numeric metrics restored as arrays",
                           isinstance(nd, np.ndarray), f"{type(nd)}"))
    return checks


# ── Section C: pixel parity ───────────────────────────────────────────────────


def _parity_checks() -> list[Check]:
    """The load-bearing check: same figure, drawn two ways, byte-identical."""
    from meanap.pipeline.render import available_figures, load_context, render_figure

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "Full", express=False)
        express = _run(tmp, "Express", express=True)

        with open_bundle(express.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)
            figs = available_figures(ctx, "recA", LAG)
            checks.append(("bundle advertises figures to redraw", len(figs) >= 5,
                           f"{len(figs)}"))

            out = tmp / "redrawn"
            pipeline_dir = (full / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                            / "WT" / "recA" / f"{LAG}mslag")

            compared = identical = 0
            mismatched: list[str] = []
            for spec in figs:
                original = pipeline_dir / f"{spec.name}.png"
                if not original.exists():
                    continue
                redrawn = render_figure(ctx, "recA", LAG, spec.name, out)
                compared += 1
                if _digest(original) == _digest(redrawn):
                    identical += 1
                else:
                    mismatched.append(spec.name)

            checks.append(("every advertised figure exists in the full run",
                           compared == len(figs), f"{compared}/{len(figs)}"))
            checks.append((f"redrawn figures are pixel-identical ({identical}/{compared})",
                           compared > 0 and identical == compared,
                           f"differ: {mismatched}"))

            # The batch-scaled variants share axes across recordings, so they
            # are the ones that break if batch_bounds isn't recomputed right.
            scaled = pipeline_dir / "2_scaled_MEA_NetworkPlot.png"
            if scaled.exists():
                redrawn = render_figure(ctx, "recA", LAG, "2_scaled_MEA_NetworkPlot", out)
                checks.append(("batch-scaled figure matches (pooled bounds recomputed)",
                               _digest(scaled) == _digest(redrawn), ""))
    return checks


# ── Section D: vector output and restyling ────────────────────────────────────


def _vector_checks() -> list[Check]:
    from meanap.pipeline.render import load_context, render_figure

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express = _run(tmp, "Express", express=True)
        with open_bundle(express.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)
            out = tmp / "vector"

            svg = render_figure(ctx, "recA", LAG, "2_MEA_NetworkPlot", out, fmt="svg")
            checks.append(("svg is written", svg.exists() and svg.suffix == ".svg",
                           f"{svg.name}"))
            head = svg.read_text(errors="ignore")[:400]
            checks.append(("svg really is vector markup", "<svg" in head, head[:60]))
            checks.append(("svg holds editable elements",
                           "<path" in svg.read_text(errors="ignore"), ""))

            pdf = render_figure(ctx, "recA", LAG, "2_MEA_NetworkPlot", out, fmt="pdf")
            checks.append(("pdf is written",
                           pdf.exists() and pdf.read_bytes()[:4] == b"%PDF", ""))

            # Restyling must change the picture without touching the bundle.
            # ``twop_auto_node_size`` drives node_size_scale, which is one of
            # the few styling inputs the spatial plotter actually consumes.
            png = render_figure(ctx, "recA", LAG, "2_MEA_NetworkPlot", out / "a")
            restyled = render_figure(ctx, "recA", LAG, "2_MEA_NetworkPlot", out / "b",
                                     overrides={"twop_auto_node_size":
                                                not ctx.params.twop_auto_node_size})
            checks.append(("an override changes the rendered figure",
                           _digest(png) != _digest(restyled), ""))
            checks.append(("the override did not mutate the context",
                           ctx.params.twop_auto_node_size
                           == Params().twop_auto_node_size, ""))

            try:
                render_figure(ctx, "recA", LAG, "2_MEA_NetworkPlot", out,
                              overrides={"not_a_real_param": 1})
                msg = ""
            except ValueError as e:
                msg = str(e)
            checks.append(("an unknown override is rejected",
                           "Unknown parameter override" in msg, msg[:60]))

            try:
                render_figure(ctx, "recA", LAG, "no_such_figure", out)
                msg2 = ""
            except ValueError as e:
                msg2 = str(e)
            checks.append(("an unknown figure name is rejected",
                           "not one of the figures" in msg2, msg2[:60]))
    return checks


def _style_checks() -> list[Check]:
    """The Network Viewer control set, driven through the bundle renderer."""
    from meanap.network_plot import (
        EDGE_THRESHOLD_METHODS, LAYOUT_OPTIONS, NetworkStyle,
    )
    from meanap.pipeline.render import (
        STYLE_KEYS, load_context, render_figure, style_from_overrides,
    )

    checks: list[Check] = []

    # The identity style must not perturb anything — this is what keeps the
    # pipeline's figures byte-stable while the plumbing exists.
    a = np.array([[0, .5, .1], [.5, 0, .9], [.1, .9, 0]])
    c = np.array([[0, 0], [1, 0], [0, 1]], float)
    adj, coords, thresh = NetworkStyle.pipeline_default().prepare(a, c)
    checks.append(("pipeline default is the identity transform",
                   np.array_equal(adj, a) and np.array_equal(coords, c)
                   and thresh == 0.0, f"thresh={thresh}"))
    checks.append(("no style requested → no NetworkStyle built",
                   style_from_overrides({"twop_auto_node_size": True}) is None, ""))
    checks.append(("a styling key builds a NetworkStyle",
                   isinstance(style_from_overrides({"colormap": "magma"}),
                              NetworkStyle), ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express = _run(tmp, "Express", express=True)
        with open_bundle(express.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)
            out = tmp / "styled"
            base = render_figure(ctx, "recA", LAG, "4_MEA_NetworkPlotNodedegree"
                                 "Participationcoefficient", out / "base")
            fig = "4_MEA_NetworkPlotNodedegreeParticipationcoefficient"

            # Every control must visibly change the figure. A knob that renders
            # identically is a knob that isn't wired up.
            variants = {
                "colormap": {"colormap": "magma"},
                "layout": {"layout": "Circular"},
                "max_edges": {"max_edges": 3},
                "edge threshold": {"edge_threshold_method": "Percentile",
                                   "edge_threshold": 99.0},
                "node size scale": {"node_size_scale": 3.0},
                "node scaling method": {"node_scaling_method": "Square"},
                "min node size": {"min_node_size": 2.0},
                "edge widths": {"min_edge_width": 2.0, "max_edge_width": 12.0},
            }
            for label, ov in variants.items():
                got = render_figure(ctx, "recA", LAG, fig, out / label, overrides=ov)
                checks.append((f"control changes the figure: {label}",
                               _digest(base) != _digest(got), f"{ov}"))

            checks.append(("every style key is covered by a control",
                           STYLE_KEYS <= {k for ov in variants.values() for k in ov}
                           | {"node_scaling_power"},
                           f"{sorted(STYLE_KEYS - {k for ov in variants.values() for k in ov})}"))
            checks.append(("layout options are the viewer's",
                           "Circular" in LAYOUT_OPTIONS
                           and "Percentile" in EDGE_THRESHOLD_METHODS, ""))

            # Styling and vector output must compose.
            svg = render_figure(ctx, "recA", LAG, fig, out / "svg", fmt="svg",
                                overrides={"colormap": "magma", "layout": "Circular"})
            checks.append(("styled vector output works",
                           svg.suffix == ".svg" and "<svg" in svg.read_text()[:400], ""))
    return checks


def _group_family_checks() -> list[Check]:
    """2B / 4B batch comparisons redrawn from the bundle, and pixel-checked."""
    from meanap.pipeline.render import (
        available_group_families, load_context, render_group_family,
    )

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "Full", express=False)
        express = _run(tmp, "Express", express=True)

        with open_bundle(express.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)
            fams = {f.key for f in available_group_families(ctx)}
            checks.append(("network + activity families are available",
                           {"network", "activity"} <= fams, f"{sorted(fams)}"))

            out = tmp / "groups"
            total_compared = total_identical = 0
            mismatched: list[str] = []
            for key in ("network", "activity"):
                written = render_group_family(ctx, key, out)
                checks.append((f"'{key}' family produced figures", len(written) > 0,
                               f"{len(written)}"))
                for path in written:
                    original = full / path.relative_to(out)
                    if not original.exists():
                        mismatched.append(f"missing original: {path.name}")
                        continue
                    total_compared += 1
                    if _digest(original) == _digest(path):
                        total_identical += 1
                    else:
                        mismatched.append(path.name)

            checks.append((f"group figures are pixel-identical "
                           f"({total_identical}/{total_compared})",
                           total_compared > 0 and total_identical == total_compared,
                           f"{mismatched[:4]}"))

            svg = render_group_family(ctx, "network", tmp / "groups_svg", fmt="svg")
            checks.append(("group families render as svg",
                           bool(svg) and all(p.suffix == ".svg" for p in svg),
                           f"{len(svg)}"))

            try:
                render_group_family(ctx, "nonsense", out)
                msg = ""
            except ValueError as e:
                msg = str(e)
            checks.append(("an unknown family is rejected",
                           "Unknown figure family" in msg, msg[:50]))
    return checks


def _cell_type_self_contained_checks() -> list[Check]:
    """Cell types must travel *in* the bundle, not via the spreadsheet.

    A bundle is shared with people who have neither the raw data nor the
    ``PutativeCellType_*`` spreadsheet. If the marker rings or the by-cell-type
    comparisons quietly reached back for that file, they would render fine on
    the machine that produced the bundle and be blank or wrong everywhere else
    — the worst kind of failure. So this deletes the spreadsheet outright
    before rendering, and demands pixel equality against the run that had it.
    """
    from meanap.catnap.store import load_recording_state
    from meanap.pipeline.render import load_context, render_figure, render_group_family

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "Full", express=False)
        express = _run(tmp, "Express", express=True)

        # The state carries markers and the resolved grouping.
        state, _ = load_recording_state(
            express / "ExperimentMatFiles" / f"recA{CATNAP_SUFFIX}", Path("."))
        checks.append(("markers stored in the bundle state",
                       state.markers is not None
                       and state.markers[1] == ["NeuN+", "GAD+"],
                       f"{None if state.markers is None else state.markers[1]}"))
        checks.append(("resolved groups stored in the bundle state",
                       state.groups is not None and state.groups.n_groups > 0,
                       f"{None if state.groups is None else state.groups.names}"))

        bundle_path = express.with_suffix(BUNDLE_SUFFIX)

        # Now make the world hostile: no spreadsheet, no raw data, and the
        # original output folder gone. Only the bundle survives.
        import shutil
        for stray in tmp.glob("*.csv"):
            stray.unlink()
        shutil.rmtree(express)
        checks.append(("spreadsheet and output folder removed",
                       not list(tmp.glob("*.csv")) and not express.exists(), ""))

        with open_bundle(bundle_path) as b:
            ctx = load_context(b)
            checks.append(("groups survive the round trip",
                           _groups_of(ctx, "recA") is not None, ""))

            out = tmp / "orphan"
            # The marker rings live on the spatial network plots.
            fig = "2_MEA_NetworkPlot"
            redrawn = render_figure(ctx, "recA", LAG, fig, out)
            original = (full / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                        / "WT" / "recA" / f"{LAG}mslag" / f"{fig}.png")
            checks.append(("network plot with marker rings is identical "
                           "without the spreadsheet",
                           _digest(original) == _digest(redrawn), ""))

            written = render_group_family(ctx, "cell_type", out)
            checks.append(("by-cell-type comparisons render with no spreadsheet",
                           len(written) > 0, f"{len(written)}"))
            same = sum(1 for p in written
                       if (full / p.relative_to(out)).exists()
                       and _digest(full / p.relative_to(out)) == _digest(p))
            checks.append((f"…and are pixel-identical ({same}/{len(written)})",
                           written and same == len(written), ""))
    return checks


def _groups_of(ctx, recording):
    from meanap.pipeline.render import _states

    entry = _states(ctx).get(recording)
    return None if entry is None else entry[0].groups


def _gallery_cache_checks() -> list[Check]:
    """Thumbnail resolution + caching: the gallery's cost model.

    A family is all-or-nothing — the group plotters emit a folder per call and
    can't be asked for one figure — so a gallery pays the whole render or none
    of it. These checks pin the two things that make that acceptable: the
    thumbnail resolution actually reduces cost, and the second view is free.
    """
    import time

    from meanap.pipeline.figure_output import (
        DEFAULT_THUMBNAIL_DPI, current_dpi, figure_dpi,
    )
    from meanap.pipeline.render import gallery, load_context, render_group_family
    from meanap.pipeline.render_cache import RenderCache, bundle_identity, cache_key

    checks: list[Check] = []

    # The override must be scoped, or one request's resolution leaks into the
    # next — the reason this is a ContextVar and not a module global.
    checks.append(("no override by default", current_dpi() is None, ""))
    with figure_dpi(96):
        inner = current_dpi()
    checks.append(("override applies inside the block", inner == 96, f"{inner}"))
    checks.append(("…and is restored after", current_dpi() is None, ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express = _run(tmp, "Express", express=True)
        bundle_path = express.with_suffix(BUNDLE_SUFFIX)

        with open_bundle(bundle_path) as b:
            ctx = load_context(b)

            full = render_group_family(ctx, "network", tmp / "full_dpi")
            thumb = render_group_family(ctx, "network", tmp / "thumb",
                                        dpi=DEFAULT_THUMBNAIL_DPI)
            checks.append(("same figure count at both resolutions",
                           len(full) == len(thumb), f"{len(full)} vs {len(thumb)}"))
            full_mb = sum(p.stat().st_size for p in full) / 1e6
            thumb_mb = sum(p.stat().st_size for p in thumb) / 1e6
            checks.append((f"thumbnails are smaller ({full_mb:.1f} → {thumb_mb:.1f} MB)",
                           thumb_mb < full_mb * 0.6, ""))

            # Caching: second call must not re-render.
            with RenderCache.in_temp() as cache:
                t0 = time.perf_counter()
                first, cached1 = gallery(ctx, "network", cache)
                t_first = time.perf_counter() - t0

                t0 = time.perf_counter()
                second, cached2 = gallery(ctx, "network", cache)
                t_second = time.perf_counter() - t0

                checks.append(("first view renders", not cached1 and len(first) > 0,
                               f"{len(first)}"))
                checks.append(("second view is a cache hit", cached2, ""))
                checks.append(("…and returns the same files",
                               [p.name for p in first] == [p.name for p in second], ""))
                checks.append((f"cache hit is far faster "
                               f"({t_first:.1f}s → {t_second * 1000:.0f}ms)",
                               t_second < t_first / 10, ""))

                # A different style must not collide with the cached entry.
                restyled, cached3 = gallery(ctx, "network", cache,
                                            overrides={"custom_grp_order": ["KO", "WT"]})
                checks.append(("a restyled view is a separate entry", not cached3, ""))

                # A partial render must not be served.
                key = cache_key(bundle_identity(ctx.root), "network",
                                fmt="png", dpi=DEFAULT_THUMBNAIL_DPI)
                (cache.path_for(key) / ".complete").unlink()
                checks.append(("an incomplete entry counts as a miss",
                               cache.get(key) is None, ""))

            # Identity is content-based, so a renamed copy still hits.
            import shutil
            twin = tmp / f"Renamed{BUNDLE_SUFFIX}"
            shutil.copy(bundle_path, twin)
            checks.append(("bundle identity follows content, not filename",
                           bundle_identity(bundle_path) == bundle_identity(twin), ""))
            twin.write_bytes(twin.read_bytes() + b"x")
            checks.append(("…and changes when the bytes change",
                           bundle_identity(bundle_path) != bundle_identity(twin), ""))
    return checks


def _palette_checks() -> list[Check]:
    """Age and group colours: presets, custom lists, and an unchanged default.

    The default is the load-bearing one. Every pixel-parity guarantee in this
    file rests on an unstyled render matching the pipeline's figure, so a
    ``ColorScheme()`` that shifted any colour would quietly break all of them.
    """
    import matplotlib.cm as cm

    from meanap.params import Params
    from meanap.pipeline.palette import (
        AGE_SCHEMES, GROUP_SCHEMES, ColorScheme, parse_colors,
    )
    from meanap.pipeline.plotting_step4 import _div_colors, _group_colors

    checks: list[Check] = []
    historical_groups = [
        (0.996, 0.670, 0.318), (0.780, 0.114, 0.114), (0.459, 0.000, 0.376),
        (0.027, 0.306, 0.659), (0.5, 0.5, 0.5),
    ]
    age_ok = all(
        _div_colors(n) == [tuple(cm.viridis(x)[:3]) for x in np.linspace(1, 0, n)]
        for n in (1, 2, 3, 5, 9)
    )
    checks.append(("the default age palette is still flipud(viridis)", age_ok, ""))
    group_ok = all(
        _group_colors(n) == [historical_groups[i % 5] for i in range(n)]
        for n in (1, 3, 5, 8)
    )
    checks.append(("the default group palette is still MATLAB's groupColors",
                   group_ok, ""))
    checks.append(("…and Params defaults resolve to that same scheme",
                   ColorScheme.from_params(Params()) == ColorScheme(), ""))

    checks.append(("every age scheme yields the requested number of colours",
                   all(len(ColorScheme(age_scheme=s).ages(4)) == 4
                       for s in AGE_SCHEMES), ""))
    checks.append(("every group scheme does too",
                   all(len(ColorScheme(group_scheme=s).groups(4)) == 4
                       for s in GROUP_SCHEMES), ""))
    checks.append(("a preset actually changes the colours",
                   ColorScheme(group_scheme="okabe-ito").groups(3)
                   != ColorScheme().groups(3), ""))
    checks.append(("age schemes are ordered, so first ≠ last",
                   ColorScheme(age_scheme="plasma").ages(3)[0]
                   != ColorScheme(age_scheme="plasma").ages(3)[-1], ""))
    # Endpoints only: a 256-entry lookup table rounds an interior sample to a
    # different index depending on which direction it is approached from, so
    # the middle of a reversed map is a neighbouring colour, not the same one.
    fwd = ColorScheme(age_scheme="viridis").ages(3)
    rev = ColorScheme(age_scheme="viridis_r").ages(3)
    checks.append(("_r swaps which end of the colormap the youngest age gets",
                   fwd[0] == rev[-1] and fwd[-1] == rev[0] and fwd != rev,
                   f"{fwd[0]} vs {rev[-1]}"))

    checks.append(("custom colours win over the scheme",
                   ColorScheme(group_scheme="tab10",
                               group_colors=["#ff0000"]).groups(1)
                   == [(1.0, 0.0, 0.0)], ""))
    checks.append(("…and cycle when there are fewer than there are groups",
                   ColorScheme(group_colors=["#ff0000", "#0000ff"]).groups(3)
                   == [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)], ""))
    checks.append(("a comma-separated string is accepted, as a text box gives it",
                   ColorScheme(age_colors="#ff0000, blue").ages(2)
                   == [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)], ""))
    checks.append(("names, hex-3 and hex-6 all parse",
                   len(parse_colors(["crimson", "#abc", "#1f77b4"])) == 3, ""))

    for bad, expect, name in [
        (dict(group_scheme="rainbow"), "Unknown group colour scheme", "group scheme"),
        (dict(age_scheme="jet"), "Unknown age colour scheme", "age scheme"),
        (dict(group_colors=["#zzzzzz"]), "is not a colour", "colour code"),
    ]:
        try:
            ColorScheme(**bad)
            message = ""
        except ValueError as e:
            message = str(e)
        checks.append((f"a bad {name} is refused at construction",
                       expect in message, message[:60]))
    return checks


def _palette_render_checks() -> list[Check]:
    """A scheme reaches the drawn figure, and the default leaves it untouched."""
    from meanap.pipeline.palette import ColorScheme
    from meanap.pipeline.render import load_context, render_comparison_figure

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express = _run(tmp, "Express", express=True)

        with open_bundle(express.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)

            def draw(name, **overrides):
                return render_comparison_figure(
                    ctx, "network", "recording", "age", "Dens", tmp / name,
                    lag=LAG, overrides=overrides or None)

            plain = draw("plain")
            same = draw("same", group_color_scheme="meanap")
            okabe = draw("okabe", group_color_scheme="okabe-ito")
            custom = draw("custom", group_colors=["#ff0000", "#00ff00"])
            ages = draw("ages", age_color_scheme="plasma")

            checks.append(("passing the default scheme changes nothing",
                           _digest(plain) == _digest(same), ""))
            checks.append(("a group preset changes the figure",
                           _digest(plain) != _digest(okabe), ""))
            checks.append(("custom group colours change the figure",
                           _digest(plain) != _digest(custom), ""))
            checks.append(("…and differ from the preset too",
                           _digest(custom) != _digest(okabe), ""))
            # This split colours by group, so the age scheme must not touch it —
            # a control that redraws when it has no business to would break the
            # render cache's promise that one address is one figure.
            checks.append(("the age scheme leaves a by-age split alone",
                           _digest(plain) == _digest(ages), ""))

            by_group = render_comparison_figure(
                ctx, "network", "recording", "group", "Dens", tmp / "bg", lag=LAG)
            by_group_plasma = render_comparison_figure(
                ctx, "network", "recording", "group", "Dens", tmp / "bgp", lag=LAG,
                overrides={"age_color_scheme": "plasma"})
            checks.append(("…but does change a by-group split, where ages are the x",
                           _digest(by_group) != _digest(by_group_plasma), ""))

            try:
                draw("bad", group_colors=["#zzzzzz"])
                message = ""
            except ValueError as e:
                message = str(e)
            checks.append(("a bad colour is refused before drawing",
                           "is not a colour" in message, message[:50]))

            # The scheme must survive into the folder-at-a-time path as well,
            # or the gallery families would disagree with the faceted ones.
            from meanap.pipeline.render import render_group_family
            fam_plain = render_group_family(ctx, "network", tmp / "famA")
            fam_okabe = render_group_family(
                ctx, "network", tmp / "famB",
                overrides={"group_color_scheme": "okabe-ito"})
            rel = Path("4_NetworkActivity/4B_GroupComparisons/4_RecordingsByAge"
                       f"/HalfViolinPlots/Lag{LAG}ms/Dens_byDIV.png")
            checks.append(("the family renderer honours the scheme too",
                           bool(fam_plain) and bool(fam_okabe)
                           and _digest(tmp / "famA" / rel)
                           != _digest(tmp / "famB" / rel), ""))
    return checks


def _one_comparison_checks() -> list[Check]:
    """One 4B figure at a time must equal the same figure drawn as a folder.

    The viewer's comparison tab is only worth having if selecting a metric
    shows the figure the pipeline would have written — not something close to
    it. Both paths call ``plot_half_violin_by_x`` through the same frames, and
    this holds them to that: every address rendered alone, byte-compared
    against the family render of the same run.
    """
    from meanap.pipeline.render import (
        comparison_lags, comparison_metrics, load_context,
        render_comparison_figure, render_group_family,
    )

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express = _run(tmp, "Express", express=True)

        with open_bundle(express.with_suffix(BUNDLE_SUFFIX)) as b:
            ctx = load_context(b)

            family_out = tmp / "family"
            written = {p.relative_to(family_out): p
                       for p in render_group_family(ctx, "network", family_out)}
            checks.append(("the family render produced the reference figures",
                           len(written) > 0, f"{len(written)}"))

            checks.append(("the lags are discoverable", comparison_lags(ctx) == [LAG],
                           f"{comparison_lags(ctx)}"))
            checks.append(("a lagless family reports no lags",
                           comparison_lags(ctx, "ephys_activity") == [], ""))

            rec_metrics = comparison_metrics("network", "recording")
            node_metrics = comparison_metrics("network", "node")
            checks.append(("both levels advertise metrics",
                           len(rec_metrics) > 10 and len(node_metrics) >= 5,
                           f"{len(rec_metrics)}/{len(node_metrics)}"))

            one_out = tmp / "single"
            compared = identical = missing = 0
            mismatched: list[str] = []
            for level, metrics in (("recording", rec_metrics), ("node", node_metrics)):
                for split in ("group", "age"):
                    for metric in metrics:
                        path = render_comparison_figure(
                            ctx, "network", level, split, metric, one_out, lag=LAG)
                        rel = path.relative_to(one_out)
                        reference = written.get(rel)
                        if reference is None:
                            missing += 1
                            mismatched.append(f"no family figure at {rel}")
                            continue
                        compared += 1
                        if _digest(reference) == _digest(path):
                            identical += 1
                        else:
                            mismatched.append(rel.as_posix())

            checks.append(("every address lands on a family figure's path",
                           missing == 0, f"{missing} unmatched: {mismatched[:2]}"))
            checks.append((f"single renders are pixel-identical ({identical}/{compared})",
                           compared > 0 and identical == compared,
                           f"differ: {mismatched[:3]}"))
            checks.append(("…and that covered both levels and both splits",
                           compared == 2 * (len(rec_metrics) + len(node_metrics)),
                           f"{compared}"))

            svg = render_comparison_figure(
                ctx, "network", "recording", "group", "Dens", tmp / "svg",
                lag=LAG, fmt="svg")
            checks.append(("a comparison figure renders as svg",
                           svg.suffix == ".svg" and svg.stat().st_size > 0, ""))

            # Every rejection a viewer can provoke, said in a way that names the
            # alternative — these are user-visible 400s, not internal asserts.
            def _refused(**kw) -> str:
                args = {"family": "network", "level": "recording", "split": "group",
                        "metric": "Dens", "lag": LAG, **kw}
                try:
                    render_comparison_figure(
                        ctx, args["family"], args["level"], args["split"],
                        args["metric"], tmp / "bad", lag=args["lag"])
                except ValueError as e:
                    return str(e)
                return ""

            checks.append(("an unknown family is refused",
                           "Unknown comparison family" in _refused(family="nope"), ""))
            checks.append(("an unknown level is refused",
                           "Unknown level" in _refused(level="cell"), ""))
            checks.append(("an unknown split is refused",
                           "Unknown split" in _refused(split="sideways"), ""))
            checks.append(("an unknown metric is refused, naming the level",
                           "recording-level metric" in _refused(metric="NotAMetric"), ""))
            checks.append(("a missing lag is refused, listing the ones that exist",
                           str(LAG) in _refused(lag=None), _refused(lag=None)[:60]))
            checks.append(("a lag the run doesn't have is refused",
                           "this run has" in _refused(lag=999), ""))
            checks.append(("passing a lag to a lagless family is refused",
                           "do not depend on the STTC lag"
                           in _refused(family="ephys_activity", metric="FRmean"), ""))
    return checks


def _comparison_frames_checks() -> list[Check]:
    """The extracted frame builders must feed both plotting paths identically.

    ``plot_step2_group_comparisons`` and ``render_comparison_figure`` now share
    ``ephys_comparison_frames``; this is the 2B half of the parity check, built
    without a bundle because the CAT-NAP fixture has no electrophysiology
    stats.
    """
    import json as _json

    from meanap.params import Params
    from meanap.pipeline.plotting_step2 import (
        EPHYS_NODE_METRICS, EPHYS_REC_METRICS, ephys_comparison_frames,
        plot_step2_group_comparisons,
    )
    from meanap.pipeline.plotting_step4 import netmet_comparison_frames
    from meanap.pipeline.render import RenderContext, render_comparison_figure

    checks: list[Check] = []
    recs = _recordings()
    n = 8
    # Recording-level entries must be scalars and node-level ones per-channel
    # arrays, as step 2 writes them — the plotter coerces a metric column with
    # float(), so a list parked in a recording-level column is a hard error.
    stats = {
        rec.filename: {
            "FR": list(np.linspace(1.0, 3.0, n) + i),
            "FRactive": list(np.linspace(1.0, 3.0, n) + i),
            "channelBurstRate": list(np.linspace(0.5, 2.0, n) + i),
            "FRmean": 2.0 + i, "FRmedian": 1.9 + i, "numActiveElec": n,
            "channelAveBurstRate": 1.2 + i,
        }
        for i, rec in enumerate(recs)
    }

    df_rec, df_node = ephys_comparison_frames(recs, stats)
    checks.append(("2B frames have one row per recording", len(df_rec) == len(recs),
                   f"{len(df_rec)}"))
    checks.append(("…and one node row per channel per recording",
                   len(df_node) == n * len(recs), f"{len(df_node)}"))
    checks.append(("…carrying the grouping columns",
                   {"FileName", "Grp", "DIV"} <= set(df_rec.columns), ""))
    checks.append(("2B frames carry no Lag column",
                   "Lag" not in df_rec.columns, ""))

    ordered_rec, _ = ephys_comparison_frames(recs, stats, ["KO", "WT"])
    checks.append(("a custom group order becomes an ordered categorical",
                   list(ordered_rec["Grp"].cat.categories) == ["KO", "WT"], ""))

    # The node frame is empty when no recording has per-channel data. The
    # ordering step used to raise KeyError on that frame rather than skip it.
    flat = {rec.filename: {"FRmean": 1.0} for rec in recs}
    empty_rec, empty_node = ephys_comparison_frames(recs, flat, ["KO", "WT"])
    checks.append(("an empty node frame doesn't break the group ordering",
                   not empty_rec.empty and empty_node.empty, ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # The step-2 plotter appends "2B_GroupComparisons" to whatever it is
        # given, and render_group_family hands it <root>/2_NeuronalActivity —
        # so mirror that, or the two paths can't be compared.
        folder_out = tmp / "folder"
        plot_step2_group_comparisons(recs, stats, folder_out / "2_NeuronalActivity")
        reference = {p.relative_to(folder_out): p for p in folder_out.rglob("*.png")}
        checks.append(("2B folder render produced figures", len(reference) > 0,
                       f"{len(reference)}"))

        root = tmp / "root"
        (root / "2_NeuronalActivity").mkdir(parents=True)
        with open(root / "2_NeuronalActivity" / "ephys_results.json", "w") as fh:
            _json.dump(stats, fh)
        ctx = RenderContext(
            params=Params(), recordings={r.filename: r for r in recs},
            results={}, batch_bounds={}, root=root, mode="ephys")

        one_out = tmp / "single"
        compared = identical = 0
        mismatched: list[str] = []
        for level, metrics in (("recording", EPHYS_REC_METRICS),
                               ("node", EPHYS_NODE_METRICS)):
            for split in ("group", "age"):
                for metric in metrics:
                    path = render_comparison_figure(
                        ctx, "ephys_activity", level, split, metric, one_out)
                    ref = reference.get(path.relative_to(one_out))
                    if ref is None:
                        mismatched.append(f"no folder figure at {path.relative_to(one_out)}")
                        continue
                    compared += 1
                    if _digest(ref) == _digest(path):
                        identical += 1
                    else:
                        mismatched.append(path.name)

        checks.append((f"2B single renders are pixel-identical ({identical}/{compared})",
                       compared > 0 and identical == compared and not mismatched,
                       f"{mismatched[:3]}"))

    # 4B frames: the same shape, plus the lag column the network family needs.
    results = {
        rec.filename: {f"{LAG}mslag": {"Dens": 0.3 + i, "ND": list(np.arange(n) + i)}}
        for i, rec in enumerate(recs)
    }
    net_rec, net_node = netmet_comparison_frames(recs, results)
    checks.append(("4B frames carry the Lag column",
                   list(net_rec["Lag"].unique()) == [f"{LAG}mslag"],
                   f"{list(net_rec['Lag'].unique())}"))
    checks.append(("…and one node row per channel per recording per lag",
                   len(net_node) == n * len(recs), f"{len(net_node)}"))
    return checks


def _ephys_render_checks() -> list[Check]:
    """The renderer must read electrophysiology output too, not just CAT-NAP.

    The two pipelines store their per-recording arrays differently — ephys in
    ``<rec>_adjM.npz`` (adjacency + channels, node positions derived from the
    channel layout), CAT-NAP in ``<rec>_catnap.npz`` (adjacency + explicit
    coordinates + cell types). The renderer takes whichever is present rather
    than branching on mode, so this checks the ephys shape end to end without
    needing a real ephys run.
    """
    import json as _json

    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.render import (
        available_figures, load_context, render_figure,
    )
    from meanap.pipeline.resume import ADJM_SUFFIX
    from meanap.pipeline.step4 import _convert_numpy, compute_network_metrics

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = create_output_folders(tmp, "Ephys", ["WT"])

        # Step 3's file shape: bare adjacency keys plus a `_raw` copy the
        # metrics were *not* computed from, and the channel list.
        n = 16
        adj = _adjacency(31)[:n, :n]
        channels = np.arange(1, n + 1)
        np.savez(root / "ExperimentMatFiles" / f"recE{ADJM_SUFFIX}",
                 channels=channels,
                 **{f"adjM{LAG}mslag": adj, f"adjM{LAG}mslag_raw": adj * 0.5})

        params = Params(channel_layout="MCS60", random_seed=5)
        metrics = compute_network_metrics(
            adj, np.full(n, 100.0), 600.0, 0.0, 2,
            exclude_edges_below_threshold=False, params=params,
            rng=np.random.default_rng(5))
        results = {"recE": {f"{LAG}mslag": {k: v for k, v in metrics.items()
                                            if k != "adjMsub"}}}
        with open(root / "4_NetworkActivity" / "netmet_results.json", "w") as fh:
            _json.dump(_convert_numpy(results), fh)
        import pandas as pd
        pd.DataFrame([{"FileName": "recE", "Grp": "WT", "DIV": 58, "Lag": f"{LAG}mslag"}]
                     ).to_csv(root / "4_NetworkActivity"
                              / "NetworkActivity_RecordingLevel.csv", index=False)
        from meanap.params import save_params
        save_params(params, root)

        ctx = load_context(root)
        checks.append(("ephys output loads as a render context",
                       ctx.mode == "ephys" and "recE" in ctx.recordings,
                       f"{ctx.mode}"))
        checks.append(("adjacency found in the _adjM.npz",
                       "adjMsub" in ctx.results["recE"][f"{LAG}mslag"], ""))
        got = ctx.results["recE"][f"{LAG}mslag"]["adjMsub"]
        checks.append(("…and it is the thresholded matrix, not the _raw copy",
                       np.allclose(got, metrics["adjMsub"]), ""))

        figs = available_figures(ctx, "recE", LAG)
        checks.append(("figures are offered for an ephys recording",
                       len(figs) >= 5, f"{len(figs)}"))
        checks.append(("the field-of-view figure is not offered (no projection)",
                       not any(f.name == "12_MeanImageAndNetwork" for f in figs), ""))

        out = tmp / "rendered"
        drawn = render_figure(ctx, "recE", LAG, "2_MEA_NetworkPlot", out)
        checks.append(("an ephys network plot renders",
                       drawn.exists() and drawn.stat().st_size > 5000,
                       f"{drawn.stat().st_size if drawn.exists() else 0}"))
        svg = render_figure(ctx, "recE", LAG, "2_MEA_NetworkPlot", out, fmt="svg")
        checks.append(("…and as svg", "<svg" in svg.read_text()[:400], ""))
        # Colour-map changes need a figure that *has* a colour metric —
        # 2_MEA_NetworkPlot draws flat cyan nodes, so it is deliberately
        # immune. Use the participation-coefficient plot instead.
        coloured = "4_MEA_NetworkPlotNodedegreeParticipationcoefficient"
        base = render_figure(ctx, "recE", LAG, coloured, out / "c")
        restyled = render_figure(ctx, "recE", LAG, coloured, out / "d",
                                 overrides={"colormap": "magma"})
        checks.append(("colour map applies on the ephys path",
                       _digest(base) != _digest(restyled), ""))
        moved = render_figure(ctx, "recE", LAG, "2_MEA_NetworkPlot", out / "e",
                              overrides={"layout": "Circular"})
        checks.append(("layout applies on the ephys path",
                       _digest(drawn) != _digest(moved), ""))

        # ── step-2 activity figures (rasters, heatmaps, burst detail) ────────
        from meanap.pipeline.io import save_spike_times_npz
        from meanap.pipeline.render import (
            available_activity_figures, render_activity_figure,
        )
        from meanap.pipeline.resume import SPIKE_SUBDIR
        from meanap.pipeline.step2 import convert_numpy

        checks.append(("no activity figures without spike times",
                       available_activity_figures(ctx, "recE") == [], ""))

        rng = np.random.default_rng(9)
        spike_times = {ch: np.sort(rng.uniform(0, 600, rng.integers(20, 200)))
                       for ch in range(n)}
        save_spike_times_npz(
            root / SPIKE_SUBDIR / "recE_spikes.npz",
            {ch: {"bior1p5": t} for ch, t in spike_times.items()},
            channels, 25000.0, duration_s=600.0)
        ephys = {
            "FR": np.array([len(t) / 600.0 for t in spike_times.values()]),
            "channelBurstRate": rng.random(n) * 5,
            "channelBurstDur": rng.random(n) * 200,
        }
        with open(root / "2_NeuronalActivity" / "ephys_results.json", "w") as fh:
            _json.dump(convert_numpy({"recE": ephys}), fh)

        ctx2 = load_context(root)
        figs = available_activity_figures(ctx2, "recE")
        names = {f.name for f in figs}
        checks.append(("activity figures appear once spikes + stats exist",
                       len(figs) >= 5, f"{len(figs)}"))
        checks.append(("the raster and burst detail are always offered",
                       {"3_Raster", "8_BurstDetectionInfo"} <= names, f"{sorted(names)}"))
        checks.append(("a heatmap with no metric is not offered",
                       "6_ISIwithinBurst_heatmap" not in names, f"{sorted(names)}"))

        act_out = tmp / "activity"
        raster = render_activity_figure(ctx2, "recE", "3_Raster", act_out)
        checks.append(("the raster renders",
                       raster.exists() and raster.stat().st_size > 5000,
                       f"{raster.stat().st_size if raster.exists() else 0}"))
        heat = render_activity_figure(ctx2, "recE", "2_Heatmap", act_out)
        checks.append(("a heatmap renders", heat.exists(), ""))
        svg2 = render_activity_figure(ctx2, "recE", "3_Raster", act_out, fmt="svg")
        checks.append(("activity figures render as svg",
                       "<svg" in svg2.read_text()[:400], ""))
        again = render_activity_figure(ctx2, "recE", "3_Raster", act_out / "b")
        checks.append(("rendering twice is deterministic",
                       _digest(raster) == _digest(again), ""))
        try:
            render_activity_figure(ctx2, "recE", "not_a_figure", act_out)
            msg = ""
        except ValueError as e:
            msg = str(e)
        checks.append(("an unknown activity figure is rejected",
                       "not one of the activity figures" in msg, msg[:60]))
    return checks


def _manifest_honesty_checks() -> list[Check]:
    """The manifest must not promise a figure the viewer cannot draw.

    A bundle is read by someone who wasn't there when it was made. If its
    manifest lists a family the renderer has no code for, they get a dead
    button and no explanation — worse than the manifest saying nothing. So the
    advertised set is asserted against what ``render`` actually implements.
    """
    from meanap.pipeline.bundle import (
        RECONSTRUCTABLE_FAMILIES, UNRECONSTRUCTABLE_FAMILIES,
    )
    from meanap.pipeline.render import GROUP_FAMILIES

    checks: list[Check] = []

    # Every group family the renderer implements must be advertised, under the
    # manifest's naming.
    implemented = {f.key for f in GROUP_FAMILIES}
    expected = {
        "network": "4B_group_comparisons",
        "activity": "2B_activity_comparisons",
        "ephys_activity": "2B_activity_comparisons",
        "cell_type": "cell_type_activity",
        "subnetwork": "cell_type_subnetwork_groups",
    }
    checks.append(("every implemented family has a manifest name",
                   implemented <= set(expected),
                   f"{sorted(implemented - set(expected))}"))
    advertised = set(RECONSTRUCTABLE_FAMILIES)
    mapped = {expected[k] for k in implemented if k in expected}
    checks.append(("every implemented family is advertised",
                   mapped <= advertised, f"{sorted(mapped - advertised)}"))
    per_recording = {"4A_individual_network", "2A_individual_activity",
                     "1B_spike_detection_checks", "3_edge_threshold_checks",
                     "cell_type_subnetwork_per_rec"}
    checks.append(("nothing is advertised that isn't implemented",
                   advertised - mapped <= per_recording,
                   f"{sorted(advertised - mapped - per_recording)}"))
    checks.append(("the two lists are disjoint",
                   not (advertised & set(UNRECONSTRUCTABLE_FAMILIES)),
                   f"{sorted(advertised & set(UNRECONSTRUCTABLE_FAMILIES))}"))

    with tempfile.TemporaryDirectory() as tmp:
        root = _run(Path(tmp), "Express", express=True)
        with open_bundle(root.with_suffix(BUNDLE_SUFFIX)) as b:
            checks.append(("the manifest records what it cannot rebuild",
                           set(b.manifest["not_reconstructable"])
                           == set(UNRECONSTRUCTABLE_FAMILIES), ""))
            checks.append(("can_reconstruct agrees with the manifest",
                           b.can_reconstruct("4B_group_comparisons")
                           and b.can_reconstruct("2A_individual_activity")
                           and b.can_reconstruct("cell_type_subnetwork_per_rec")
                           # Nothing is unreconstructable any more, so the
                           # negative case has to be a family that isn't real.
                           and not b.can_reconstruct("no_such_family"),
                           ""))
    return checks


def _background_checks() -> list[Check]:
    """Quantisation must be applied before plotting, or parity is unprovable."""
    checks: list[Check] = []
    rng = np.random.default_rng(3)
    img = rng.random((1280, 1280))
    q = quantize_background((img, (0.0, 8.0, 0.0, 8.0)))
    checks.append(("large projections are decimated",
                   max(q[0].shape) <= 1024, f"{q[0].shape}"))
    checks.append(("quantising is idempotent (stable across a save/load)",
                   np.array_equal(q[0], quantize_background(q)[0]), ""))
    checks.append(("extent is preserved", q[1] == (0.0, 8.0, 0.0, 8.0), f"{q[1]}"))
    small = quantize_background((np.ones((4, 4)), (0, 1, 0, 1)))
    checks.append(("a flat image doesn't divide by zero",
                   small is not None and np.isfinite(small[0]).all(), ""))
    checks.append(("None passes through", quantize_background(None) is None, ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("Express mode, .meanap bundles, and figure reconstruction")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [
        ("Section A1 — bundle round-trip:", _bundle_checks),
        ("Section A2 — hostile archives:", _zip_slip_checks),
        ("Section B — reconstructing derived state:", _reconstruction_checks),
        ("Section C — pixel parity with the pipeline:", _parity_checks),
        ("Section D1 — vector output and restyling:", _vector_checks),
        ("Section D2 — the Network Viewer control set:", _style_checks),
        ("Section D3 — 2B / 4B batch comparisons:", _group_family_checks),
        ("Section D3b — cell types without the spreadsheet:",
         _cell_type_self_contained_checks),
        ("Section D3c — one 4B comparison figure at a time:", _one_comparison_checks),
        ("Section D3e — age and group palettes:", _palette_checks),
        ("Section D3f — palettes reaching the figure:", _palette_render_checks),
        ("Section D3d — the shared comparison frames (2B):", _comparison_frames_checks),
        ("Section D4 — thumbnail resolution and caching:", _gallery_cache_checks),
        ("Section D5 — electrophysiology output:", _ephys_render_checks),
        ("Section D6 — manifest honesty:", _manifest_honesty_checks),
        ("Section D7 — mean-projection quantisation:", _background_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
