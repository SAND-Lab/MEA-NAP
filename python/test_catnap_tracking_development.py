"""The tracked-cell metric table: joining tracking to the pipeline's node tables.

Both joins fail silently when wrong. A recording matched to the wrong pipeline
recording, or a tracking position mapped to the wrong channel, still yields
a full table of plausible numbers. So each test checks that a specific cell
picks up the values of its own channel.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from meanap.catnap.tracking.development import (
    TRACKED_METRICS_CSV, BuildReport, FileNameIndex, build_for_run, name_key,
    refresh_cell_types, tracked_cell_metrics,
)

CHAIN = "7_PREP1_P1_pupA_WT"
#: The pipeline's names: no date, tokens in another order from the raw names.
REC = {10: "PREP1_7_P1_pupA_WT_DIV10", 20: "PREP1_7_P1_pupA_WT_DIV20"}


def _payload(recordings=True, roi=True) -> dict:
    """Two days. Raw ROIs 0..4 on day 1, 0..3 on day 2; ROI 1 is never a cell.

    Cluster 0 is on both days, cluster 1 on both, cluster 2 on day 1 only.
    """
    s1 = {"div": 10, "cluster": [0, 1, 2, -1]}          # iscell raw ids 0,2,3,4
    s2 = {"div": 20, "cluster": [1, -1, 0]}             # iscell raw ids 0,2,3
    if recordings:
        s1["recording"] = "20240101_7_PREP1_P1_pupA_WT_DIV10"
        s2["recording"] = "20240111_7_PREP1_P1_pupA_WT_DIV20"
    if roi:
        s1["roi"], s2["roi"] = [0, 2, 3, 4], [0, 2, 3]
    return {"chainKey": CHAIN, "sessions": [s1, s2],
            "cells": [{"cluster": 0, "rescuedDivs": [20], "mergedDivs": []}]}


def _activity() -> pd.DataFrame:
    rows = []
    for div, rec in REC.items():
        chans = [1, 3, 4, 5] if div == 10 else [1, 3, 4]
        for ch in chans:
            # the value encodes (day, channel), so a misjoin is visible
            rows.append({"FileName": rec, "Grp": "WT", "DIV": float(div), "Channel": ch,
                         "FR": div + ch / 10})
    return pd.DataFrame(rows)


def _network(lags=("1000mslag",)) -> pd.DataFrame:
    rows = []
    for lag in lags:
        for div, rec in REC.items():
            # channel 4 on DIV20 is below the activity threshold: no row
            chans = [1, 3, 4, 5] if div == 10 else [1, 3]
            for i, ch in enumerate(chans):
                rows.append({"FileName": rec, "Grp": "WT", "DIV": float(div), "Lag": lag,
                             "Channel": ch, "activeChannelIndex": i, "Ci": 1,
                             "ND": 100 * div + ch + (0.5 if lag != "1000mslag" else 0)})
    return pd.DataFrame(rows)


def _value(df, cluster, div, col, lag=None):
    sel = (df["cluster"] == cluster) & (df["DIVrecorded"] == div)
    if lag is not None:
        sel &= df["Lag"] == lag
    vals = df.loc[sel, col]
    assert len(vals) == 1, vals
    return vals.iloc[0]


def test_name_key_ignores_order_and_date():
    assert name_key("20240101_7_PREP1_P1_pupA_WT_DIV10") == name_key(REC[10])
    assert name_key(REC[10]) != name_key(REC[20])


def test_ambiguous_key_matches_nothing():
    idx = FileNameIndex.from_names(["A_B_DIV3", "B_A_DIV3", "C_DIV3"])
    assert idx.find("20240101_A_B_DIV3", "x", 3) is None
    assert idx.find("A_B_DIV3", "x", 3) == "A_B_DIV3"      # exact still wins
    assert idx.find(None, "C", 3) == "C_DIV3"              # by chain and DIV


def test_cells_pick_up_their_own_channel():
    df = tracked_cell_metrics([_payload()], _activity(), _network())
    # cluster 0: raw 0 on DIV10 (ch 1), raw 3 on DIV20 (ch 4)
    assert _value(df, 0, 10, "FR") == 10.1 and _value(df, 0, 10, "ND") == 1001
    assert _value(df, 0, 20, "FR") == 20.4
    # cluster 1: raw 2 on DIV10 (ch 3), raw 0 on DIV20 (ch 1)
    assert _value(df, 1, 10, "FR") == 10.3 and _value(df, 1, 20, "ND") == 2001
    # single-day cluster 2 is not a tracked cell
    assert 2 not in set(df["cluster"])
    assert "Ci" not in df and "activeChannelIndex" not in df


def test_inactive_day_is_nan_not_dropped():
    df = tracked_cell_metrics([_payload()], _activity(), _network())
    assert np.isnan(_value(df, 0, 20, "ND"))
    assert len(df) == 4


def test_channel_list_fallback_and_chain_fallback():
    """Old payloads: no recording names and no raw ids."""
    report = BuildReport()
    df = tracked_cell_metrics([_payload(recordings=False, roi=False)],
                              _activity(), _network(), report=report)
    # positions map onto the run's channel list in order, as with stored ids
    assert _value(df, 0, 20, "FR") == 20.4
    assert _value(df, 1, 10, "FR") == 10.3
    assert not report.unmatched_days and not report.unmapped_days


def test_count_mismatch_is_reported_not_guessed():
    act = _activity()
    act = act[~((act.FileName == REC[20]) & (act.Channel == 4))]
    report = BuildReport()
    df = tracked_cell_metrics([_payload(roi=False)], act, None, report=report)
    assert set(df["DIVrecorded"]) == {10}
    assert len(report.unmapped_days) == 1 and "DIV20" in report.unmapped_days[0]


def test_every_lag_and_measure_gets_its_rows():
    act = pd.concat([_activity().assign(ActivityType=a) for a in ("peaks", "spks")])
    net = pd.concat([_network(("1000mslag", "500mslag")).assign(ActivityType=a)
                     for a in ("peaks", "spks")])
    df = tracked_cell_metrics([_payload()], act, net)
    assert len(df) == 4 * 2 * 2
    sub = df[df["ActivityType"] == "spks"]
    assert _value(sub, 1, 20, "ND", "500mslag") == 2001.5


def test_cell_types_and_day_source():
    calls = {(CHAIN, 0): {"Mecp2": "+", "NeuN": ""}, (CHAIN, 1): {"Mecp2": "-"}}
    df = tracked_cell_metrics([_payload()], _activity(), _network(), calls)
    assert _value(df, 0, 10, "celltype_Mecp2") == "+"
    assert _value(df, 1, 10, "celltype_Mecp2") == "-"
    assert _value(df, 1, 10, "celltype_NeuN") == ""
    assert _value(df, 0, 20, "dayVia") == "rescued"
    assert _value(df, 0, 10, "dayVia") == "roicat"


def _run_folder(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "2_NeuronalActivity").mkdir(parents=True)
    (run / "4_NetworkActivity").mkdir()
    _activity().to_csv(run / "2_NeuronalActivity" / "TwoPhotonActivity_NodeLevel.csv",
                       index=False)
    _network().to_csv(run / "4_NetworkActivity" / "NetworkActivity_NodeLevel.csv",
                      index=False)
    root = run / "CellTracking"
    (root / "payload").mkdir(parents=True)
    (root / "payload" / f"{CHAIN}.json").write_text(json.dumps(_payload()))
    (root / "cell_types_final.csv").write_text(
        "chain,cluster,marker,final\n"
        f"{CHAIN},0,Mecp2,+\n{CHAIN},1,Mecp2,\n")
    return root


def test_build_and_refresh(tmp_path):
    root = _run_folder(tmp_path)
    df = build_for_run(root)
    assert (root / TRACKED_METRICS_CSV).is_file() and len(df) == 4

    # a decision is saved: cluster 1 becomes Mecp2- and a new marker appears
    (root / "cell_types_final.csv").write_text(
        "chain,cluster,marker,final\n"
        f"{CHAIN},0,Mecp2,+\n{CHAIN},1,Mecp2,-\n{CHAIN},1,GAD,+\n")
    assert refresh_cell_types(root)
    after = pd.read_csv(root / TRACKED_METRICS_CSV, keep_default_na=False,
                        dtype={"celltype_Mecp2": str, "celltype_GAD": str})
    assert _value(after, 1, 20, "celltype_Mecp2") == "-"
    assert _value(after, 1, 20, "celltype_GAD") == "+"
    assert _value(after, 0, 20, "celltype_GAD") == ""
    # nothing else moved
    def plain(cols):
        return [c for c in cols if not c.startswith("celltype_")]
    assert plain(after.columns) == plain(df.columns)
    assert list(after.columns[10:12]) == ["celltype_GAD", "celltype_Mecp2"]
    assert float(_value(after, 1, 10, "FR")) == 10.3


def test_no_tracking_table_without_run_tables(tmp_path):
    root = tmp_path / "CellTracking"
    (root / "payload").mkdir(parents=True)
    assert build_for_run(root).empty
    assert not refresh_cell_types(root)


def _service(run: Path):
    """The viewer service on a run folder, without loading a full run context."""
    from meanap.viewer.server import ViewerService

    svc = ViewerService.__new__(ViewerService)
    svc._bundle, svc.source = None, run
    return svc


def _many_cells_payload(n: int = 12) -> dict:
    """One chain, two days, *n* cells tracked across both (raw id = position)."""
    sessions = [{"div": d, "cluster": list(range(n)), "roi": list(range(n)),
                 "recording": REC[d]} for d in (10, 20)]
    return {"chainKey": CHAIN, "sessions": sessions, "cells": []}


def test_viewer_endpoint_follows_saved_decisions(tmp_path):
    import os
    import time

    n = 12
    root = _run_folder(tmp_path)
    run = root.parent
    act = pd.DataFrame([{"FileName": REC[d], "Grp": "WT", "DIV": float(d), "Channel": c + 1,
                         "FR": d + c / 100} for d in (10, 20) for c in range(n)])
    act.to_csv(run / "2_NeuronalActivity" / "TwoPhotonActivity_NodeLevel.csv", index=False)
    (root / "payload" / f"{CHAIN}.json").write_text(json.dumps(_many_cells_payload(n)))
    final = "chain,cluster,marker,final\n" + "".join(
        f"{CHAIN},{c},M,{'+' if c < 6 else '-'}\n" for c in range(n))
    (root / "cell_types_final.csv").write_text(final)
    build_for_run(root)
    svc = _service(run)

    meta = svc.tracking_development()
    assert meta["available"] and meta["groups"] == ["WT"]
    (d,) = meta["definitions"]
    rows = {t["name"]: t["rows"] for t in d["types"]}
    assert len(rows["M+"]) == 12 and len(rows["M-"]) == 12      # 6 cells x 2 days each

    # values line up with the cell-days the meta listed
    vals = svc.tracking_development("FR")["values"]
    r = meta["rows"]
    for i in range(len(vals)):
        assert vals[i] == pytest.approx(r["divRecorded"][i] + r["cluster"][i] / 100)

    # stats saved, then a decision: the view follows it and flags the tables as stale
    stats = root / "DevelopmentByCellType"
    stats.mkdir()
    (stats / "Stats_MixedModel.csv").write_text("metric,term,p\nFR,age,0.5\n")
    past = time.time() - 60
    os.utime(stats / "Stats_MixedModel.csv", (past, past))
    (root / "cell_types_final.csv").write_text(final.replace(f"{CHAIN},0,M,+", f"{CHAIN},0,M,-"))
    meta = svc.tracking_development()
    rows = {t["name"]: t["rows"] for t in meta["definitions"][0]["types"]}
    assert len(rows["M+"]) == 10 and len(rows["M-"]) == 14
    assert meta["statsStale"]
    assert svc.tracking_development("FR")["mixed"][0]["term"] == "age"


def test_viewer_endpoint_without_a_table(tmp_path):
    root = tmp_path / "run" / "CellTracking"
    (root / "payload").mkdir(parents=True)
    assert _service(root.parent).tracking_development() == {"available": False}
