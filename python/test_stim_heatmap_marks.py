"""Stimulating electrodes marked on the step-2 heatmaps, as in MATLAB.

``electrodeHeatMaps.m`` and ``plotNodeHeatmap.m`` draw each electrode a
recording stimulated on white with a black edge when ``stimulationMode`` is
on. Checks that:

* the heatmap scene marks them and keeps them out of the colour range;
* the painter draws them white with a black edge, and says so on hover;
* step 2 and the viewer find them in the stim step's figure payload, only in a
  stimulation run, and find none for an event-driven run;
* ``plot_neuronal_activity_checks`` marks them on every heatmap.

    QT_QPA_PLATFORM=offscreen uv run pytest python/test_stim_heatmap_marks.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CHANNELS = list(range(11, 71))[:60]
STIM = 23


def _fr():
    fr = np.linspace(1.0, 10.0, 60)
    fr[CHANNELS.index(STIM)] = 500.0          # what step 1 found around the artifact
    return fr


def _scene(stimulated):
    from meanap.native.scene import heatmap_scene

    return heatmap_scene(_fr(), CHANNELS, "rec", "mean firing rate (Hz)",
                         channel_layout="MCS60", batch_max=20.0, stimulated=stimulated)


def test_scene_marks_and_leaves_out_of_scale():
    scene = _scene({STIM})
    i = scene.names.index(str(STIM))
    assert scene.stimulated.sum() == 1 and scene.is_stimulated(i)
    assert np.isnan(scene.values[i])
    assert all(high <= 10.0 for _t, _low, high in scene.panels[:1])

    plain = _scene(None)
    assert not plain.is_stimulated(i) and plain.panels[0][2] > 10.0


def _rgb(image, x, y):
    c = image.pixelColor(int(round(x)), int(round(y)))
    return c.red(), c.green(), c.blue()


def test_painter_draws_white_with_black_edge():
    from meanap.native.activity_paint import HeatmapPainter
    from meanap.native.output import render_image

    scene = _scene({STIM})
    painter = HeatmapPainter(scene)
    image = render_image(painter)
    i = scene.names.index(str(STIM))
    for panel in range(len(scene.panels)):
        _plot, _bar, scale, _c = painter._panel(panel)
        x, y = painter._pixels(panel)[i]
        radius = scene.diameter * scale / 2
        assert _rgb(image, x, y) == (255, 255, 255), f"panel {panel} centre"
        edge = [_rgb(image, x + radius + d, y) for d in (-1, -0.5, 0, 0.5)]
        assert min(sum(c) for c in edge) < 150, f"panel {panel} edge: {edge}"
        # Its neighbour is coloured as before.
        j = scene.names.index(str(STIM + 1))
        assert _rgb(image, *painter._pixels(panel)[j]) != (255, 255, 255)
    assert painter.describe(i).endswith("stimulating electrode")


def _payload(tmp: Path, stim_channel: int | None) -> Path:
    from meanap.stim.events import stim_info_without_stim_nodes
    from meanap.stim.redraw import FIGURES_SUFFIX, save_figure_payload

    chans = np.array([21, 22, 23, 24])
    info = stim_info_without_stim_nodes(chans, np.zeros((4, 2)))
    if stim_channel is not None:
        info[list(chans).index(stim_channel)].pattern = 1
    path = tmp / "ExperimentMatFiles" / f"recA{FIGURES_SUFFIX}"
    save_figure_payload(path, stim_info=info, patterns=[np.array([1.0])],
                        spike_times={}, method="thr4", params={}, artifact_s=0.002,
                        info={}, seed=1, recording="recA")
    return path


def test_found_in_the_stim_payload(tmp_path):
    from meanap.params import Params
    from meanap.pipeline.plotting_step2 import step2_stimulated_electrodes

    on, off = Params(stimulation_mode=True), Params(stimulation_mode=False)
    assert step2_stimulated_electrodes(on, tmp_path, "recA") == set()     # no payload
    _payload(tmp_path, STIM)
    assert step2_stimulated_electrodes(on, tmp_path, "recA") == {STIM}
    assert step2_stimulated_electrodes(off, tmp_path, "recA") == set()

    events = tmp_path / "events"
    _payload(events, None)                         # light / TTL: nothing stimulates
    assert step2_stimulated_electrodes(on, events, "recA") == set()


def test_every_heatmap_marked(tmp_path, monkeypatch):
    import meanap.pipeline.plotting_step2 as p2
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo

    seen = {}

    def spy(metric, chs, title, clabel, out_path, **kw):
        seen[Path(out_path).stem] = kw.get("stimulated")

    monkeypatch.setattr(p2, "plot_heatmap", spy)
    ephys = {key: _fr() for _n, key, _c, _m in p2.ACTIVITY_HEATMAPS}
    p2.plot_neuronal_activity_checks(
        RecordingInfo("recA", 14, "WT"), Params(channel_layout="MCS60"), {}, 60,
        np.array(CHANNELS), 25000.0, 60.0, ephys, tmp_path,
        only="2_Heatmap", stimulated={STIM})
    assert seen == {"2_Heatmap": {STIM}}
    for name, *_ in p2.ACTIVITY_HEATMAPS:
        seen.clear()
        p2.plot_neuronal_activity_checks(
            RecordingInfo("recA", 14, "WT"), Params(channel_layout="MCS60"), {}, 60,
            np.array(CHANNELS), 25000.0, 60.0, ephys, tmp_path,
            only=Path(name).stem, stimulated={STIM})
        assert seen == {Path(name).stem: {STIM}}
