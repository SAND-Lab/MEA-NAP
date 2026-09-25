"""Cell types on tracked cells: reading, ID-space mapping, annotation.

The ID-space test is the one that matters. Cell-type files hold raw suite2p
indices while tracking works on iscell positions, and with non-iscell ROIs
interleaved an off-by-mapping bug labels the wrong cell with no error at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from meanap.catnap.tracking.celltypes import (
    NEG, POS, UNKNOWN,
    annotate_payload, annotate_tracking_dir, cell_call, place_labels,
    read_marker_labels,
)

HEADER = ("NeuN_Positive,NeuN_Negative,Comments on NeuN,"
          "Mecp2_Positive,Mecp2_Negative,Comments on Mecp2")


def _write(path: Path, rows: list[str], header: str = HEADER) -> Path:
    # a byte-order mark, as the real files carry
    path.write_text("﻿" + "\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_reads_positive_negative_columns_and_skips_numeric_comments(tmp_path):
    f = _write(tmp_path / "rec.csv", [
        "0,,2 cells,,0,",
        ",1,,1,,11",       # "11" in a comments column is a note, not an ROI
        "3,,,3,,",
    ])
    labels = read_marker_labels(f)
    assert labels.markers == ["Mecp2", "NeuN"]
    assert labels.positive["NeuN"] == {0, 3}
    assert labels.negative["NeuN"] == {1}
    assert labels.positive["Mecp2"] == {1, 3}
    assert labels.negative["Mecp2"] == {0}
    assert 11 not in labels.ids()
    assert labels.positive_only == set()


def test_positive_only_format_treats_unlisted_as_negative(tmp_path):
    f = _write(tmp_path / "rec.csv", ["0,4", "2,"], header="NeuN+,GAD+")
    labels = read_marker_labels(f)
    assert labels.positive_only == {"NeuN", "GAD"}
    placed = place_labels(labels, np.array([0, 2, 4]))
    assert placed.states["NeuN"].tolist() == [POS, POS, NEG]
    assert placed.states["GAD"].tolist() == [NEG, NEG, POS]


def test_raw_ids_map_to_iscell_positions(tmp_path):
    # raw ROIs 0..5, of which 1 and 4 are not cells: positions are 0,2,3,5
    roi_index = np.array([0, 2, 3, 5])
    f = _write(tmp_path / "rec.csv", ["2,,,5,,", "5,,,,2,", ",3,,,,"])
    placed = place_labels(read_marker_labels(f), roi_index)
    assert placed.states["NeuN"].tolist() == [UNKNOWN, POS, NEG, POS]
    assert placed.states["Mecp2"].tolist() == [UNKNOWN, NEG, UNKNOWN, POS]


def test_unlabelled_stays_unknown_and_conflicts_are_dropped(tmp_path):
    f = _write(tmp_path / "rec.csv", ["0,0,,,,", "1,,,,,"])
    placed = place_labels(read_marker_labels(f), np.array([0, 1, 2]))
    assert placed.states["NeuN"].tolist() == [UNKNOWN, POS, UNKNOWN]
    assert placed.conflicts == 1


def test_file_from_another_recording_is_rejected(tmp_path):
    f = _write(tmp_path / "rec.csv", [f"{i},,,,," for i in range(100, 160)])
    with pytest.raises(ValueError, match="another recording"):
        place_labels(read_marker_labels(f), np.arange(20))


def test_cell_call():
    assert cell_call([POS, UNKNOWN, POS]) == "+"
    assert cell_call([NEG, NEG]) == "-"
    assert cell_call([POS, NEG]) == "~"
    assert cell_call([UNKNOWN, UNKNOWN]) is None


def _payload(clusters_by_day, divs):
    """A minimal viewer payload: one cell per cluster, on every day it appears."""
    sessions = [{"div": d, "cluster": list(c)} for d, c in zip(divs, clusters_by_day)]
    ids = sorted({c for day in clusters_by_day for c in day if c >= 0})
    cells = []
    for cid in ids:
        pos = [[k, 0.0, 0.0] for k, day in enumerate(clusters_by_day) if cid in day]
        cells.append({"cluster": cid, "positions": pos,
                      "divs": [divs[k] for k, _, _ in pos]})
    return {"sessions": sessions, "cells": cells}


def test_annotate_payload_follows_each_cell_through_its_days(tmp_path):
    from meanap.catnap.tracking.celltypes import SessionLabels

    # cluster 7 sits at position 0 on day 1 and position 2 on day 2
    payload = _payload([[7, 8, -1], [-1, 8, 7]], [14, 21])
    day1 = SessionLabels("a", "a.csv", {"Mecp2": np.array([POS, NEG, NEG], np.int8)})
    day2 = SessionLabels("b", "b.csv", {"Mecp2": np.array([UNKNOWN, POS, POS], np.int8)})
    agreement = annotate_payload(payload, [day1, day2])
    by = {c["cluster"]: c for c in payload["cells"]}
    assert by[7]["types"]["Mecp2"] == [POS, POS]
    assert by[7]["typeCall"]["Mecp2"] == "+"
    assert by[8]["types"]["Mecp2"] == [NEG, POS]
    assert by[8]["typeCall"]["Mecp2"] == "~"
    assert agreement["Mecp2"]["pairs"] == 2 and agreement["Mecp2"]["agree"] == 1
    assert payload["sessions"][0]["labels"]["Mecp2"] == [1, -1, -1]


def test_annotate_tracking_dir_end_to_end(tmp_path):
    """An old-style run: payloads without ``roi``/``recording``; the label file's
    date disagrees with the recording's; iscell has a non-cell interleaved."""
    ct = tmp_path / "CellTracking"
    for d in ("payload", "chains", "viewer"):
        (ct / d).mkdir(parents=True)
    key = "OPME1_3_P1_pup1A_Het_MOI1"
    payload = _payload([[0, 1, -1], [1, -1, 0]], [14, 21])
    payload.update(chainKey=key, chain="Tracked cells", subtitle="", fs=30.0,
                   frame=64, fovPreviewPx=64, maskPreviewPx=64, pools={})
    (ct / "payload" / f"{key}.json").write_text(json.dumps(payload))
    # an old network: no "clusters", so nodes are rebuilt as the cells present
    # on two or more days, sorted by cluster id
    (ct / "chains" / f"{key}.json").write_text(json.dumps(
        {"genotype": "Het", "network": {"nCells": 2, "days": [{}, {}]}}))
    (ct / "summary.json").write_text("{}")

    s2p = tmp_path / "masks"
    rec14 = "OPME1_3_20230101_P1_pup1A_Het_MOI1_DIV14"
    rec21 = "OPME1_3_20230108_P1_pup1A_Het_MOI1_DIV21"
    for rec, iscell in ((rec14, [1, 0, 1, 1]), (rec21, [1, 1, 1])):
        (s2p / rec).mkdir(parents=True)
        np.save(s2p / rec / "iscell.npy",
                np.array([[v, 0.9] for v in iscell], dtype=float))

    labels = tmp_path / "labels"
    labels.mkdir()
    # DIV14: raw 0 → pos 0, raw 2 → pos 1 (raw 1 is not a cell)
    _write(labels / f"{rec14}.csv", ["0,,,,2,", ",,,0,,", "2,,,,,", "3,,,3,,"])
    # DIV21 file carries the wrong date; matched by chain and DIV instead
    _write(labels / "OPME1_3_20230107_P1_pup1A_Het_MOI1_DIV21.csv",
           ["0,,,,1,", "1,,,0,,", "2,,,2,,"])

    report = annotate_tracking_dir(ct, [labels], suite2p_roots=[s2p])
    assert report.labelled_days == 2 and not report.rejected
    assert len(report.renamed) == 1

    out = json.loads((ct / "payload" / f"{key}.json").read_text())
    assert out["sessions"][0]["roi"] == [0, 2, 3]
    assert out["sessions"][1]["recording"] == rec21
    by = {c["cluster"]: c for c in out["cells"]}
    # cluster 0: day 1 pos 0 = raw 0 (Mecp2+); day 2 pos 2 = raw 2 (Mecp2+)
    assert by[0]["types"]["Mecp2"] == [POS, POS]
    # cluster 1: day 1 pos 1 = raw 2 (Mecp2-); day 2 pos 0 = raw 0 (Mecp2+)
    assert by[1]["typeCall"]["Mecp2"] == "~"

    meta = json.loads((ct / "chains" / f"{key}.json").read_text())
    assert meta["cell_types"]["labelled_divs"] == [14, 21]
    nodes = meta["cell_types"]["nodes"]
    assert nodes["clusters"] == [0, 1]
    assert nodes["states"]["Mecp2"] == [[POS, POS], [NEG, POS]]
    assert nodes["calls"]["Mecp2"] == ["+", "~"]
    assert "cell_types" in json.loads((ct / "summary.json").read_text())
    rows = (ct / "cell_types.csv").read_text().splitlines()
    assert rows[0].startswith("chain,genotype,cluster,div")
    assert len(rows) == 1 + 2 * 2 * 2   # 2 cells x 2 days x 2 markers
    page = (ct / "viewer" / f"{key}.html").read_text()
    assert '"markers": ["Mecp2", "NeuN"]' in page

    # running again replaces rather than duplicates
    annotate_tracking_dir(ct, [labels], suite2p_roots=[s2p])
    assert (ct / "cell_types.csv").read_text().splitlines() == rows


