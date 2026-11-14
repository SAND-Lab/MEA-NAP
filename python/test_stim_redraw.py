"""Stimulation figures redrawn from what the run saved (meanap.stim.redraw).

The stim step saves the inputs of every per-recording stim figure, then draws
the figures from that saved copy. The viewer draws them from the same copy in
a bundle. These tests check, on a small synthetic recording:

* the figures drawn from the saved payloads are pixel-identical to the ones
  the step wrote;
* a bundle leaves those pictures out, and keeps the payloads;
* the viewer lists and serves them, and falls back to the packed pictures of
  a run from before the payloads existed;
* an ephys run's figures are not mistaken for calcium imaging traces.

    .venv/bin/python -m pytest python/test_stim_redraw.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

EVENTS = np.arange(1.0, 61.0, 2.0)          # 30 stimuli, on electrode 13
T = 62.0
CHANNELS = np.array([11, 12, 13, 14, 15, 16, 17, 18])
REC = "recA"


def _spikes(seed=0):
    """Background firing, plus a response 5-50 ms after each stimulus on half the nodes."""
    rng = np.random.default_rng(seed)
    trains = [rng.uniform(0, T, rng.poisson(3 * T)) for _ in CHANNELS]
    for e in EVENTS:
        for j in (0, 1, 3, 4):
            trains[j] = np.r_[trains[j], e + rng.uniform(0.005, 0.05, rng.poisson(3))]
    return [np.sort(t) for t in trains]


def _run(root: Path):
    """The electrical path's figure-writing steps, on synthetic data, into *root*."""
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import _electrical_events, _stim_figures, _stim_networks
    from meanap.stim.detection import get_stim_patterns
    from meanap.stim.events import stim_info_without_stim_nodes
    from meanap.stim.sequences import conditions_from_patterns

    params = Params(stim_network_rep_num=40, func_con_lag_val=[10])
    rec = RecordingInfo(REC, 14, "WT")
    coords = np.c_[np.arange(len(CHANNELS)) % 4, np.arange(len(CHANNELS)) // 4].astype(float)
    stim_info = stim_info_without_stim_nodes(CHANNELS, coords)
    stim_info[2].elec_stim_times = EVENTS.copy()
    stim_info[2].elec_stim_dur = np.full(EVENTS.size, 1e-4)
    sp = {**params.to_stim_params_dict(), "fs": 25000.0}
    stim_info, patterns = get_stim_patterns(stim_info, sp)
    conditions = conditions_from_patterns(stim_info, patterns)
    method = params.spikes_method
    trains = _spikes()
    trains[2] = np.array([])                      # the stimulating electrode
    spikes = {c: {method: t} for c, t in enumerate(trains)}
    dest = root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / "WT" / REC
    dest.mkdir(parents=True)
    info = {"FileName": REC, "Grp": "WT", "DIV": 14, "FN": [REC], "duration_s": T}
    log = lambda *_: None                         # noqa: E731
    _stim_networks(params, rec, info, trains, _electrical_events(conditions), CHANNELS,
                   None, dest, root / "ExperimentMatFiles", log,
                   windows={cd.display_name: (0.002, 0.05) for cd in conditions},
                   exclude=np.array([s.elec_stim_times.size > 0 for s in stim_info]),
                   coords=coords,
                   condition_electrodes={cd.display_name: sorted(cd.channel_ids)
                                         for cd in conditions})
    _stim_figures(params, rec, dest, root, stim_info, patterns, spikes, sp, 0.002, info,
                  method, log)
    return dest


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("out") / "OutputDataTest"
    return root, _run(root)


def _ctx(root: Path):
    from meanap.params import Params
    from meanap.pipeline.render import RenderContext
    from meanap.pipeline.spreadsheet import RecordingInfo

    return RenderContext(params=Params(), recordings={REC: RecordingInfo(REC, 14, "WT")},
                         results={}, batch_bounds={}, root=root, mode="ephys")


def _pixels(path: Path) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path))


