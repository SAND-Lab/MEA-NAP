"""Electrophysiology network plots size nodes to their packing ("fit").

The claim the default rests on: on the standard MEA layouts it draws exactly
what the fixed scale of 1.0 always drew, and it only shrinks nodes where they
sit closer than an MEA's electrodes (sorted units, HD-MEA routings), where the
fixed scale drew each node several times wider than the gap to its neighbour.
"""
from __future__ import annotations

import numpy as np
import pytest

from meanap.network_plot import (
    NODE_SIZE_AUTO, NODE_SIZE_FIT, NetworkStyle, auto_node_size_scale,
    resolve_node_size_scale,
)
from meanap.params import Params
from meanap.pipeline.channel_layout import get_coords_from_layout


@pytest.mark.parametrize("layout", ["MCS60", "Axion64", "Axion16"])
def test_fit_is_exactly_one_on_standard_layouts(layout):
    _, coords = get_coords_from_layout(layout)
    assert resolve_node_size_scale(NODE_SIZE_FIT, np.asarray(coords)) == 1.0


def test_fit_never_enlarges_but_auto_does():
    _, coords = get_coords_from_layout("Axion16")      # sparser than an 8x8 grid
    assert auto_node_size_scale(np.asarray(coords)) > 1.5
    assert resolve_node_size_scale(NODE_SIZE_AUTO, np.asarray(coords)) > 1.5
    assert resolve_node_size_scale(NODE_SIZE_FIT, np.asarray(coords)) == 1.0


def test_fit_shrinks_dense_layouts():
    # 300 nodes on a 0.2-unit grid inside the usual 0-8 box: sorted-unit density.
    g = np.arange(0, 4, 0.2)
    coords = np.array([(x, y) for x in g for y in g[:15]])
    scale = resolve_node_size_scale(NODE_SIZE_FIT, coords)
    assert scale == pytest.approx(0.875 * 0.2)
    assert resolve_node_size_scale(2.5, coords) == 2.5          # Manual is Manual


def test_runs_default_to_fit_and_catnap_is_unchanged():
    assert NetworkStyle.for_run(Params()).node_size_scale == NODE_SIZE_FIT
    assert NetworkStyle().node_size_scale == NODE_SIZE_FIT
    s2p = Params(suite2p_mode=True)
    assert NetworkStyle.for_run(s2p).node_size_scale == (
        NODE_SIZE_AUTO if s2p.twop_auto_node_size else 1.0)
    s2p.twop_auto_node_size = False
    assert NetworkStyle.for_run(s2p).node_size_scale == 1.0


def test_viewer_controls_show_fit_as_auto_and_keep_it():
    from meanap.viewer.controls import CONTROLS, control_default, parse_overrides

    fit, fixed = NetworkStyle(node_size_scale=NODE_SIZE_FIT), NetworkStyle(node_size_scale=1.0)
    mode = next(c for c in CONTROLS if c.key == "node_size_mode")
    assert control_default(mode, fit) == "Auto"
    assert control_default(mode, fixed) == "Manual"
    # Nothing asked: the run's own sizing stands.
    assert "node_size_scale" not in parse_overrides({}, fit)
    # Auto on a fixed-scale drawing gets MEA-NAP's never-larger sizing...
    assert parse_overrides({"node_size_mode": ["Auto"]}, fixed)[
        "node_size_scale"] == NODE_SIZE_FIT
    # ...and Manual with a number is that number.
    got = parse_overrides(
        {"node_size_mode": ["Manual"], "node_size_scale": ["2"]}, fit)
    assert got["node_size_scale"] == 2.0


@pytest.mark.parametrize("layout", ["MCS60", "Axion64"])
def test_standard_layout_figures_are_pixel_identical(tmp_path, layout):
    import matplotlib.image as mpimg
    from meanap.pipeline.plotting_step4 import plot_spatial_network

    ch, _ = get_coords_from_layout(layout)
    ch = np.asarray(ch)
    rng = np.random.default_rng(3)
    a = rng.random((len(ch), len(ch)))
    a = np.triu(a * (a > 0.7), 1)
    a = a + a.T
    z = (a > 0).sum(0).astype(float)
    z2 = rng.random(len(ch))
    imgs = []
    for scale in (1.0, NODE_SIZE_FIT):
        out = tmp_path / f"{scale}.png"
        plot_spatial_network(a, ch, layout, z, z2,
                             "betweenness centrality", 10, "rec", out,
                             node_size_scale=scale)
        imgs.append(mpimg.imread(out))
    assert imgs[0].shape == imgs[1].shape and np.array_equal(imgs[0], imgs[1])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
