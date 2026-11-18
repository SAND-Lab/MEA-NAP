"""Inactive electrodes behind a network, and MaxWell runs' spatial plots.

Two things share the plumbing tested here. A run whose spike file places its
own nodes (a detected MaxWell run, a sorted import) has those positions and
its whole electrode table stored with the adjacency, so step 4 can draw its
spatial plots at all — a detected MaxWell run used to skip every one, its
layout "FromFile" having no fixed table. And with the electrode table at hand,
the electrodes no node sits on can be drawn as faint dots.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from meanap.network_plot import NetworkStyle  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.channel_layout import (  # noqa: E402
    all_electrode_coords, file_node_coords, get_coords_from_layout,
    inactive_electrode_coords,
)
from meanap.pipeline.plotting_step4 import _inactive_dots  # noqa: E402
from meanap.pipeline.step4 import recording_positions, spatial_node_noun  # noqa: E402

DOTS = NetworkStyle(inactive_electrodes="Faint dots")


def _grid(n=10, pitch=0.2):
    g = np.arange(n) * pitch
    return np.array([(x, y) for x in g for y in g])


def test_inactive_are_the_electrodes_without_a_node():
    electrodes = _grid()
    nodes = electrodes[[0, 5, 17, 99]]
    left = inactive_electrode_coords(electrodes, nodes)
    assert len(left) == len(electrodes) - 4
    assert not any(np.allclose(n, e) for n in nodes for e in left)


def test_a_unit_on_a_ring_round_its_electrode_occupies_it():
    electrodes = _grid()
    # Two units on one electrode, 0.06 either side: under half the 0.2 pitch.
    units = electrodes[[12, 12, 40]] + np.array([[0.06, 0], [-0.06, 0], [0, 0.03]])
    assert len(inactive_electrode_coords(electrodes, units)) == len(electrodes) - 2


def test_file_positions_detected_maxwell_and_sorted():
    ids = np.array([101, 205, 309])
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    detected = {"electrode_ids": ids, "electrode_coords": xy}

    class F(dict):
        files = property(lambda self: list(self))

    got = file_node_coords(F(detected), np.array([309, 101, 999]))
    assert np.allclose(got[:2], [[2.0, 0.0], [0.0, 0.0]]) and np.isnan(got[2]).all()
    sorted_file = F(detected, unit_coords=np.array([[0.1, 0.0]]))
    assert np.allclose(file_node_coords(sorted_file, ids), [[0.1, 0.0]])
    assert file_node_coords(F(channels=ids)) is None        # an MCS file places nothing


def test_older_adjacency_files_fall_back_to_the_spike_file():
    class F(dict):
        files = property(lambda self: list(self))

    adj = F(channels=np.array([1, 2]))
    spikes = F(electrode_ids=np.array([1, 2, 3]),
               electrode_coords=np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]))
    nodes, electrodes = recording_positions(Params(), adj, spikes)
    assert np.allclose(nodes, [[0.0, 0.0], [1.0, 0.0]]) and len(electrodes) == 3


def test_dots_only_when_asked_and_on_the_electrode_layout():
    _, mcs = get_coords_from_layout("MCS60")
    active = np.asarray(mcs)[:40]
    assert _inactive_dots(NetworkStyle(), "MCS60", None, active, None) is None
    got = _inactive_dots(DOTS, "MCS60", None, active, None)
    assert len(got) == len(all_electrode_coords("MCS60")) - 40
    circular = NetworkStyle(inactive_electrodes="Faint dots", layout="Circular")
    assert _inactive_dots(circular, "MCS60", None, active, None) is None
    # Cells placed by their own positions, with no electrode table: no grid.
    assert _inactive_dots(DOTS, "MCS60", None, active, active) is None


def test_node_nouns():
    xy = np.zeros((2, 2))
    assert spatial_node_noun(Params(), None) is None
    assert spatial_node_noun(Params(), xy) == "electrode"           # detected MaxWell
    assert spatial_node_noun(Params(spike_source="import"), xy) == "unit"
    assert spatial_node_noun(Params(suite2p_mode=True), xy) is None


def test_scene_carries_the_dots_and_widens_its_extent():
    from meanap.native.scene import network_scene

    electrodes = _grid(5, 1.0)
    nodes = electrodes[[6, 7, 12]]
    adj = np.array([[0, 0.5, 0], [0.5, 0, 0.4], [0, 0.4, 0]])
    plain = network_scene(adj, nodes, 0.0, np.array([1.0, 2.0, 1.0]))
    dotted = network_scene(adj, nodes, 0.0, np.array([1.0, 2.0, 1.0]),
                           inactive_xy=inactive_electrode_coords(electrodes, nodes))
    assert len(plain.inactive_xy) == 0 and len(dotted.inactive_xy) == 22
    assert dotted.extent == (0.0, 4.0, 0.0, 4.0) and plain.extent == (1.0, 2.0, 1.0, 2.0)
    assert dotted.inactive_diameter == pytest.approx(0.25)


def test_maxwell_run_draws_its_spatial_plots():
    import test_maxwell_voltage as mx
    from meanap.pipeline.runner import run_pipeline

    raw, _, _ = mx.data()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        logs: list[str] = []
        run_pipeline(mx._params(tmp, raw.parent, stop_analysis_step=4, express_mode=False,
                                func_con_lag_val=[10]), log=logs.append)
        assert not [m for m in logs if "skipped spatial network plot" in m], logs
        drawn = {p.name for p in tmp.rglob("4A_*/**/*.png")}
        assert "2_MEA_NetworkPlot.png" in drawn
        assert "3_MEA_NetworkPlotNodedegreeBetweennesscentrality.png" in drawn
        adj = next(tmp.rglob(f"{mx.NAME}_adjM.npz"))
        with np.load(adj) as a:
            assert "coords" in a.files and "electrode_coords" in a.files


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    raise SystemExit(pytest.main([__file__, "-q"]))
