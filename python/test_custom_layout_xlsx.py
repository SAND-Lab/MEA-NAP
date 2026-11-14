"""Excel recording sheets, and Custom channel layouts from a file.

    QT_QPA_PLATFORM=offscreen uv run python test_custom_layout_xlsx.py

The pipeline read only CSV sheets (an .xlsx one stopped it); and the Custom
layout was offered on the Data tab but rejected by every step. Here an .xlsx
sheet and a hexagonal 19-electrode layout go through steps 1–4, the Data tab
reads and draws the layout file, and the simple view will not move on
without a readable one.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.io as sio

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

fails: list[str] = []
_app = None


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok or not detail else f"  — {detail}"))
    if not ok:
        fails.append(name)


def hexagon(pitch: float = 100.0) -> list[tuple[int, float, float]]:
    """19 electrodes, numbered row by row from the top."""
    rows, ch = [], 1
    for r, n in enumerate([3, 4, 5, 4, 3]):
        for k in range(n):
            rows.append((ch, (k - (n - 1) / 2) * pitch, r * pitch * np.sqrt(3) / 2))
            ch += 1
    return rows


def sheet_checks(tmp: Path) -> None:
    from meanap.pipeline.spreadsheet import read_recording_csv

    print("Recording sheets")
    table = pd.DataFrame({"Recording Filename": ["001", "rec_B", None, " rec_C "],
                          "DIV group": [14, 21, None, "7"], "Genotype": ["WT", "KO", None, "WT"],
                          "Ground": [None, "15, 82", None, 15]})
    table.to_excel(tmp / "s.xlsx", index=False)
    table.to_csv(tmp / "s.csv", index=False)
    xlsx = read_recording_csv(tmp / "s.xlsx", "A2:A100")
    csv = read_recording_csv(tmp / "s.csv", "A2:A100")
    check("an .xlsx sheet reads as its CSV twin does", xlsx == csv and len(xlsx) == 3,
          f"{xlsx} vs {csv}")
    check("names stay as written (001 is not 1), trimmed",
          [r.filename for r in xlsx] == ["001", "rec_B", "rec_C"], str([r.filename for r in xlsx]))
    check("a blank row is skipped", len(xlsx) == 3)
    (tmp / "s.xls").write_bytes(b"old")
    try:
        read_recording_csv(tmp / "s.xls", "2:10")
        check("an old .xls says to save it as .xlsx", False)
    except ValueError as err:
        check("an old .xls says to save it as .xlsx", ".xlsx" in str(err), str(err))
    bad = table.copy()
    bad.loc[1, "DIV group"] = "twenty"
    bad.to_excel(tmp / "bad.xlsx", index=False)
    try:
        read_recording_csv(tmp / "bad.xlsx", "2:10")
        check("a DIV that is not a number names its row", False)
    except ValueError as err:
        check("a DIV that is not a number names its row", "row 3" in str(err), str(err))


def layout_checks(tmp: Path) -> None:
    from meanap.params import Params
    from meanap.pipeline import channel_layout as cl
    from meanap.pipeline.probes import electrode_pitch_um

    print("Layout files")
    pd.DataFrame(hexagon(), columns=["Channel", "X", "Y"]).to_csv(tmp / "hex.csv", index=False)
    rows = cl.read_layout_file(tmp / "hex.csv")
    check("a layout file reads by its column names", len(rows) == 19 and rows[0][0] == 1)
    params = Params(channel_layout="Custom", custom_layout=rows)
    name = cl.layout_of(params)
    channels, xy = cl.get_coords_from_layout(name)
    top = xy[channels == 1][0][1]
    check("row 1 of the file is at the top of the drawing", top == xy[:, 1].max(), str(xy[:3]))
    check("drawn on the [0, 8] scale every layout uses",
          np.isclose(xy.min(), 0) and np.isclose(xy.max(), 8), f"{xy.min()} {xy.max()}")
    check("its pitch is read from the file (µm)", np.isclose(electrode_pitch_um(name), 100.0),
          str(electrode_pitch_um(name)))
    check("and it caps a network's size like a fixed layout", cl.fixed_electrode_count(params) == 19)
    for text, why in (("channel,x,y\n1,0,0\n1,100,0\n", "more than once"),
                      ("channel,x,y\n1,0,0\n2,0,0\n", "same place"),
                      ("channel,x,y\n1,0,0\n2,a,0\n", "row 3")):
        (tmp / "bad.csv").write_text(text)
        try:
            cl.read_layout_file(tmp / "bad.csv")
            check(f"a bad file is refused ({why})", False)
        except ValueError as err:
            check(f"a bad file is refused, saying why ({why})", why in str(err), str(err))
    try:
        cl.get_coords_from_layout("Custom")
        check("Custom with no table asks for the file", False)
    except ValueError as err:
        check("Custom with no table asks for the file", "layout file" in str(err), str(err))


def gui_checks(tmp: Path) -> None:
    global _app
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from meanap.gui.panels.data import CHANNEL_LAYOUTS, DataPanel
    from meanap.params import Params

    print("The Data tab")
    offered = set(CHANNEL_LAYOUTS)
    check("Axion16 and Custom are offered; Mea256, MCS59, MCS60old are not",
          {"Axion16", "Custom"} <= offered and not offered & {"Mea256", "MCS59", "MCS60old"},
          str(CHANNEL_LAYOUTS))
    panel = DataPanel()
    panel.channel_layout.setCurrentText("Custom")
    _app.processEvents()
    check("choosing Custom shows the layout file row", not panel.custom_layout_box.isHidden())
    check("with no file, it says what is missing", "layout file" in panel.custom_layout_problem(),
          panel.custom_layout_problem())
    panel.custom_layout_file.set_value(str(tmp / "hex.csv"))
    _app.processEvents()
    check("a good file is read, summarised and drawn",
          panel.custom_layout_problem() == "" and "19 electrodes" in panel.custom_layout_note.text()
          and len(panel.custom_layout_preview._channels) == 19, panel.custom_layout_note.text())
    saved = Params()
    panel.save(saved)
    check("the table is saved with the settings, not only the path",
          saved.channel_layout == "Custom" and len(saved.custom_layout) == 19
          and saved.custom_layout_file.endswith("hex.csv"))
    moved = Params(channel_layout="Custom", custom_layout=saved.custom_layout,
                   custom_layout_file=str(tmp / "elsewhere" / "hex.csv"))
    other = DataPanel()
    other.load(moved)
    _app.processEvents()
    check("settings from another computer keep their table when the file is not there",
          other.custom_layout_problem() == "" and "isn't here" in other.custom_layout_note.text(),
          other.custom_layout_note.text())
    panel.channel_layout.setCurrentText("MCS60")
    check("another layout hides it again", panel.custom_layout_box.isHidden())

    print("Viewers")
    from PyQt6.QtWidgets import QComboBox

    from meanap.gui.layout_preview import choose_layout_item
    combo = QComboBox()
    combo.addItems(["MCS60", "Axion64", "Axion16"])
    choose_layout_item(combo, saved)
    check("a viewer's layout list takes the run's custom layout, table and all",
          combo.currentText() == "Custom" and str(combo.currentData()).startswith("Custom:"))


def pipeline_checks(tmp: Path) -> None:
    from meanap.params import Params
    from meanap.pipeline.channel_layout import read_layout_file
    from meanap.pipeline.runner import run_pipeline

    print("A run")
    fs = 12500.0
    raw = tmp / "raw"
    raw.mkdir()
    rng = np.random.default_rng(0)
    # 19 hexagon electrodes and one, channel 99, that the layout leaves out.
    channels = np.array(list(range(1, 20)) + [99])
    names = ["hexA_DIV14", "hexB_DIV14"]
    for name in names:
        dat = rng.standard_normal((int(30 * fs), len(channels))) * 5
        for k in range(len(channels)):
            for s in rng.choice(dat.shape[0] - 20, 250, replace=False):
                dat[s:s + 6, k] -= 60
        sio.savemat(raw / f"{name}.mat", {"dat": dat, "channels": channels, "fs": fs})
    pd.DataFrame([{"Recording Filename": n, "DIV group": 14, "Genotype": "WT"} for n in names]) \
        .to_excel(tmp / "recs.xlsx", index=False)
    params = Params(output_data_folder=str(tmp), output_data_folder_name="Run",
                    spreadsheet_file_name=str(tmp / "recs.xlsx"), spreadsheet_range="2:100",
                    raw_data=str(raw), channel_layout="Custom",
                    custom_layout_file=str(tmp / "hex.csv"), start_analysis_step=1,
                    stop_analysis_step=4, func_con_lag_val=[10], prob_thresh_rep_num=20,
                    recording_workers=1, random_seed=1, thresholds=[4.0], spikes_method="thr4")
    logs: list[str] = []
    root = run_pipeline(params, log=lambda m: logs.append(str(m)))
    text = "\n".join(logs)
    check("an .xlsx sheet and a Custom layout (read from its file) run steps 1–4",
          (root / "4_NetworkActivity").is_dir() and "Custom (19 electrodes)" in text)
    check("a channel the layout leaves out is reported",
          "not in the custom layout" in text and "99" in text)
    heatmap = root / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis" / "WT" / names[0] \
        / "2_Heatmap.png"
    networks = list((root / "4_NetworkActivity").rglob("*NetworkPlot*.png"))
    check("its electrodes are drawn: heatmaps and network plots", heatmap.is_file()
          and len(networks) > 0, f"{heatmap.is_file()} {len(networks)}")
    params.custom_layout, params.custom_layout_file = [], ""
    try:
        run_pipeline(params, log=lambda m: None)
        check("Custom with no file stops before step 1", False)
    except ValueError as err:
        check("Custom with no file stops before step 1, saying so", "custom_layout_file" in str(err),
              str(err))
    assert read_layout_file(tmp / "hex.csv")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sheet_checks(tmp)
        layout_checks(tmp)
        gui_checks(tmp)
        pipeline_checks(tmp)
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