def test_step_writes_payloads_and_figures(run):
    root, dest = run
    mats = root / "ExperimentMatFiles"
    assert (mats / f"{REC}_stimFigures.npz").is_file()
    with np.load(mats / f"{REC}_stimNetwork.npz") as d:
        assert "figure_meta" in d.files
    names = {p.relative_to(dest).with_suffix("").as_posix() for p in dest.rglob("*.png")}
    assert {"9_FR_before_after_stimulation", "10_stimulation_raster_and_psth",
            "13_StimNetwork_13_10mslag", "14_StimConsistency_13",
            "15_StimNetworkSplitHalf_13_10mslag", "16_StimNetworkGraph_10mslag"} <= names
    with np.load(mats / f"{REC}_stimNetwork.npz") as d:
        assert "13__post__10ms__sttc_thr" in d.files and "coords" in d.files


def test_redrawn_figures_match_the_run(run, tmp_path):
    from meanap.pipeline.render import available_stim_figures, render_stim_figures

    root, dest = run
    ctx = _ctx(root)
    listed = {f.name for f in available_stim_figures(ctx, REC)}
    on_disk = {p.relative_to(dest).with_suffix("").as_posix() for p in dest.rglob("*.png")}
    assert listed == on_disk
    drawn = render_stim_figures(ctx, REC, tmp_path)
    assert len(drawn) == len(on_disk)
    for path in drawn:
        rel = path.relative_to(tmp_path)
        np.testing.assert_array_equal(_pixels(path), _pixels(dest / rel), err_msg=str(rel))


def test_bundle_leaves_redrawable_pictures_out(run):
    from meanap.pipeline.bundle import _redrawable_stim_members

    root, dest = run
    members = _redrawable_stim_members(root)
    on_disk = {p.relative_to(root).as_posix() for p in dest.rglob("*.png")}
    assert members == on_disk


def test_old_runs_show_their_packed_pictures(run, tmp_path):
    """A run from before the payloads: no payloads, pictures listed and served as packed."""
    import shutil

    from meanap.pipeline.bundle import _redrawable_stim_members
    from meanap.pipeline.render import available_stim_figures, stim_figure_path

    root, dest = run
    old = tmp_path / "Old"
    shutil.copytree(root, old)
    for p in (old / "ExperimentMatFiles").glob(f"{REC}_stimFigures.npz"):
        p.unlink()
    net = old / "ExperimentMatFiles" / f"{REC}_stimNetwork.npz"
    with np.load(net) as d:
        arrays = {k: d[k] for k in d.files if k != "figure_meta"}
    np.savez(net, **arrays)
    ctx = _ctx(old)
    assert _redrawable_stim_members(old) == set()
    listed = [f.name for f in available_stim_figures(ctx, REC)]
    assert "14_StimConsistency_13" in listed and len(listed) == len(list(dest.rglob("*.png")))
    path = stim_figure_path(ctx, REC, "14_StimConsistency_13", [], None)
    assert path.is_relative_to(old.resolve())
    with pytest.raises(FileNotFoundError):
        stim_figure_path(ctx, REC, "../../params", [], None)


def test_in_app_viewer_draws_each_alone(run, tmp_path):
    """The in-app viewer asks for one figure at a time and gets it live: a
    native chart (a network grid for 16), drawn without the rest, identical to
    the step's file. Opening it also works on a run with only the pictures."""
    from types import SimpleNamespace

    from meanap.native.output import NativeFigure
    from meanap.pipeline.render import available_stim_figures, render_stim_figure
    from meanap.viewer.live import live_figure

    root, dest = run
    ctx = _ctx(root)
    service = SimpleNamespace(ctx=ctx)
    for spec in available_stim_figures(ctx, REC):
        live = live_figure(service, "stim", REC, spec.name)
        assert isinstance(live.figure, NativeFigure), spec.name
        assert live.figure.kind == ("network_grid" if spec.name.startswith("16_") else "chart")
        out = tmp_path / spec.name.replace("/", "_")
        path = render_stim_figure(ctx, REC, spec.name, out)
        assert sorted(p.name for p in out.rglob("*.png")) == [path.name] \
            or spec.name.startswith("12_"), spec.name   # 12 comes as its pair
        np.testing.assert_array_equal(_pixels(path), _pixels(dest / f"{spec.name}.png"),
                                      err_msg=spec.name)


