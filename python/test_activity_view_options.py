"""Viewer options for the activity figures: inactive electrodes on a heatmap,
and the raster's row order.

Both are viewer options, not run settings: absent, the figures are the
pipeline's own, and the tests check that, as well as what each option does.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

from meanap.pipeline.raster_order import (  # noqa: E402
    RASTER_ORDERS, available_orders, order_rows,
)


def _two_groups(n_each=6, bins=300, seed=0):
    """Rows in two groups that burst at different times, interleaved, plus a silent row."""
    rng = np.random.default_rng(seed)
    a = (rng.uniform(size=bins) < 0.1).astype(float)
    b = (rng.uniform(size=bins) < 0.1).astype(float)
    rows = []
    for k in range(n_each):
        rows.append(a * 8 + rng.poisson(0.3, bins))
        rows.append(b * 8 + rng.poisson(0.3, bins))
    rows.append(np.zeros(bins))
    return np.array(rows)


def test_recording_order_is_the_identity_and_firing_rate_is_busiest_first():
    counts = np.array([[1, 1], [5, 5], [3, 3]], dtype=float)
    assert list(order_rows(counts, "Recording order")) == [0, 1, 2]
    assert list(order_rows(counts, "Firing rate")) == [1, 2, 0]


def test_correlation_puts_each_group_together_and_silence_last():
    counts = _two_groups()
    rows = order_rows(counts, "Correlation")
    assert sorted(rows) == list(range(len(counts)))
    group = np.array([k % 2 for k in range(12)] + [-1])[rows]
    assert group[-1] == -1                        # the silent row
    assert np.count_nonzero(np.diff(group[:-1])) == 1     # two runs, one each


def test_unknown_order_and_rastermap_only_when_installed():
    with pytest.raises(ValueError):
        order_rows(np.ones((5, 4)), "Alphabetical")
    from meanap.pipeline.raster_order import rastermap_available

    assert ("Rastermap" in available_orders()) == rastermap_available()
    assert set(available_orders()) <= set(RASTER_ORDERS)


def test_a_sorted_raster_keeps_each_row_with_its_name():
    from meanap.native.scene import raster_scene, reorder_raster

    trains = {0: np.array([1.0]), 1: np.arange(0, 10, 0.1), 2: np.arange(0, 10, 0.5)}
    scene = raster_scene(trains, 10.0, names=["e11", "e12", "e13"])
    plain = reorder_raster(scene, "Recording order")
    assert plain is scene and scene.order_label == ""
    busy = reorder_raster(scene, "Firing rate")
    assert busy.names == ["e12", "e13", "e11"]
    assert np.array_equal(busy.counts[0], scene.counts[1])
    assert busy.order_label == "sorted by firing rate"


def test_heatmap_shows_the_electrodes_without_a_node_only_when_asked():
    from meanap.native.scene import heatmap_scene

    channels = np.arange(9)
    coords = np.array([(i % 3, i // 3) for i in channels], dtype=float)
    used = np.array([0, 4, 8])
    plain = heatmap_scene(np.array([1.0, 2.0, 3.0]), used, "t", "rate",
                          layout=(channels, coords))
    dotted = heatmap_scene(np.array([1.0, 2.0, 3.0]), used, "t", "rate",
                           layout=(channels, coords), inactive=True)
    assert len(plain.inactive_xy) == 0
    assert len(dotted.inactive_xy) == 6
    assert dotted.diameter == plain.diameter       # the nodes keep their size


def test_heatmap_with_dots_is_drawn(tmp_path):
    from meanap.native import output
    from meanap.native.activity_paint import HeatmapPainter
    from meanap.native.scene import heatmap_scene

    output.ensure_app()
    channels = np.arange(16)
    coords = np.array([(i % 4, i // 4) for i in channels], dtype=float)
    scene = heatmap_scene(np.arange(4.0), np.array([0, 5, 10, 15]), "t", "rate",
                          layout=(channels, coords), inactive=True)
    output.save(HeatmapPainter(scene), tmp_path / "h.png")
    assert (tmp_path / "h.png").stat().st_size > 5000


def test_requests_carry_only_what_differs_from_the_pipeline():
    from meanap.pipeline.render import split_activity_view
    from meanap.viewer.controls import parse_activity_overrides

    assert parse_activity_overrides({}) == {}
    assert parse_activity_overrides({"inactive_electrodes": ["Hidden"],
                                     "raster_order": ["Recording order"]}) == {}
    asked = parse_activity_overrides({"inactive_electrodes": ["Faint dots"],
                                      "raster_order": ["Correlation"]})
    assert asked == {"inactive_electrodes": "Faint dots", "raster_order": "Correlation"}
    with pytest.raises(ValueError):
        parse_activity_overrides({"raster_order": ["Sideways"]})
    params, view = split_activity_view({**asked, "raster_plot_upper_percentile": 95.0})
    assert view == asked and params == {"raster_plot_upper_percentile": 95.0}
    assert split_activity_view(None) == (None, {})


def test_each_control_is_shown_beside_the_figures_it_changes():
    from meanap.gui.results_viewer import StylePanel
    from meanap.native import output
    from meanap.viewer.controls import control_schema

    schema = {c["key"]: c for c in control_schema()}
    assert schema["raster_order"]["scopes"] == ["raster"]
    assert "heatmap" in schema["inactive_electrodes"]["scopes"]
    output.ensure_app()
    panel = StylePanel()
    panel.set_schema(control_schema())

    def shown():
        return {k for k, w in panel._widgets.items() if not w.isHidden()}

    panel.set_scope("raster")
    assert shown() == {"raster_order"}
    panel.set_scope("heatmap")
    assert shown() == {"inactive_electrodes"}
    panel.set_scope("spatial")
    assert "raster_order" not in shown() and "layout" in shown()
