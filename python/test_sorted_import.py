"""Importing spike-sorted data + event-driven (light) stimulation analysis.

Runs on the synthetic recording in ``sorted_import_fixture.py`` (12 MaxWell
electrodes, 15 units, 40 s, a flash marked by TTL every second), where the
truth is known: which samples each unit fired, where it sits, which TTL bit
is the stimulus, and which units respond to ON and to OFF.

    .venv/bin/python -m pytest python/test_sorted_import.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sorted_import_fixture as fx  # noqa: E402
from meanap.params import SORTED_METHOD, Params  # noqa: E402
from meanap.pipeline.io import load_spike_file  # noqa: E402
from meanap.pipeline.maxwell import read_maxwell_meta, read_maxwell_ttl  # noqa: E402
from meanap.pipeline.sorted_import import (  # noqa: E402
    ElectrodeTable, find_sorted_output, layout_coords_from_um, read_phy,
    read_spykingcircus, to_spike_file,
)
from meanap.stim.events import assign_conditions, events_from_ttl, read_events_csv  # noqa: E402

_FIXTURE: fx.Fixture | None = None


def fixture() -> fx.Fixture:
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = fx.make_fixture(Path(tempfile.mkdtemp()) / "data")
    return _FIXTURE


def _expected_electrode(unit: int) -> int:
    return int(fx.ELECTRODES[fx.UNIT_PEAK_ROW[unit]])


# ── MaxWell metadata and TTLs ─────────────────────────────────────────────────

def test_maxwell_meta_joins_mapping_by_channel():
    meta = read_maxwell_meta(fixture().raw)
    assert meta.fs == fx.FS and meta.duration_s == fx.DURATION_S
    assert meta.first_frame == fx.FIRST_FRAME
    # Routed-row order, whatever order the mapping table lists them in.
    np.testing.assert_array_equal(meta.channels, fx.CHANNELS)
    np.testing.assert_array_equal(meta.electrodes, fx.ELECTRODES)
    np.testing.assert_allclose(meta.xy_um, fx.electrode_xy_um())


def test_ttl_auto_picks_the_marker_not_the_frame_sync():
    times, words = read_maxwell_ttl(fixture().raw)
    ev, how = events_from_ttl(times, words, "auto")
    assert how == "auto → fall:7"
    np.testing.assert_allclose(ev, fx.EVENT_TIMES_S, atol=1 / fx.FS)
    # The explicit rules agree; the frame-sync bit is the 60 Hz one.
    np.testing.assert_allclose(events_from_ttl(times, words, "value:0")[0], ev)
    sync, _ = events_from_ttl(times, words, "rise:5", min_interval_s=0)
    assert abs(np.median(np.diff(sync)) - 1 / 60) < 1e-3


def test_debounce_merges_bouncing_markers():
    times = np.array([0.0, 1.0, 1.0001, 1.02, 3.0, 3.0002])
    words = np.array([128, 0, 128, 0, 0, 128])  # bouncy edges near 1 s
    ev, _ = events_from_ttl(times, words, "value:0", min_interval_s=0.05)
    np.testing.assert_allclose(ev, [1.0])  # 3.0 is no change: word already 0
    ev, _ = events_from_ttl(np.r_[times, 3.5], np.r_[words, 0], "value:0", min_interval_s=0.05)
    np.testing.assert_allclose(ev, [1.0, 3.5])


def test_conditions_alternate_and_csv():
    t = np.arange(5.0)
    assert assign_conditions(t, "alternate", ["ON", "OFF"]).tolist() == \
        ["ON", "OFF", "ON", "OFF", "ON"]
    assert set(assign_conditions(t, "single")) == {"stim"}
    path = fixture().folder / "events_test.csv"
    path.write_text("onset_s,condition\n2.5,OFF\n1.0,ON\n4.0,\n")
    ev = read_events_csv(path)
    np.testing.assert_allclose(ev.times_s, [1.0, 2.5, 4.0])
    assert ev.conditions.tolist() == ["ON", "OFF", "stim"]


# ── Readers ───────────────────────────────────────────────────────────────────

def _check_units(imp, units: list[int]):
    for i, u in enumerate(units):
        np.testing.assert_allclose(imp.spike_trains[i], fixture().samples[u] / fx.FS)
        assert int(imp.electrodes.ids[imp.peak_index[i]]) == _expected_electrode(u)


def test_spykingcircus_reader_recovers_trains_and_peaks():
    f = fixture()
    meta = read_maxwell_meta(f.raw)
    imp = read_spykingcircus(f.sc_result, electrodes=ElectrodeTable.from_maxwell(meta),
                             fs=meta.fs, duration_s=meta.duration_s)
    assert imp.n_units == fx.N_UNITS and imp.duration_s == fx.DURATION_S
    assert imp.sorter_unit_ids[:3].tolist() == ["temp_0", "temp_1", "temp_2"]
    _check_units(imp, list(range(fx.N_UNITS)))
    assert set(imp.labels) == {"unsorted"}


def test_spykingcircus_needs_the_recording():
    try:
        read_spykingcircus(fixture().sc_result, electrodes=None, fs=None)
    except ValueError as e:
        assert "raw recording" in str(e)
    else:
        raise AssertionError("expected a ValueError")


def test_phy_reader_alone_and_with_maxwell_ids():
    f = fixture()
    imp = read_phy(f.phy)   # positions, fs from phy; no .dat → last spike
    assert imp.fs == fx.FS and imp.labels[fx.NOISE_UNIT] == "noise"
    np.testing.assert_array_equal(imp.peak_index, fx.UNIT_PEAK_ROW)
    meta = read_maxwell_meta(f.raw)
    imp = read_phy(f.phy, electrodes=ElectrodeTable.from_maxwell(meta),
                   duration_s=meta.duration_s)
    _check_units(imp, list(range(fx.N_UNITS)))


def test_find_sorted_output_prefers_merged_and_respects_names():
    f = fixture()
    assert find_sorted_output(f.folder, fx.NAME) == ("spykingcircus", f.sc_result)
    assert find_sorted_output(f.folder, fx.NAME, "phy") == ("phy", f.phy)
    # A recording whose name is a prefix of this one's (a plate vs its well)
    # must not claim its output: files only match at a ".", and a folder
    # matching a longer recording in the batch is that recording's.
    plate = fx.NAME[:-2]
    assert find_sorted_output(f.folder, plate, "spykingcircus") is None
    assert find_sorted_output(f.folder, plate, "phy", others=(plate, fx.NAME)) is None


# ── Into the spike file ───────────────────────────────────────────────────────

def test_layout_coords_flip_y_and_keep_aspect():
    coords, scale = layout_coords_from_um(np.array([[0, 0], [100, 0], [0, 50]]))
    # y = 0 µm is the top edge of a 50 µm-tall patch: 50 × 8/100 = 4 up.
    np.testing.assert_allclose(coords, [[0, 4], [8, 4], [0, 0]])
    assert scale == 8 / 100


def test_spike_file_drops_noise_and_names_units_by_electrode():
    f = fixture()
    meta = read_maxwell_meta(f.raw)
    imp = read_phy(f.phy, electrodes=ElectrodeTable.from_maxwell(meta), duration_s=meta.duration_s)
    sf = to_spike_file(imp)
    assert len(sf.channels) == fx.N_UNITS - 1
    assert str(fx.NOISE_UNIT) not in sf.units["sorter_unit_id"].tolist()
    for i, sid in enumerate(sf.units["sorter_unit_id"]):
        u = int(sid)
        assert sf.channels[i] == _expected_electrode(u)
        assert sf.units["id"][i].split("-")[0] == str(_expected_electrode(u))
        np.testing.assert_allclose(sf.spike_times[i][SORTED_METHOD], f.samples[u] / fx.FS)
    # Two units on one electrode are told apart, on a ring round it.
    ids = sf.units["id"].tolist()
    assert len(set(ids)) == len(ids)
    assert len(np.unique(sf.units["coords"], axis=0)) == len(ids)


# ── Through the pipeline ──────────────────────────────────────────────────────

def _run(tmp: Path, **overrides) -> Path:
    from meanap.pipeline.runner import run_pipeline

    f = fixture()
    sheet = tmp / "batch.csv"
    pd.DataFrame([{"Recording filename": fx.NAME, "DIV": 10, "Group": "Synth"}]).to_csv(
        sheet, index=False)
    p = Params(raw_data=str(f.folder), output_data_folder=str(tmp),
               output_data_folder_name="Run", spreadsheet_file_name=str(sheet),
               spreadsheet_range="2:100", spike_source="import",
               channel_layout="FromFile", random_seed=1, overwrite_existing_output=True,
               **overrides)
    run_pipeline(p, log=lambda m: None)
    return tmp / "Run"


def test_import_step_writes_a_sorted_spike_file():
    with tempfile.TemporaryDirectory() as d:
        out = _run(Path(d), stop_analysis_step=1)
        sf = load_spike_file(out / "1_SpikeDetection" / "1A_SpikeDetectedData"
                             / f"{fx.NAME}_spikes.npz")
        assert sf.sorted and sf.duration_s == fx.DURATION_S and sf.fs == fx.FS
        assert len(sf.channels) == fx.N_UNITS          # SpyKING CIRCUS: no curation
        np.testing.assert_array_equal(np.sort(sf.electrodes["ids"]), np.sort(fx.ELECTRODES))
        assert sf.methods == [SORTED_METHOD]


def test_a_recording_with_no_units_is_skipped_not_fatal(monkeypatch):
    import meanap.pipeline.import_step as step
    from meanap.pipeline.sorted_import import ImportedSorting

    # What a sorter that found nothing gives: the recording, and no units.
    empty = ImportedSorting(
        sorter="phy", sorter_unit_ids=np.array([], dtype=int), spike_trains=[],
        peak_index=np.array([], dtype=int),
        electrodes=ElectrodeTable(ids=np.asarray(fx.ELECTRODES), xy_um=fx.electrode_xy_um()),
        fs=fx.FS, duration_s=fx.DURATION_S, labels=np.array([], dtype=str))
    monkeypatch.setattr(step, "read_sorted_output", lambda *a, **k: empty)
    with tempfile.TemporaryDirectory() as d:
        out = _run(Path(d), stop_analysis_step=1)
        assert not (out / "1_SpikeDetection" / "1A_SpikeDetectedData"
                    / f"{fx.NAME}_spikes.npz").exists()


def test_from_file_layout_is_refused_up_front_without_an_import():
    import pytest

    from meanap.pipeline.runner import run_pipeline

    with tempfile.TemporaryDirectory() as d:
        sheet = Path(d) / "batch.csv"
        pd.DataFrame([{"Recording filename": fx.NAME, "DIV": 10, "Group": "Synth"}]).to_csv(
            sheet, index=False)
        p = Params(raw_data=str(fixture().folder), output_data_folder=d,
                   spreadsheet_file_name=str(sheet), channel_layout="FromFile")
        with pytest.raises(ValueError, match="FromFile"):
            run_pipeline(p, log=lambda m: None)
        # Refused before the run made anything.
        assert list(Path(d).iterdir()) == [sheet]


def test_light_responses_found_and_only_there():
    """End to end: import, steps 2–4 on the file's own layout, then the
    TTL-driven stim analysis with ON/OFF conditions."""
    with tempfile.TemporaryDirectory() as d:
        out = _run(Path(d), stop_analysis_step=4, func_con_lag_val=[25],
                   cartography_lag_val=[25], prob_thresh_rep_num=20,
                   stimulation_mode=True, stim_detection_method="maxwellTTL",
                   stim_event_condition_mode="alternate",
                   stim_event_condition_labels=["ON", "OFF"],
                   stim_analysis_window=[-0.3, 0.3], post_stim_window_dur=0.0,
                   stim_n_shuffles=50, stim_network_window=[0.0, 0.4],
                   stim_network_rep_num=50)
        rows = pd.read_csv(out / "StimActivity_NodeLevel.csv")
        assert set(rows["condition"]) == {"ON", "OFF"}
        assert rows["unit_id"].notna().all()
        # Which sorter unit each row is: unit IDs map back through the spike file.
        sf = load_spike_file(out / "1_SpikeDetection" / "1A_SpikeDetectedData"
                             / f"{fx.NAME}_spikes.npz")
        sorter = dict(zip(sf.units["id"], (int(s.split("_")[1]) for s in sf.units["sorter_unit_id"])))
        rows["unit"] = rows["unit_id"].map(sorter)
        responders = {"ON": set(fx.ON_RESPONDERS), "OFF": set(fx.OFF_RESPONDERS)}
        for cond, truth in responders.items():
            z = rows[rows["condition"] == cond].set_index("unit")["zscore"]
            # A clear gap, not a lucky threshold: responders well above,
            # everything else near zero.
            assert set(z.index[z > 3]) == truth, (cond, z.round(1).to_dict())
            assert z.drop(list(truth)).max() < 2, (cond, z.round(1).to_dict())
        # Step 2–4 ran on the file's own layout and drew the networks.
        assert (out / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv").exists()
        heat = list((out / "2_NeuronalActivity").rglob("2_Heatmap.png"))
        assert heat, "no firing-rate heatmap drawn from the FromFile layout"
        assert (out / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / "Synth"
                / fx.NAME / "stim_events.csv").exists()
        # Stimulus-triggered networks: a row per condition × epoch × lag plus
        # noise correlations, and every node in the node-level table.
        net = pd.read_csv(out / "StimNetwork_RecordingLevel.csv")
        assert set(zip(net["condition"], net["epoch"])) >= {
            ("ON", "evoked"), ("ON", "baseline"), ("OFF", "noise_corr")}
        nodes = pd.read_csv(out / "StimNetwork_NodeLevel.csv")
        assert len(nodes) == 2 * fx.N_UNITS and nodes["unit_id"].notna().all()
        assert (out / "ExperimentMatFiles" / f"{fx.NAME}_stimNetwork.npz").exists()
        assert list((out / "2_NeuronalActivity").rglob("13_StimNetwork_ON_25mslag.png"))


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