def test_catnap_loader_skips_comment_columns(tmp_path):
    from meanap.catnap.subnetwork import load_cell_type_table

    f = _write(tmp_path / "rec.csv", ["0,,,,1,11", "2,,,,,"])
    table = load_cell_type_table(f)
    assert "Comments on Mecp2" not in table.columns
    assert list(table["NeuN_Positive"].dropna()) == [0, 2]


def test_find_label_file_prefers_csv_and_accepts_nested(tmp_path):
    from meanap.catnap.tracking.celltypes import find_label_file

    (tmp_path / "flat").mkdir()
    (tmp_path / "flat" / "rec.xlsx").write_text("x")
    (tmp_path / "flat" / "rec.csv").write_text("x")
    assert find_label_file("rec", [tmp_path / "flat"]).suffix == ".csv"
    (tmp_path / "raw" / "rec2").mkdir(parents=True)
    (tmp_path / "raw" / "rec2" / "PutativeCellType_rec2.csv").write_text("x")
    assert find_label_file("rec2", [tmp_path / "flat", tmp_path / "raw"]).name \
        == "PutativeCellType_rec2.csv"
    assert find_label_file("nope", [tmp_path / "flat", "", None]) is None


def test_roi_id_png_round_trips_ids_and_weights():
    """The page recovers ROI position from red*256+green. Nearest-neighbour
    resizing must not blend two IDs into a third, and IDs above 255 must survive."""
    import base64
    import io

    from PIL import Image

    from meanap.catnap.tracking.viewer import roi_id_png

    frame = 40
    stat = [{"ypix": np.array([1, 1, 2]), "xpix": np.array([1, 2, 1]),
             "lam": np.array([1.0, 0.5, 0.25])} for _ in range(300)]
    stat[299] = {"ypix": np.array([30, 30]), "xpix": np.array([30, 31]),
                 "lam": np.array([2.0, 1.0])}
    png = roi_id_png(stat, frame, size=frame)
    im = np.asarray(Image.open(io.BytesIO(base64.b64decode(png))).convert("RGB")).astype(int)
    ids = im[..., 0] * 256 + im[..., 1]
    assert ids[30, 30] == 300 and ids[30, 31] == 300      # position 299, +1
    assert im[30, 30, 2] == 255 and im[30, 31, 2] == 127  # weight in blue
    assert ids[0, 0] == 0
    assert set(np.unique(ids)) <= {0, 1, 300}              # first ROI wins ties


