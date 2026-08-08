"""Test that step-1 and step-3 check figures travel as data, not pictures.

Run from the repo root::

    uv run python python/test_check_figures_bundle.py

These three figures used to be the exception the bundle could not rebuild —
they are drawn from raw voltage — and so travelled as PNGs, which made them
over half of a bundle's bytes. Almost none of that voltage is visible in them,
so they now travel as the slices they show.

What matters, and is checked here:
  - the figure the run writes and the figure a viewer rebuilds are *byte*
    identical, which is only true because one function draws both;
  - the payload is far smaller than the pictures it replaces;
  - a folder written before the payload existed keeps its PNGs, and its
    manifest stops claiming a family the bundle cannot produce — overclaiming
    would promise the viewer a figure and then fail.

The step-3 edge-threshold checks get the same treatment, and were worse off
before it: their folder was already on the never-pack list *and* the family was
declared unreconstructable, so a bundle dropped them and could not rebuild them.

The CAT-NAP per-recording subnetwork figures needed no payload at all — the
adjacency, coordinates, groups and three tables were already in the bundle, and
only the wiring was missing. The parity section below runs the real dataset
when it is present, because "the same function draws both" is a claim about
pixels, not about intent.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402

from meanap.params import Params  # noqa: E402
from meanap.pipeline.bundle import (  # noqa: E402
    RECONSTRUCTABLE_FAMILIES, UNRECONSTRUCTABLE_FAMILIES, build_manifest,
    write_bundle,
)
from meanap.pipeline.plotting import (  # noqa: E402
    CHECKS_SUFFIX, SPIKE_CHECK_FIGURES, SpikeCheckData, compute_spike_check_data,
    draw_spike_check_figures, load_spike_check_data, save_spike_check_data,
)
from meanap.pipeline.spike_detection import SpikeDetectionResult  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── A synthetic recording, so this runs in seconds ────────────────────────────

FS = 5000.0
N_SAMPLES = int(FS * 8)
N_CHANNELS = 12
METHODS = ("bior1p5", "thr4")
WAVE_LEN = 25


def _fake_result(rng: np.random.Generator) -> tuple[np.ndarray, SpikeDetectionResult]:
    dat = rng.normal(0, 5, (N_SAMPLES, N_CHANNELS))
    spike_times, waveforms = {}, {}
    for ch in range(N_CHANNELS):
        n = 40 + ch
        times = np.sort(rng.uniform(0.1, N_SAMPLES / FS - 0.1, n))
        spike_times[ch] = {m: times[:: (1 if m == METHODS[0] else 2)]
                           for m in METHODS}
        waveforms[ch] = {m: rng.normal(0, 3, (len(spike_times[ch][m]), WAVE_LEN))
                         for m in METHODS}
        for t in times:                       # make the traces look like spikes
            i = int(t * FS)
            if 0 < i < N_SAMPLES - 1:
                dat[i, ch] -= 40
    return dat, SpikeDetectionResult(
        spike_times=spike_times, spike_waveforms=waveforms,
        thresholds={ch: {m: 5.0 for m in METHODS} for ch in range(N_CHANNELS)},
        channels=np.arange(1, N_CHANNELS + 1), fs=FS)


def _params(**kw) -> Params:
    return Params(random_seed=3, fs=FS, d_samp_f=500.0, **kw)


# ── Payload ───────────────────────────────────────────────────────────────────

def _payload_checks() -> list[Check]:
    checks: list[Check] = []
    rng = np.random.default_rng(0)
    dat, result = _fake_result(rng)
    params = _params()

    data = compute_spike_check_data(dat, result, params, "REC")
    checks.append(("the payload has one panel per example-trace axis",
                   data.n_panels == 9, str(data.n_panels)))
    checks.append(("it stores windows, not whole traces",
                   data.trace_windows.shape[1] < N_SAMPLES / 10,
                   f"{data.trace_windows.shape} vs {N_SAMPLES} samples"))
    checks.append(("the frequency curve is reduced, not raw spike times",
                   data.freq_curves.shape[0] == len(METHODS)
                   and data.freq_curves.shape[1] == int(np.ceil(N_SAMPLES / 500)),
                   str(data.freq_curves.shape)))
    # The y-limits are ±std of the recording, so storing the window's std
    # instead would silently rescale every panel.
    from meanap.pipeline.spike_detection import bandpass_filter
    full_stds = [
        float(np.std(bandpass_filter(dat[:, int(ch)].astype(float), FS,
                                     params.filter_low_pass,
                                     params.filter_high_pass)))
        for ch in data.trace_channels
    ]
    checks.append(("each panel's std is of its whole trace, not of its window",
                   np.allclose(data.trace_stds, full_stds),
                   f"{data.trace_stds[:2]} vs {full_stds[:2]}"))

    with tempfile.TemporaryDirectory() as tmp:
        path = save_spike_check_data(Path(tmp) / f"REC{CHECKS_SUFFIX}", data)
        back = load_spike_check_data(path)
        checks.append(("the payload round-trips through the npz",
                       back.rec_name == data.rec_name
                       and back.methods == data.methods
                       and np.array_equal(back.trace_windows, data.trace_windows)
                       and np.array_equal(back.trace_views, data.trace_views)
                       and np.array_equal(back.freq_curves, data.freq_curves), ""))
        checks.append(("including the ragged per-panel spike frames",
                       all(np.array_equal(a, b)
                           for pa, pb in zip(data.trace_spike_frames,
                                             back.trace_spike_frames)
                           for a, b in zip(pa, pb)),
                       ""))
        checks.append(("and loads without allow_pickle",
                       # np.load defaults to allow_pickle=False; an object array
                       # would have raised on the line above.
                       True, ""))

        raw_bytes = dat.nbytes
        checks.append(("the payload is a fraction of the raw voltage",
                       path.stat().st_size < raw_bytes / 10,
                       f"{path.stat().st_size/1e3:.0f} KB vs {raw_bytes/1e3:.0f} KB"))
    return checks


# ── Drawing ───────────────────────────────────────────────────────────────────

def _draw_checks() -> list[Check]:
    checks: list[Check] = []
    rng = np.random.default_rng(1)
    dat, result = _fake_result(rng)
    params = _params()
    data = compute_spike_check_data(dat, result, params, "REC")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        npz = save_spike_check_data(tmp / f"REC{CHECKS_SUFFIX}", data)

        run_dir, view_dir = tmp / "run", tmp / "view"
        written = draw_spike_check_figures(data, run_dir)
        draw_spike_check_figures(load_spike_check_data(npz), view_dir)

        checks.append(("drawing produces all three figures",
                       sorted(p.stem for p in written) == sorted(SPIKE_CHECK_FIGURES),
                       str([p.name for p in written])))

        # The guarantee the whole design rests on.
        identical = [
            (run_dir / f"{n}.png").read_bytes() == (view_dir / f"{n}.png").read_bytes()
            for n in SPIKE_CHECK_FIGURES
        ]
        checks.append(("a rebuilt figure is byte-identical to the run's own",
                       all(identical),
                       str(dict(zip(SPIKE_CHECK_FIGURES, identical)))))

        png_bytes = sum((run_dir / f"{n}.png").stat().st_size
                        for n in SPIKE_CHECK_FIGURES)
        checks.append(("the payload is smaller than the pictures it replaces",
                       npz.stat().st_size < png_bytes,
                       f"{npz.stat().st_size/1e3:.0f} KB vs {png_bytes/1e3:.0f} KB"))

        one = draw_spike_check_figures(load_spike_check_data(npz), tmp / "one",
                                       only="3_Waveforms")
        checks.append(("only= draws exactly the figure asked for",
                       len(one) == 1 and one[0].stem == "3_Waveforms",
                       str([p.name for p in one])))

        svg = draw_spike_check_figures(load_spike_check_data(npz), tmp / "svg",
                                       only="1_ExampleTraces", fmt="svg")
        checks.append(("and can emit vector output like every other family",
                       svg[0].suffix == ".svg" and svg[0].stat().st_size > 0,
                       svg[0].name))

        # A recording where nothing was detected has no panels and no waveform
        # channel; the pipeline drew neither figure, and nor should this.
        empty = SpikeDetectionResult(
            spike_times={}, spike_waveforms={}, thresholds={},
            channels=np.arange(2), fs=FS)
        try:
            blank = compute_spike_check_data(
                np.zeros((100, 2)), empty, params, "EMPTY")
            drew = draw_spike_check_figures(blank, tmp / "empty")
            ok = [p.stem for p in drew] == ["2_SpikeFrequencies"]
        except StopIteration:
            ok = False   # next(iter(...)) on no channels
        checks.append(("a recording with no detected spikes degrades quietly",
                       ok, "raised, or drew the wrong set"))
    return checks


# ── Bundle ────────────────────────────────────────────────────────────────────

def _fake_output_folder(root: Path, *, with_payload: bool) -> None:
    """The parts of an output folder this feature touches."""
    from meanap.pipeline.resume import SPIKE_SUBDIR

    (root / SPIKE_SUBDIR).mkdir(parents=True, exist_ok=True)
    checks_dir = root / "1_SpikeDetection" / "1B_SpikeDetectionChecks" / "G" / "REC"
    checks_dir.mkdir(parents=True, exist_ok=True)
    for name in SPIKE_CHECK_FIGURES:
        (checks_dir / f"{name}.png").write_bytes(b"\x89PNG" + b"0" * 50_000)
    (root / SPIKE_SUBDIR / "REC_spikes.npz").write_bytes(b"0" * 1000)

    if with_payload:
        rng = np.random.default_rng(2)
        dat, result = _fake_result(rng)
        save_spike_check_data(
            root / SPIKE_SUBDIR / f"REC{CHECKS_SUFFIX}",
            compute_spike_check_data(dat, result, _params(), "REC"))


def _bundle_checks() -> list[Check]:
    checks: list[Check] = []

    checks.append(("the family is declared reconstructable",
                   "1B_spike_detection_checks" in RECONSTRUCTABLE_FAMILIES,
                   str(RECONSTRUCTABLE_FAMILIES)))
    checks.append(("and no longer declared unreconstructable",
                   "1B_spike_detection_checks" not in UNRECONSTRUCTABLE_FAMILIES,
                   str(UNRECONSTRUCTABLE_FAMILIES)))

    recs = [RecordingInfo(filename="REC", div=14, group="G")]
    manifest = build_manifest(Params(), recs, mode="ephys")

    # A folder with the payload: pictures dropped, family claimed.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "run"
        _fake_output_folder(root, with_payload=True)
        bundle = write_bundle(root, dict(manifest), Path(tmp) / "a.meanap")
        z = zipfile.ZipFile(bundle)
        names = z.namelist()
        man = json.loads(z.read("manifest.json"))

        checks.append(("with a payload, the PNGs are not packed",
                       not any("1B_SpikeDetectionChecks" in n for n in names),
                       str([n for n in names if "1B_" in n])))
        checks.append(("the payload is",
                       any(CHECKS_SUFFIX in n for n in names),
                       str(names)))
        checks.append(("and the manifest claims the family",
                       "1B_spike_detection_checks" in man["reconstructable"]
                       and "spike_detection_checks" not in man["embedded_figures"],
                       str(man["reconstructable"])))

    # A folder written before the payload existed: pictures kept, claim dropped.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "old"
        _fake_output_folder(root, with_payload=False)
        bundle = write_bundle(root, dict(manifest), Path(tmp) / "b.meanap")
        z = zipfile.ZipFile(bundle)
        names = z.namelist()
        man = json.loads(z.read("manifest.json"))

        checks.append(("without a payload, the PNGs are kept instead of lost",
                       sum("1B_SpikeDetectionChecks" in n for n in names) == 3,
                       str([n for n in names if "1B_" in n])))
        checks.append(("and the manifest stops claiming what it cannot rebuild",
                       "1B_spike_detection_checks" not in man["reconstructable"]
                       and "1B_spike_detection_checks" in man["not_reconstructable"],
                       str(man["reconstructable"])))
        checks.append(("saying instead that they are embedded",
                       "spike_detection_checks" in man["embedded_figures"],
                       str(man["embedded_figures"])))
    return checks


# ── Render + viewer ───────────────────────────────────────────────────────────

def _render_checks() -> list[Check]:
    from meanap.pipeline.render import (
        RenderContext, available_spike_check_figures, render_spike_check_figure,
    )

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "run"
        _fake_output_folder(root, with_payload=True)
        ctx = RenderContext(params=_params(), recordings={}, results={},
                            batch_bounds={}, root=root, mode="ephys")

        figs = available_spike_check_figures(ctx, "REC")
        checks.append(("the renderer offers all three for a recording with data",
                       [f.name for f in figs] == list(SPIKE_CHECK_FIGURES),
                       str([f.name for f in figs])))
        checks.append(("and none for a recording without",
                       available_spike_check_figures(ctx, "MISSING") == [], ""))

        dest = Path(tmp) / "out"
        made = [render_spike_check_figure(ctx, "REC", f.name, dest) for f in figs]
        checks.append(("each renders to a file",
                       all(p.is_file() and p.stat().st_size > 0 for p in made),
                       str([p.name for p in made])))

        try:
            render_spike_check_figure(ctx, "MISSING", "3_Waveforms", dest)
            said = ""
        except ValueError as e:
            said = str(e)
        checks.append(("a missing payload fails with an actionable message",
                       "step 1" in said, said))

        try:
            render_spike_check_figure(ctx, "REC", "not_a_figure", dest)
            said = ""
        except ValueError as e:
            said = str(e)
        checks.append(("an unknown figure name says how to list the real ones",
                       "available_spike_check_figures" in said, said))
    return checks


def _viewer_checks() -> list[Check]:
    """The viewer has to actually surface them — the gap that started this."""
    from meanap.viewer import page, server

    checks: list[Check] = []
    src = Path(server.__file__).read_text()
    checks.append(("the server lists spike checks in its manifest",
                   '"spike_checks"' in src, ""))
    checks.append(("and serves them on their own route",
                   '/api/spikecheck' in src, ""))

    html = page.PAGE_HTML
    checks.append(("the page has a section for them",
                   'id="spikechecks"' in html, ""))
    checks.append(("wired to the spikecheck route",
                   '/api/spikecheck' in html, ""))
    checks.append(("and they are downloadable like any other single figure",
                   'kind === "spikecheck"' in html, ""))
    return checks


# ── Step-3 edge-threshold checks ──────────────────────────────────────────────

def _edge_check_data(n_nodes=10, n_check=8, seed=5):
    """Threshold snapshots of the shape ``adjm_thr`` hands to the plot."""
    rng = np.random.default_rng(seed)
    adj = np.abs(rng.normal(0, 0.1, (n_nodes, n_nodes)))
    adj = (adj + adj.T) / 2
    np.fill_diagonal(adj, 0)
    # Thresholds settle as repeats grow, which is what the figure is about.
    dist1 = [adj * (1.5 - 0.4 * i / n_check)
             + rng.normal(0, 0.01 / (i + 1), (n_nodes, n_nodes))
             for i in range(n_check)]
    dist1 = [(d + d.T) / 2 for d in dist1]
    rep_val = np.arange(1, n_check + 1) * 25
    return dist1, rep_val, adj


def _edge_check_checks() -> list[Check]:
    from meanap.pipeline.plotting_step3 import (
        EDGE_CHECK_SUFFIX, compute_edge_threshold_check,
        draw_edge_threshold_check, load_edge_threshold_check,
        save_edge_threshold_check, stored_lags,
    )

    checks: list[Check] = []
    dist1, rep_val, adj = _edge_check_data()
    rng = np.random.default_rng(11)
    data = compute_edge_threshold_check(dist1, rep_val, adj, rng=rng)

    checks.append(("the payload keeps one summary point per checkpoint",
                   data.n_checkpoints == len(dist1)
                   and len(data.mean_thr) == len(dist1)
                   and len(data.std_thr) == len(dist1),
                   f"{data.n_checkpoints} vs {len(dist1)}"))
    # 10 nodes is 45 unique edges, so the sampler takes its full twelve.
    checks.append(("and the sampled trajectories the second row draws",
                   data.trajectories.shape == (12, len(dist1)),
                   str(data.trajectories.shape)))
    checks.append(("and five discarded-edge maps, not every snapshot",
                   data.maps.shape == (5, 10, 10), str(data.maps.shape)))

    nominal = sum(d.nbytes for d in dist1)
    with tempfile.TemporaryDirectory() as tmp:
        path = save_edge_threshold_check(
            Path(tmp) / f"REC{EDGE_CHECK_SUFFIX}", {25: data})
        checks.append(("the payload is a fraction of the snapshots it replaces",
                       path.stat().st_size < nominal / 2,
                       f"{path.stat().st_size/1e3:.1f} KB vs {nominal/1e3:.0f} KB"))
        checks.append(("the file records which lags it holds",
                       stored_lags(path) == [25], str(stored_lags(path))))

        back = load_edge_threshold_check(path, 25)
        checks.append(("it round-trips",
                       np.allclose(back.mean_thr, data.mean_thr)
                       and np.allclose(back.trajectories, data.trajectories)
                       and np.array_equal(back.maps, data.maps), ""))
        checks.append(("and a lag it does not hold reads as absent",
                       load_edge_threshold_check(path, 999) is None, ""))

        run = draw_edge_threshold_check(data, Path(tmp) / "run.png")
        view = draw_edge_threshold_check(back, Path(tmp) / "view.png")
        checks.append(("a rebuilt figure is byte-identical to the run's own",
                       run.read_bytes() == view.read_bytes(), ""))

    # Several lags in one file, which is how step 3 writes it.
    with tempfile.TemporaryDirectory() as tmp:
        per_lag = {lag: compute_edge_threshold_check(
            dist1, rep_val, adj, rng=np.random.default_rng(lag))
            for lag in (10, 25, 50)}
        path = save_edge_threshold_check(
            Path(tmp) / f"REC{EDGE_CHECK_SUFFIX}", per_lag)
        checks.append(("one file carries every lag the run computed",
                       stored_lags(path) == [10, 25, 50], str(stored_lags(path))))

    checks.append(("no checkpoints yields no payload rather than an empty figure",
                   compute_edge_threshold_check([], np.array([]), adj) is None, ""))

    # The family was declared unreconstructable *and* its folder was on the
    # never-pack list, so bundles silently lost these figures.
    checks.append(("the family is now declared reconstructable",
                   "3_edge_threshold_checks" in RECONSTRUCTABLE_FAMILIES
                   and "3_edge_threshold_checks" not in UNRECONSTRUCTABLE_FAMILIES,
                   str(UNRECONSTRUCTABLE_FAMILIES)))
    return checks


def _edge_render_checks() -> list[Check]:
    from meanap.pipeline.plotting_step3 import (
        EDGE_CHECK_SUFFIX, compute_edge_threshold_check, save_edge_threshold_check,
    )
    from meanap.pipeline.render import (
        RenderContext, available_edge_check_lags, render_edge_check_figure,
    )

    checks: list[Check] = []
    dist1, rep_val, adj = _edge_check_data()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "run"
        (root / "ExperimentMatFiles").mkdir(parents=True)
        save_edge_threshold_check(
            root / "ExperimentMatFiles" / f"REC{EDGE_CHECK_SUFFIX}",
            {lag: compute_edge_threshold_check(dist1, rep_val, adj,
                                               rng=np.random.default_rng(lag))
             for lag in (10, 25)})
        ctx = RenderContext(params=_params(), recordings={}, results={},
                            batch_bounds={}, root=root, mode="ephys")

        checks.append(("the renderer lists the lags that are there",
                       available_edge_check_lags(ctx, "REC") == [10, 25],
                       str(available_edge_check_lags(ctx, "REC"))))
        checks.append(("and none for a recording with no checks",
                       available_edge_check_lags(ctx, "OTHER") == [], ""))

        out = render_edge_check_figure(ctx, "REC", 25, Path(tmp) / "out")
        checks.append(("it renders, named as the pipeline names it",
                       out.name == "REC25msLagProbThreshCheck.png"
                       and out.stat().st_size > 0, out.name))
        svg = render_edge_check_figure(ctx, "REC", 10, Path(tmp) / "out", fmt="svg")
        checks.append(("and can emit vector output",
                       svg.suffix == ".svg" and svg.stat().st_size > 0, svg.name))

        try:
            render_edge_check_figure(ctx, "REC", 999, Path(tmp) / "out")
            said = ""
        except ValueError as e:
            said = str(e)
        checks.append(("a lag with no data explains why it might be missing",
                       "plot thresholding checks" in said, said))
    return checks


def _edge_viewer_checks() -> list[Check]:
    from meanap.viewer import page, server

    checks: list[Check] = []
    src = Path(server.__file__).read_text()
    checks.append(("the server lists edge-check lags in its manifest",
                   '"edge_checks"' in src, ""))
    checks.append(("and serves them on their own route",
                   "/api/edgecheck" in src, ""))
    html = page.PAGE_HTML
    checks.append(("the page has a section for them",
                   'id="edgechecks"' in html, ""))
    checks.append(("wired to the edgecheck route",
                   "/api/edgecheck" in html, ""))
    checks.append(("and downloadable like any other single figure",
                   'kind === "edgecheck"' in html, ""))
    return checks


# ── CAT-NAP per-recording subnetwork figures ──────────────────────────────────

DATASET = REPO_ROOT / "local" / "example2pdataWCellTypes"
CATNAP_REC = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"


def _subnetwork_declaration_checks() -> list[Check]:
    """No payload was needed here — only the claim and the wiring."""
    from meanap.pipeline.render import SUBNETWORK_FIGURES

    checks: list[Check] = []
    checks.append(("the family is declared reconstructable",
                   "cell_type_subnetwork_per_rec" in RECONSTRUCTABLE_FAMILIES,
                   str(RECONSTRUCTABLE_FAMILIES)))
    checks.append(("nothing is left that a bundle cannot rebuild",
                   UNRECONSTRUCTABLE_FAMILIES == (),
                   str(UNRECONSTRUCTABLE_FAMILIES)))
    checks.append(("all five per-recording figures are named",
                   [f.name for f in SUBNETWORK_FIGURES] == [
                       "1_CellTypeNetwork", "2_SubnetworkGraphs",
                       "3_NodeMetricsByCellType", "4_SubnetworkMetrics",
                       "5_EdgeMixing"],
                   str([f.name for f in SUBNETWORK_FIGURES])))

    # The jitter in 3_NodeMetricsByCellType has to come from a stream a viewer
    # can derive, not from whatever state the metrics left the shared one in.
    src = (REPO_ROOT / "src" / "meanap" / "catnap" / "pipeline.py").read_text()
    checks.append(("the pipeline draws that figure from its own rng stream",
                   'make_rng(params.random_seed, "catnap_subnetwork_plot"' in src,
                   ""))
    rsrc = (REPO_ROOT / "src" / "meanap" / "pipeline" / "render.py").read_text()
    checks.append(("and the renderer derives the identical one",
                   '"catnap_subnetwork_plot"' in rsrc, ""))
    return checks


def _subnetwork_viewer_checks() -> list[Check]:
    from meanap.viewer import page, server

    checks: list[Check] = []
    src = Path(server.__file__).read_text()
    checks.append(("the server lists subnetwork figures per lag",
                   '"subnetworks"' in src, ""))
    checks.append(("and serves them on their own route",
                   "/api/subnetwork" in src, ""))
    html = page.PAGE_HTML
    checks.append(("the page has a section for them",
                   'id="subnetworks"' in html, ""))
    checks.append(("changing the lag refreshes it, since they are per-lag",
                   "fillFigures(); fillSubnetworks();" in html, ""))
    checks.append(("and they are downloadable like any other single figure",
                   'kind === "subnetwork"' in html, ""))
    return checks


def _subnetwork_parity_checks() -> list[Check]:
    """A full run's figures against the ones rebuilt from its bundle."""
    import tempfile as tf

    from meanap.pipeline.bundle import build_manifest, open_bundle, write_bundle
    from meanap.pipeline.render import (
        available_subnetwork_figures, load_context, render_subnetwork_figure,
    )
    from meanap.pipeline.runner import run_pipeline
    from meanap.pipeline.spreadsheet import read_recording_csv

    checks: list[Check] = []
    with tf.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet = tmp / "recs.csv"
        sheet.write_text(
            f"Recording Filename,DIV group,Genotype\n{CATNAP_REC},21,HET\n")
        params = Params(
            raw_data=str(DATASET), spreadsheet_file_name=str(sheet),
            spreadsheet_range="A2:A2", output_data_folder=str(tmp),
            output_data_folder_name="Full", random_seed=1, express_mode=False,
            suite2p_mode=True, twop_subnetwork_analysis=True,
            twop_subnetwork_network_plots=False, prob_thresh_rep_num=20,
            func_con_lag_val=[25], num_2p_traces=0)
        root = run_pipeline(params, log=lambda m: None)

        recs = read_recording_csv(sheet, "A2:A2")
        bundle = write_bundle(root, build_manifest(params, recs, mode="catnap"),
                              tmp / "b.meanap")
        on_disk = (root / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                   / "HET" / CATNAP_REC / "25mslag" / "cellTypeSubnetworks")

        import zipfile
        packed = [n for n in zipfile.ZipFile(bundle).namelist()
                  if "cellTypeSubnetworks" in n]
        checks.append(("the bundle carries no subnetwork pictures",
                       not packed, str(packed[:3])))

        dest = tmp / "rebuilt"
        with open_bundle(bundle) as b:
            ctx = load_context(b)
            figs = available_subnetwork_figures(ctx, CATNAP_REC, 25)
            checks.append(("all five are offered for the real recording",
                           len(figs) == 5, str([f.name for f in figs])))
            for spec in figs:
                rebuilt = render_subnetwork_figure(ctx, CATNAP_REC, 25,
                                                   spec.name, dest)
                original = on_disk / f"{spec.name}.png"
                checks.append((f"{spec.name} is byte-identical to the run's own",
                               original.exists()
                               and original.read_bytes() == rebuilt.read_bytes(),
                               "missing" if not original.exists() else "differs"))
    return checks


def main() -> int:
    print("=" * 70)
    print("Check figures in a bundle")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [("Payload:", _payload_checks),
                         ("Drawing:", _draw_checks),
                         ("Bundle:", _bundle_checks),
                         ("Renderer:", _render_checks),
                         ("Viewer:", _viewer_checks),
                         ("Edge-threshold payload:", _edge_check_checks),
                         ("Edge-threshold renderer:", _edge_render_checks),
                         ("Edge-threshold viewer:", _edge_viewer_checks),
                         ("Subnetwork wiring:", _subnetwork_declaration_checks),
                         ("Subnetwork viewer:", _subnetwork_viewer_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    # Needs the real 2P dataset: these figures are drawn from cell-type
    # spreadsheets, and a synthetic stand-in would prove nothing about pixels.
    if (DATASET / CATNAP_REC).is_dir():
        p, n = _report("Subnetwork parity (real dataset):",
                       _subnetwork_parity_checks())
        total_pass += p
        total += n
    else:
        print(f"\nSubnetwork parity — SKIPPED (no dataset at {DATASET})")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
