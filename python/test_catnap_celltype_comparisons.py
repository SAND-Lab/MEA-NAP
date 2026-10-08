"""Cross-sectional cell-type comparisons: calls for every cell, then figures.

The calls are what can go silently wrong:

* a label file under its raw name (with the imaging date) must still be found;
* raw ROI ids must land on the right ``Channel``;
* a tracked cell must take its final call, and an undecided one must become
  unknown rather than keep the disputed day's label.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from meanap.catnap import celltype_comparisons as cc

REC = "PREP1_7_P1_pupA_WT_DIV10"          # the pipeline's name
RAW = "20240101_7_PREP1_P1_pupA_WT_DIV10"  # the label file's name


def _labels(folder: Path, name: str = RAW) -> None:
    # raw ids: 0, 2, 3 NeuN+; 5 NeuN-; GAD lists positives only
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.csv").write_text(
        "NeuN_Positive,NeuN_Negative,GAD+\n0,5,3\n2,,\n3,,\n")


def test_calls_find_raw_named_files_and_keep_unknowns(tmp_path):
    _labels(tmp_path / "labels")
    # channels = raw id + 1; raw 1 and 4 are not cells
    calls = cc.cell_calls({REC: np.array([1, 3, 4, 6])}, [tmp_path / "labels"])
    by = calls.set_index("Channel")
    assert by.loc[1, "celltype_NeuN"] == "+" and by.loc[3, "celltype_NeuN"] == "+"
    assert by.loc[6, "celltype_NeuN"] == "-"
    # raw 3 (channel 4) is NeuN+ and GAD+; GAD is positive-only, so others are GAD-
    assert by.loc[4, "celltype_GAD"] == "+" and by.loc[1, "celltype_GAD"] == "-"
    assert set(calls["callSource"]) == {"label file"}


def test_recording_without_a_file_is_left_out(tmp_path):
    _labels(tmp_path / "labels")
    calls = cc.cell_calls({REC: np.array([1, 3, 4, 6]), "OTHER_DIV10": np.array([1])},
                          [tmp_path / "labels"])
    assert set(calls["FileName"]) == {REC}


def test_tracked_cells_take_their_final_call(tmp_path):
    _labels(tmp_path / "labels")
    track = tmp_path / "CellTracking"
    track.mkdir()
    pd.DataFrame({"chain": "c", "cluster": [0, 1], "FileName": REC, "Channel": [1, 3],
                  "Lag": "1000mslag"}).to_csv(track / "TrackedCellMetrics.csv", index=False)
    # cluster 0 judged NeuN- overall; cluster 1 a tie nobody decided
    (track / "cell_types_final.csv").write_text(
        "chain,cluster,marker,final\nc,0,NeuN,-\nc,1,NeuN,\n")
    calls = cc.cell_calls({REC: np.array([1, 3, 4])}, [tmp_path / "labels"],
                          tracking_dir=track).set_index("Channel")
    assert calls.loc[1, "celltype_NeuN"] == "-"
    assert calls.loc[3, "celltype_NeuN"] == ""        # disputed: unknown, not "+"
    assert calls.loc[4, "celltype_NeuN"] == "+"       # untracked: its own label
    assert calls.loc[1, "callSource"] == "tracked cell, final call"


def test_recording_means_make_n_recordings():
    df = pd.DataFrame({"FileName": ["a"] * 3 + ["b"], "Grp": "g", "DIV": 10,
                       "CellType": "T", "FR": [1.0, 2.0, 3.0, 10.0]})
    m = cc.recording_means(df, ["FR"]).set_index("FileName")
    assert m.loc["a", "FR"] == 2.0 and m.loc["a", "nCells"] == 3 and len(m) == 2


def _run(tmp_path: Path) -> Path:
    """Six recordings, two groups, 12 cells each; even channels NeuN+."""
    run = tmp_path / "run"
    (run / "2_NeuronalActivity").mkdir(parents=True)
    (run / "4_NetworkActivity").mkdir()
    rng = np.random.default_rng(0)
    act, net = [], []
    labels = tmp_path / "labels"
    labels.mkdir()
    for g in ("WT", "KO"):
        for k, div in enumerate((7, 14, 21)):
            rec = f"PREP{k}_1_{g}_DIV{div}"
            raw0 = [c - 1 for c in range(1, 13)]
            (labels / f"2024010{k}_1_PREP{k}_{g}_DIV{div}.csv").write_text(
                "NeuN_Positive,NeuN_Negative\n" + "\n".join(
                    f"{a},{b}" for a, b in zip(raw0[0::2], raw0[1::2])) + "\n")
            for ch in range(1, 13):
                act.append({"FileName": rec, "Grp": g, "DIV": float(div), "Channel": ch,
                            "FR": rng.random()})
                net.append({"FileName": rec, "Grp": g, "DIV": float(div), "Lag": "1000mslag",
                            "Channel": ch, "activeChannelIndex": ch - 1, "Ci": 1,
                            "ND": rng.integers(1, 11), "NdCartDiv": 6})
    pd.DataFrame(act).to_csv(run / cc.ACTIVITY_CSV, index=False)
    pd.DataFrame(net).to_csv(run / cc.NETWORK_CSV, index=False)
    return run


def test_end_to_end_and_rebuild_from_saved_calls(tmp_path):
    run = _run(tmp_path)
    calls = cc.plot_cell_type_comparisons(run, label_folders=[tmp_path / "labels"],
                                          group_order=["WT", "KO"])
    assert calls["FileName"].nunique() == 6
    assert (run / "2_NeuronalActivity" / cc.CALLS_CSV).is_file()
    act = run / cc.ACTIVITY_DIR / "NeuN"
    net = run / cc.NETWORK_DIR / "Lag1000ms" / "NeuN"
    for d in (act, net):
        for sub in ("NodeByGroup", "NodeByAge", "RecordingsByGroup", "RecordingsByAge"):
            assert any((d / sub).iterdir()), d / sub
    assert (act / "RecordingsByGroup" / "FR_byGroup.png").is_file()
    assert (net / "NodeByAge" / "ND_byDIV_node.png").is_file()
    assert (net / "RecordingsByGroup" / "NDnorm_byGroup.png").is_file()
    # roles are categorical, never averaged into a violin
    assert not (net / "NodeByGroup" / "NdCartDiv_byGroup_node.png").exists()

    # a bundle has no label files: the saved calls alone rebuild the same set
    out = tmp_path / "rendered"
    again = cc.plot_cell_type_comparisons(run, out_dir=out, group_order=["WT", "KO"])
    assert len(again) == len(calls)
    made = {p.relative_to(out) for p in out.rglob("*.png")}
    first = {p.relative_to(run) for p in (run / cc.ACTIVITY_DIR).parent.parent.rglob("*.png")
             if "CellTypeComparisons" in str(p)}
    first |= {p.relative_to(run) for p in (run / "4_NetworkActivity").rglob("*.png")}
    assert made == first