def test_figure_16_points_at_one_electrode_in_every_panel(tmp_path):
    """Figure 16's panels are one set of electrodes: pointing at a node marks
    the same electrode wherever it is drawn."""
    from meanap.native.network_paint import NetworkGridPainter
    from meanap.native.output import NativeFigure
    from meanap.pipeline.figure_output import capture_figures
    from meanap.stim.redraw import plot_epoch_graphs

    rng = np.random.default_rng(3)
    ch = np.array([c * 10 + r for c in range(1, 5) for r in range(1, 5)])
    xy = np.array([(c, r) for c in range(1, 5) for r in range(1, 5)], float)
    n = len(ch)
    arrays = {"stim_electrode": ch == 22, "channels": ch, "coords": xy}
    epochs = {}
    for epoch in ("baseline", "evoked", "post"):
        m = np.triu(rng.uniform(0.1, 0.6, (n, n)) * (rng.random((n, n)) < 0.4), 1)
        arrays[f"p1__{epoch}__10ms__sttc_thr"] = m + m.T
        epochs[epoch] = {"window_s": [0, 0.05], "n_trials": 20}
    meta = {"conditions": [{"name": "p1", "electrodes": [22],
                            "lags": [{"lag": 10, "epochs": epochs}]}],
            "title": "t", "null": "trial_shuffle"}
    with capture_figures() as got:
        plot_epoch_graphs(arrays, meta, 10, tmp_path / "16.png")
    figure = got[-1].figure
    assert isinstance(figure, NativeFigure) and isinstance(figure.painter, NetworkGridPainter)
    painter = figure.painter
    assert len(painter.panels) == 3
    assert [m["shape"] for m in figure.scene.panels[0][0].markers] == ["star"]
    _r, _c, first = painter.panels[0]
    x0, y0 = painter._origin(0, 0)
    node = 0
    px, py = first.to_pixel(first.scene.xy[node:node + 1])[0]
    assert painter.node_at(x0 + px, y0 + py) == node
    painter.hovered = node
    row = int(first.scene.index[node])
    for _r, _c, panel in painter.panels:
        if row in panel.scene.index:
            assert int(panel.scene.index[panel.hovered]) == row
    assert painter.describe(node).startswith(f"Electrode {first.scene.names[node]}")