def test_type_category_rule_in_js():
    """The all-markers colouring, run as the browser runs it."""
    import shutil
    import subprocess

    from meanap.catnap.celltype_colours import TYPE_CATEGORY_JS

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    cases = [
        ({"NeuN": 1, "PV": 1, "SST": -1}, "PV+"),
        ({"NeuN": 1, "PV": 1, "SST": 1}, "multiple"),
        ({"NeuN": 1, "PV": -1, "SST": 0}, "NeuN+ only"),
        ({"NeuN": -1, "PV": -1, "SST": -1}, "NeuN−"),
        ({"NeuN": 0, "PV": -1, "SST": 0}, "none positive"),
        ({"NeuN": 0, "PV": 0, "SST": 0}, "unlabelled"),
        # Mecp2 never decides the category
        ({"NeuN": 1, "PV": -1, "SST": -1, "Mecp2": 1}, "NeuN+ only"),
    ]
    script = TYPE_CATEGORY_JS + "\nconst cases = " + json.dumps(
        [list(c) for c in cases]) + """;
for (const [st] of cases)
  console.log(typeCategory(m => st[m] ?? 0, Object.keys(st)));
console.log(typeCategoryColour("VIP+", ["NeuN", "PV", "VIP"], "#999"));
for (const v of [1, -1, 0]) console.log(mecp2Style(m => v, ["NeuN", "Mecp2"]));
console.log(String(mecp2Style(m => 1, ["NeuN", "PV"])));
"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True,
                         check=True).stdout.splitlines()
    assert out[:len(cases)] == [want for _, want in cases]
    assert out[len(cases)] == "#E69F00"  # an unknown subtype takes the first extra colour
    # Mecp2 is the style, not the colour: filled, outline, faint; none if unstained
    assert out[len(cases) + 1:] == ["+", "-", "?", "null"]


def test_recommend_votes_weights_fallback_days_and_leaves_ties():
    from meanap.catnap.tracking.celltypes import recommend

    assert recommend([POS, POS, NEG])["call"] == "+"
    assert recommend([POS, POS, NEG])["reason"] == "majority"
    assert recommend([POS, UNKNOWN, POS])["reason"] == "unanimous"
    tie = recommend([POS, NEG])
    assert tie["call"] is None and tie["reason"] == "tie"
    # a fallback-matched day counts half, so it no longer ties
    assert recommend([POS, NEG], weights=[1.0, 0.5])["call"] == "+"
    assert recommend([UNKNOWN])["reason"] == "unlabelled"


def test_recommend_genotype_fixes_mecp2_in_wt_and_ko_only():
    from meanap.catnap.tracking.celltypes import recommend

    assert recommend([NEG, NEG, POS], genotype="WT", marker="Mecp2")["call"] == "+"
    assert recommend([POS, POS], genotype="KO", marker="Mecp2")["call"] == "-"
    assert recommend([POS, NEG], genotype="Het", marker="Mecp2")["reason"] == "tie"
    assert recommend([NEG, NEG], genotype="WT", marker="PV")["call"] == "-"


def test_overrides_round_trip_and_final_csv(tmp_path):
    import csv as _csv

    from meanap.catnap.tracking.celltypes import (
        CELL_FIELDS, final_call, load_overrides, set_override, write_final_csv)

    path = tmp_path / "ov.json"
    assert load_overrides(path) == {}
    set_override(path, "chainA", 7, "PV", "+")
    set_override(path, "chainA", 7, "SST", "?")
    assert load_overrides(path) == {"chainA": {"7": {"PV": "+", "SST": "?"}}}
    set_override(path, "chainA", 7, "SST", None)
    assert load_overrides(path) == {"chainA": {"7": {"PV": "+"}}}
    with pytest.raises(ValueError):
        set_override(path, "chainA", 7, "PV", "maybe")

    assert final_call("-", "+") == "+"
    assert final_call("-", "?") is None
    assert final_call(None, None) is None

    cells = tmp_path / "cells.csv"
    with open(cells, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=CELL_FIELDS)
        w.writeheader()
        base = {"chain": "chainA", "genotype": "Het", "days": "", "raw_call": "~",
                "confidence": "", "reason": "tie"}
        w.writerow({**base, "cluster": 7, "marker": "PV", "recommendation": ""})
        w.writerow({**base, "cluster": 8, "marker": "PV", "recommendation": "-"})
    out = tmp_path / "final.csv"
    write_final_csv(cells, load_overrides(path), out)
    rows = list(_csv.DictReader(open(out)))
    assert [(r["final"], r["source"]) for r in rows] == [("+", "manual"),
                                                        ("-", "recommendation")]


def test_viewer_saves_overrides_through_post(tmp_path):
    """The POST route writes, validates, and refuses non-JSON bodies."""
    import urllib.error
    import urllib.request

    from meanap.viewer.server import ViewerService

    ct = tmp_path / "CellTracking"
    (ct / "chains").mkdir(parents=True)
    (ct / "payload").mkdir()
    (ct / "chains" / "chainA.json").write_text(json.dumps(
        {"cell_types": {"markers": ["Mecp2", "PV"]}}))
    svc = ViewerService.__new__(ViewerService)       # no bundle context needed
    svc._bundle, svc.source = None, tmp_path
    out = svc.set_tracking_override(
        {"chain": "chainA", "cluster": 3, "marker": "PV", "value": "-"})
    assert out["overrides"] == {"3": {"PV": "-"}}
    assert (ct / "cell_type_overrides.json").is_file()
    for bad in ({"chain": "nope", "cluster": 3, "marker": "PV", "value": "-"},
                {"chain": "chainA", "cluster": 3, "marker": "GAD", "value": "-"},
                {"chain": "chainA", "cluster": "x", "marker": "PV", "value": "-"},
                {"chain": "chainA", "cluster": 3, "marker": "PV", "value": "yes"},
                {"chain": "../../outside", "cluster": 3, "marker": "PV", "value": "-"}):
        with pytest.raises(ValueError):
            svc.set_tracking_override(bad)
