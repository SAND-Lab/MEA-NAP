"""Stimulation conditions: sequence grouping, names, StimConditions labels, group figures.

The case that motivated it: four electrodes in a row, swept left-to-right and
right-to-left alternately, 10 ms between pulses. MATLAB's electrode grouping
makes that four patterns, each mixing both directions; sequence grouping must
make it two, one per direction.

    .venv/bin/python -m pytest python/test_stim_sequences.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.stim.detection import get_stim_patterns  # noqa: E402
from meanap.stim.events import stim_info_without_stim_nodes  # noqa: E402
from meanap.stim.sequences import (  # noqa: E402
    apply_labels, assign_patterns, conditions_from_patterns, group_sequences,
    parse_condition_labels,
)

ONSETS = np.arange(1.0, 101.0, 2.5)            # 40 stimuli
ROW = [12, 13, 14, 15]


def _info(channels=(10, 11, *ROW, 20)):
    return stim_info_without_stim_nodes(np.array(channels), np.zeros((len(channels), 2)))


def _sweeps(delay=0.010):
    """Alternate L→R and R→L sweeps over ROW; electrodes 10, 11, 20 are not stimulated."""
    info = _info()
    ltr = np.arange(len(ONSETS)) % 2 == 0
    for k, ch in enumerate(ROW):
        pos = np.where(ltr, k, len(ROW) - 1 - k)
        info[2 + k].elec_stim_times = ONSETS + pos * delay
    return info


def test_matlab_grouping_mixes_sweep_directions():
    """The bug sequence grouping exists for: one 'pattern' per electrode."""
    _, pats = get_stim_patterns(_sweeps(), {"stimTimeDiffThreshold": 0.005})
    assert len(pats) == 4


def test_sweeps_become_one_condition_per_direction():
    info = _sweeps()
    conds = group_sequences(info, gap_s=0.05)
    assert [c.name for c in conds] == ["12>13>14>15", "15>14>13>12"]
    for c in conds:
        assert c.onsets_s.size == 20
        assert c.last_pulse_s == pytest.approx(0.030)
    np.testing.assert_allclose(conds[0].onsets_s, ONSETS[0::2])
    np.testing.assert_allclose(conds[1].onsets_s, ONSETS[1::2])
    assign_patterns(info, conds)
    assert info[2].pattern_ids == (1, 2) and info[2].pattern == 1
    assert info[0].pattern_ids == () and info[0].pattern == 0


def test_simultaneous_sets_and_speeds():
    info = _info()
    a = np.arange(len(ONSETS)) % 2 == 0
    for i in (2, 3):                                   # 12+13 together on even stimuli
        info[i].elec_stim_times = ONSETS[a]
    for i in (4, 5):                                   # 14+15 together on odd stimuli
        info[i].elec_stim_times = ONSETS[~a]
    assert [c.name for c in group_sequences(info, 0.05)] == ["12+13", "14+15"]

    fast, slow = _sweeps(0.005), _sweeps(0.020)        # one order at two speeds
    info = _info()
    for i in range(2, 6):
        info[i].elec_stim_times = np.sort(np.r_[fast[i].elec_stim_times,
                                                slow[i].elec_stim_times + 200])
    names = [c.name for c in group_sequences(info, 0.1)]
    assert "12>13>14>15 (5/10/15 ms)" in names and "12>13>14>15 (20/40/60 ms)" in names


def test_rare_sequence_left_out():
    info = _sweeps()
    info[3].elec_stim_times = info[3].elec_stim_times[1:]   # electrode 13 missed once
    logs = []
    conds = group_sequences(info, 0.05, log=logs.append)
    assert {c.name: c.onsets_s.size for c in conds} == {"12>13>14>15": 19, "15>14>13>12": 20}
    assert "12>14>15 (1)" in logs[0]


def test_conditions_from_matlab_patterns_named_by_electrodes():
    info = _info()
    for i in (2, 3):
        info[i].elec_stim_times = ONSETS.copy()
    info, pats = get_stim_patterns(info, {"stimTimeDiffThreshold": 0.005})
    assert [c.name for c in conditions_from_patterns(info, pats)] == ["12+13"]


def test_labels():
    assert parse_condition_labels(None) is None and parse_condition_labels(" nan ") is None
    assert parse_condition_labels("hub") == "hub"
    assert parse_condition_labels("LtoR=12>13>14>15; RtoL = 15>14>13>12") == {
        ((12,), (13,), (14,), (15,)): "LtoR", ((15,), (14,), (13,), (12,)): "RtoL"}
    assert parse_condition_labels("A=13+12") == {((12, 13),): "A"}
    with pytest.raises(ValueError):
        parse_condition_labels("A=12>x")

    conds = group_sequences(_sweeps(), 0.05)
    logs = []
    apply_labels(conds, "LtoR=12>13>14>15; other=99", logs.append)
    assert [c.display_name for c in conds] == ["LtoR", "15>14>13>12"]
    assert "99" in logs[0]
    with pytest.raises(ValueError, match="2 conditions"):
        apply_labels(group_sequences(_sweeps(), 0.05), "hub")
    with pytest.raises(ValueError, match="two conditions"):
        apply_labels(group_sequences(_sweeps(), 0.05), "X=12>13>14>15; X=15>14>13>12")


def test_spreadsheet_column(tmp_path):
    from meanap.pipeline.spreadsheet import read_recording_csv

    p = tmp_path / "a.csv"
    p.write_text("Filename,DIV,Genotype,StimConditions\nrecA,14,WT,hub\nrecB,14,KO,\n")
    a, b = read_recording_csv(p, "A2:A3")
    assert a.stim_conditions == "hub" and a.ground is None and b.stim_conditions is None
    p.write_text("Filename,DIV,Genotype,Ground,StimConditions\nrecA,14,WT,15,LtoR=1>2\n")
    (a,) = read_recording_csv(p, "A2:A2")
    assert a.ground == "15" and a.stim_conditions == "LtoR=1>2"


def test_pipeline_conditions_and_windows():
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import _post_artifact_window, _recording_conditions

    info = _sweeps()
    info, pats = get_stim_patterns(info, {"stimTimeDiffThreshold": 0.005})
    rec = RecordingInfo("r", 14, "WT", stim_conditions="LtoR=12>13>14>15; RtoL=15>14>13>12")
    conds, pats = _recording_conditions(Params(stim_group_sequences=True), rec, info, pats,
                                        lambda *_: None)
    assert [c.display_name for c in conds] == ["LtoR", "RtoL"] and len(pats) == 2
    win = _post_artifact_window([0.0, 0.5], conds[0].last_pulse_s + 0.002, lambda *_: None)
    assert win == pytest.approx((0.032, 0.5))


def _tables():
    rng = np.random.default_rng(0)
    net, split, cons = [], [], []
    for grp in ("WT", "KO"):
        for div in (14, 21):
            for r in range(5):
                fn = f"{grp}{div}_{r}"
                for cond, eff in (("hub", 0.1), ("periphery", 0.02)):
                    base = {"FileName": fn, "Grp": grp, "DIV": div, "condition": cond}
                    d = rng.normal(0.3, 0.03)
                    for epoch, v in (("baseline", d), ("evoked", d + eff)):
                        net.append({**base, "epoch": epoch, "lag_ms": 10, "Dens": v,
                                    "aN": 50, "meanSTTC": v / 2})
                    net.append({**base, "epoch": "noise_corr", "lag_ms": np.nan,
                                "meanNoiseCorr": rng.normal(0.2, 0.05),
                                "fracSigNoiseCorr": 0.3})
                    for sp in ("odd_even", "first_second"):
                        split.append({**base, "lag_ms": 10, "split": sp, "epoch": "evoked",
                                      "r_sttc": 0.8, "r_excess": rng.normal(0.6, 0.1)})
                    cons.append({**base, "popResponseRho": rng.normal(0, 0.1),
                                 "fracNodesDrifting": 0.05, "medianLatency_ms": 5.0})
    return {"StimNetwork_RecordingLevel.csv": net,
            "StimNetworkSplitHalf_RecordingLevel.csv": split,
            "StimConsistency_RecordingLevel.csv": cons}


def test_group_figures(tmp_path):
    from meanap.stim.group_plots import change_frame, plot_stim_group_comparisons

    tables = _tables()
    change = change_frame(pd.DataFrame(tables["StimNetwork_RecordingLevel.csv"]), ["Dens"])
    assert change.groupby("condition")["Dens"].mean().to_dict() == pytest.approx(
        {"hub": 0.1, "periphery": 0.02})
    from meanap.stim.group_plots import response_frame
    resp = response_frame(pd.DataFrame(tables["StimNetwork_RecordingLevel.csv"]),
                          pd.DataFrame(tables["StimConsistency_RecordingLevel.csv"]))
    assert len(resp) == 40 and resp["popResponseRho"].notna().all()
    assert resp["meanNoiseCorr"].notna().all()
    n = plot_stim_group_comparisons(tables, tmp_path, group_order=["WT", "KO"],
                                    log=lambda *_: None)
    root = tmp_path / "StimNetwork_GroupComparisons"
    assert (root / "1_ChangeByGroup" / "10mslag" / "2_density_byGroup.png").exists()
    assert (root / "2_ChangeByAge" / "10mslag" / "2_density_byAge.png").exists()
    assert (root / "3_EpochsByGroup" / "hub" / "10mslag" / "2_density_byGroup.png").exists()
    assert (root / "5_ResponseByGroup" / "10mslag").is_dir()
    assert (root / "6_ResponseByAge" / "1_mean noise correlation_byAge.png").exists()
    assert n == len(list(root.rglob("*.png")))
