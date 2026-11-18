"""The edge-weight histogram in a network plot's key, and dragging its threshold.

When some edges are not drawn at their width — hidden by the edge threshold,
or among the hairlines past the WIDE_EDGES strongest — the key shows every
edge weight as a histogram, shaded by how each is drawn, with the threshold
as a line on it. Dragging that line sets the threshold, in the native viewer
and the web one. Where every edge is drawn at its width the key is unchanged,
which is what keeps default figures on a 60- or 64-electrode MEA identical.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

from meanap.network_plot import (  # noqa: E402
    EDGE_SCALING_METHODS, NetworkStyle, scale_edge_position,
)
from meanap.native.scene import network_scene  # noqa: E402


def _network(n=40, seed=0, density=1.0):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 8, (n, 2))
    w = np.triu(rng.uniform(0.01, 1.0, (n, n)), 1)
    w[rng.uniform(size=w.shape) > density] = 0
    w = w + w.T
    return w, xy, (w > 0).sum(1).astype(float)


def _painted(scene):
    from meanap.native import output
    from meanap.native.network_paint import NetworkPainter

    output.ensure_app()
    painter = NetworkPainter(scene)
    output.render_image(painter)
    return painter


@pytest.mark.parametrize("method", EDGE_SCALING_METHODS)
def test_edge_scaling_keeps_the_ends_and_order(method):
    t = np.linspace(0, 1, 11)
    s = scale_edge_position(t, method, power=2.5)
    assert s[0] == pytest.approx(0) and s[-1] == pytest.approx(1)
    assert np.all(np.diff(s) >= 0)


def test_linear_edge_scaling_is_the_old_mapping():
    w, xy, z = _network()
    old = network_scene(w, xy, 0.0, z)
    assert np.array_equal(old.edge_width, network_scene(
        w, xy, 0.0, z, edge_scaling_method="Linear").edge_width)
    log = network_scene(w, xy, 0.0, z, edge_scaling_method="Log10")
    # Lifts the weak end: every edge at least as wide, the ends where they were.
    assert np.all(log.edge_width >= old.edge_width - 1e-12)
    assert log.edge_width.max() == pytest.approx(old.edge_width.max())


def test_scene_counts_every_edge_and_knows_its_cutoff():
    w, xy, z = _network()
    scene = network_scene(w, xy, 0.5, z)
    pairs = w[np.triu_indices(len(w), 1)]
    assert len(scene.all_edge_weight) == int((pairs > 0).sum())
    assert len(scene.edge_weight) == int((pairs >= 0.5).sum())
    assert scene.edge_cutoff == 0.5
    assert scene.edge_faint is None


def test_a_cap_on_the_edge_count_is_a_cutoff_and_still_counted():
    w, xy, z = _network()
    style = NetworkStyle(max_edges=50)
    capped, coords, thresh = style.prepare(w, xy)
    scene = network_scene(capped, coords, thresh, z, histogram_adj=w)
    assert len(scene.edge_weight) == 50
    assert len(scene.all_edge_weight) == int((w[np.triu_indices(len(w), 1)] > 0).sum())
    assert scene.edge_cutoff == pytest.approx(scene.edge_weight.min())


def test_hairlines_draw_the_edges_below_the_threshold_but_not_as_connections():
    w, xy, z = _network()
    hidden = network_scene(w, xy, 0.5, z)
    faint = network_scene(w, xy, 0.5, z, below_threshold_edges="Hairlines")
    assert len(faint.edge_weight) == len(faint.all_edge_weight)
    assert int(faint.shown.sum()) == len(hidden.edge_weight)
    assert np.all(faint.edge_weight[faint.edge_faint] < 0.5)
    for node in range(5):
        assert np.array_equal(faint.neighbours(node), hidden.neighbours(node))


def test_no_histogram_while_every_edge_is_drawn_at_its_width():
    w, xy, z = _network()
    painter = _painted(network_scene(w, xy, 0.0, z))
    assert not painter.has_histogram and painter.histogram_rect is None


def test_histogram_maps_pixels_onto_weights():
    w, xy, z = _network()
    painter = _painted(network_scene(w, xy, 0.5, z))
    assert painter.has_histogram
    box, (low, high) = painter.histogram_rect, painter.histogram_range
    assert low == pytest.approx(painter.scene.all_edge_weight[0])
    assert high == pytest.approx(painter.scene.all_edge_weight[-1])
    assert painter.weight_at(box.left()) == pytest.approx(low)
    assert painter.weight_at(box.right()) == pytest.approx(high)
    assert painter.weight_at(box.center().x()) == pytest.approx((low + high) / 2)
    assert painter.cutoff_at(box.center().x(), box.center().y()) is not None
    assert painter.cutoff_at(10, 10) is None


def test_many_edges_get_the_histogram_without_a_threshold():
    from meanap.native.network_paint import WIDE_EDGES

    w, xy, z = _network(n=60)              # 1,770 edges
    painter = _painted(network_scene(w, xy, 0.0, z))
    assert len(painter.scene.edge_weight) > WIDE_EDGES
    assert painter.has_histogram and painter.wide_count == WIDE_EDGES


def test_dragging_the_line_on_the_native_canvas_picks_a_threshold():
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    from meanap.gui.network_canvas import NetworkCanvas
    from meanap.native import output

    output.ensure_app()
    w, xy, z = _network()
    canvas = NetworkCanvas()
    canvas.resize(980, 800)
    canvas.show_scene(network_scene(w, xy, 0.5, z))
    surface = canvas.surface
    surface.resize(960, 760)
    canvas.painter.resize((960, 760))
    surface.grab()                         # paints, which lays the key out
    box = canvas.painter.histogram_rect
    assert box is not None
    picked = []
    canvas.threshold_picked.connect(picked.append)

    def send(kind, x):
        at = QPointF(x, box.center().y())
        surface.event(QMouseEvent(kind, at, at, Qt.MouseButton.LeftButton,
                                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    send(QMouseEvent.Type.MouseButtonPress, box.left() + 0.2 * box.width())
    send(QMouseEvent.Type.MouseMove, box.left() + 0.75 * box.width())
    send(QMouseEvent.Type.MouseButtonRelease, box.left() + 0.75 * box.width())
    low, high = canvas.painter.histogram_range
    assert picked == [pytest.approx(low + 0.75 * (high - low))]


def test_the_new_controls_reach_the_style():
    from meanap.pipeline.render import STYLE_KEYS, style_from_overrides
    from meanap.viewer.controls import control_schema, parse_overrides

    keys = {c["key"] for c in control_schema()}
    for key in ("edge_scaling_method", "edge_scaling_power", "below_threshold_edges"):
        assert key in keys and key in STYLE_KEYS
    asked = parse_overrides({"edge_scaling_method": ["Log2"],
                             "below_threshold_edges": ["Hairlines"]})
    assert asked == {"edge_scaling_method": "Log2", "below_threshold_edges": "Hairlines"}
    style = style_from_overrides(asked)
    assert style.edge_scaling_method == "Log2"
    assert style.scene_kwargs()["below_threshold_edges"] == "Hairlines"
    # Nothing asked: nothing restyled, so the run's figures stay as they were.
    assert parse_overrides({}) == {}


def test_web_viewer_is_told_where_the_histogram_is():
    from test_bundle_render import _run

    from meanap.pipeline.render import available_figures
    from meanap.viewer.server import ViewerService

    with tempfile.TemporaryDirectory() as tmp:
        run = _run(Path(tmp), "EdgeHist", express=True)
        service = ViewerService(run)
        rec = service.manifest()["recordings"][0]["name"]
        lag = service.manifest()["recordings"][0]["lags"][0]
        name = next(f.name for f in available_figures(service.ctx, rec, lag)
                    if "MEA_NetworkPlot" in f.name and "combined" not in f.name)
        plain = service.edge_histogram(rec, lag, name, overrides={})
        cut = service.edge_histogram(
            rec, lag, name, overrides={"edge_threshold": 0.2})
        page = cut["histogram"]
        assert page is not None, plain
        x0, y0, x1, y1 = page["rect"]
        assert 0.5 < x0 < x1 <= 1 and 0 < y0 < y1 < 1
        assert page["low"] < page["high"] and page["cutoff"] >= 0.2
        service.close()


# ── Circular plots ────────────────────────────────────────────────────────────


def _circular(style=None, n=40):
    from meanap.native.scene import circular_scene
    from meanap.pipeline.plotting_step4 import _circular_edges

    w, _xy, z = _network(n=n)
    adj, extra = _circular_edges(style, w, 0.0)
    return circular_scene(adj, np.ones((n, 3)) * 0.5, np.full(n, 0.05),
                          [""] * n, **extra)


def test_circular_plot_unchanged_without_a_style():
    from meanap.native.scene import circular_scene

    w, _xy, _z = _network()
    plain = circular_scene(w, np.ones((40, 3)), np.full(40, 0.05), [""] * 40)
    again = _circular(None)
    assert np.array_equal(plain.edge_width, again.edge_width)
    assert not _painted(again).has_histogram


def test_circular_plot_takes_the_edge_styling():
    cut = _circular(NetworkStyle(edge_threshold=0.5))
    assert cut.edge_cutoff == 0.5 and np.all(cut.edge_weight >= 0.5)
    painter = _painted(cut)
    assert painter.has_histogram and painter.histogram_rect is not None
    # Half the spatial plots' widths: at the defaults, the MATLAB 2 points.
    assert cut.edge_width.max() == pytest.approx(2.0)
    faint = _circular(NetworkStyle(edge_threshold=0.5, below_threshold_edges="Hairlines"))
    assert faint.edge_faint is not None and faint.edge_arcs.shape[0] == len(faint.edge_weight)
    capped = _circular(NetworkStyle(max_edges=30))
    assert len(capped.edge_weight) == 30 and len(capped.all_edge_weight) > 30


def test_style_panel_shows_only_edge_controls_beside_a_circular_plot():
    from meanap.gui.results_viewer import StylePanel
    from meanap.native import output
    from meanap.viewer.controls import EDGE_CONTROL_KEYS, control_schema

    output.ensure_app()
    panel = StylePanel()
    panel.set_schema(control_schema())
    panel.set_circular(True)
    shown = {k for k, w in panel._widgets.items() if not w.isHidden()}
    assert shown == set(EDGE_CONTROL_KEYS)
    panel.set_circular(False)
    assert all(not w.isHidden() for w in panel._widgets.values())