def _stim_check_run(root: Path):
    """The stim step's detection checks for a synthetic 8-electrode recording:
    pulses on electrode 13 as a big negative artifact, noise elsewhere."""
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import _stim_detection_checks
    from meanap.stim.detection import get_stim_patterns
    from meanap.stim.events import stim_info_without_stim_nodes

    fs = 1000.0
    rng = np.random.default_rng(4)
    raw = rng.normal(0, 5, (int(T * fs), len(CHANNELS)))
    for e in EVENTS:
        raw[int(e * fs):int(e * fs) + 3, 2] -= 4000
    params = Params()
    coords = np.c_[np.arange(len(CHANNELS)) % 4, np.arange(len(CHANNELS)) // 4].astype(float)
    stim_info = stim_info_without_stim_nodes(CHANNELS, coords)
    stim_info[2].elec_stim_times = EVENTS.copy()
    stim_info[2].elec_stim_dur = np.full(EVENTS.size, 1e-4)
    sp = {**params.to_stim_params_dict(), "fs": fs}
    stim_info, _ = get_stim_patterns(stim_info, sp)
    messages = []
    _stim_detection_checks(params, RecordingInfo(REC, 14, "WT"), raw, stim_info, sp, root,
                           messages.append)
    return raw, messages


def test_stim_detection_checks_are_written_and_redrawn(tmp_path):
    from types import SimpleNamespace

    from meanap.native.output import NativeFigure
    from meanap.pipeline.bundle import _redrawable_stim_members
    from meanap.pipeline.render import (
        available_stim_check_figures, render_stim_check_figure,
    )
    from meanap.stim.detection_checks import STIM_CHECKS_DIR, load_stim_check_data
    from meanap.viewer.live import live_figure

    root = tmp_path / "Out"
    raw, messages = _stim_check_run(root)
    assert messages == []
    folder = root / STIM_CHECKS_DIR / "WT" / REC
    written = sorted(p.stem for p in folder.glob("*.png"))
    # The stimulating electrode, and five others at random (never index 14 —
    # there are only 8 channels here, so all seven non-stimulating are candidates).
    assert written[:2] == ["1_StimsDetected", "2_StimsHeatmap"]
    assert "3_StimsElectrode_13" in written
    assert sum(w.startswith("3_NoStimsElectrode_") for w in written) == 5

    data = load_stim_check_data(root / "ExperimentMatFiles" / f"{REC}_stimChecks.npz")
    k = int(np.flatnonzero(data.traced == 2)[0])
    # The envelope keeps the artifact at full depth and the noise's range.
    assert data.trace_low[k].min() == pytest.approx(raw[:, 2].min(), rel=1e-6)
    assert data.trace_high[k].max() == pytest.approx(raw[:, 2].max(), rel=1e-6)
    np.testing.assert_array_equal(data.stim_times[2], EVENTS)

    ctx = _ctx(root)
    specs = available_stim_check_figures(ctx, REC)
    assert sorted(f.name for f in specs) == written
    for spec in specs:
        out = render_stim_check_figure(ctx, REC, spec.name, tmp_path / "again")
        np.testing.assert_array_equal(_pixels(out), _pixels(folder / f"{spec.name}.png"),
                                      err_msg=spec.name)
        live = live_figure(SimpleNamespace(ctx=ctx), "stim_check", REC, spec.name)
        assert isinstance(live.figure, NativeFigure) and live.figure.kind == "chart"
    # A bundle carries the file, not the pictures.
    assert _redrawable_stim_members(root) == {
        p.relative_to(root).as_posix() for p in folder.glob("*.png")}


def test_ephys_pictures_are_not_traces(run):
    from meanap.pipeline.render import available_trace_figures

    root, _ = run
    assert available_trace_figures(_ctx(root), REC) == []


def test_labels():
    from meanap.stim.redraw import sort_stim_names, stim_figure_label

    assert stim_figure_label("13_StimNetwork_LtoR_10mslag") == \
        "Baseline vs evoked network, LtoR, 10 ms lag"
    assert stim_figure_label(
        "Individual_PSTH_and_Raster_Pattern_2/Individual_PSTH_and_Raster_electrode_47") == \
        "PSTH and raster, pattern 2, electrode 47"
    assert sort_stim_names(["13_StimNetwork_a_10mslag", "9_FR_before_after_stimulation",
                            "stimPattern_1_heatmap"]) == [
        "9_FR_before_after_stimulation", "stimPattern_1_heatmap", "13_StimNetwork_a_10mslag"]


def test_post_window():
    from meanap.stim.evoked_network import post_window, separated_events

    assert post_window((0.002, 0.05)) == pytest.approx((0.05, 0.098))
    assert post_window((0.002, 0.05), [0.2, 0.4]) == (0.2, 0.4)
    with pytest.raises(ValueError):
        post_window((0.0, 0.05), [0.4, 0.2])
    ev = np.array([1.0, 1.15, 3.0])
    # evoked + baseline need 0.1 s between events; a post window to 0.3 s needs 0.35 s
    assert separated_events(ev, (0.0, 0.05)).tolist() == [True, True, True]
    assert separated_events(ev, (0.0, 0.05), after=0.3).tolist() == [False, False, True]
