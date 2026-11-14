"""Spike method for analysis: offered as step 1 names it, checked before use.

    QT_QPA_PLATFORM=offscreen uv run python test_spike_method_choice.py

The list used to be fixed — ``thr5p0``, ``mergedAll``, ``mergedWavelet`` that
step 1 never saves, and not ``thr4``/``thr5`` that it saves by default — and a
method missing from the spike files gave every electrode zero spikes without
a word. Now the list is what the wavelets and thresholds will detect, and a
step that reads a method the spike file does not have stops and says so.
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


def panel_checks() -> None:
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.panels.spike_detection import SpikeDetectionPanel
    from meanap.params import Params

    global _app
    _app = QApplication.instance() or QApplication([])
    print("The list")
    panel = SpikeDetectionPanel()

    def items():
        return [panel.spikes_method.itemData(i) for i in range(panel.spikes_method.count())]

    panel.load(Params())
    check("the defaults offer what step 1 will save: bior1p5, thr4, thr5",
          items() == ["bior1p5", "thr4", "thr5"], str(items()))
    panel.thresholds.setText("4, 4.5")
    panel.wname_list.item([panel.wname_list.item(i).text()
                           for i in range(panel.wname_list.count())].index("db2")).setSelected(True)
    check("it follows the wavelets and thresholds as they change",
          items() == ["bior1p5", "db2", "thr4", "thr4p5"], str(items()))
    panel.spikes_method.setCurrentIndex(panel.spikes_method.findData("thr4p5"))
    panel.thresholds.setText("4")
    text = panel.spikes_method.currentText()
    check("a chosen method these settings no longer detect stays chosen, marked",
          panel.spikes_method.currentData() == "thr4p5"
          and SpikeDetectionPanel.NOT_DETECTED in text, text)
    saved = Params()
    panel.save(saved)
    check("and is saved by its name, not its label", saved.spikes_method == "thr4p5",
          saved.spikes_method)
    panel.load(Params(spikes_method="thr5p0"))
    check("a saved thr5p0 (the old list's name) is read as thr5",
          panel.spikes_method.currentData() == "thr5", str(panel.spikes_method.currentData()))
    panel.load(Params(spikes_method="mergedAll"))
    check("a saved method step 1 cannot make is kept and marked, not swapped for another",
          panel.spikes_method.currentData() == "mergedAll"
          and SpikeDetectionPanel.NOT_DETECTED in panel.spikes_method.currentText(), "")


def pipeline_checks() -> None:
    from meanap.params import Params
    from meanap.pipeline.io import MissingSpikeMethod, require_spike_method
    from meanap.pipeline.runner import run_pipeline

    print("The pipeline")
    trains = {0: {"bior1p5": np.array([0.1]), "thr4": np.array([])}, 1: {"thr4": np.array([])}}
    require_spike_method(trains, "thr4", "rec")
    try:
        require_spike_method(trains, "thr5", "rec")
        check("a method not in the file is refused", False)
    except MissingSpikeMethod as err:
        check("a method not in the file is refused, naming what is there",
              "thr5" in str(err) and "bior1p5, thr4" in str(err), str(err))
    require_spike_method({}, "thr5", "rec")
    check("a file with no electrodes has nothing to refuse", True)

    rng = np.random.default_rng(0)
    fs = 12500.0
    dat = rng.standard_normal((int(4 * fs), 60)) * 5
    for k in range(500, dat.shape[0] - 500, 1000):
        dat[k:k + 6] -= 60
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "raw").mkdir()
        sio.savemat(tmp / "raw" / "recA.mat", {"dat": dat, "channels": np.arange(60) + 11,
                                               "fs": fs})
        pd.DataFrame([{"Recording Filename": "recA", "DIV group": 14, "Genotype": "WT"}]) \
            .to_csv(tmp / "recs.csv", index=False)

        def params(**kw) -> Params:
            p = Params(output_data_folder=str(tmp), output_data_folder_name="Run",
                       spreadsheet_file_name=str(tmp / "recs.csv"), spreadsheet_range="2:100",
                       raw_data=str(tmp / "raw"), channel_layout="MCS60", recording_workers=1,
                       random_seed=1, wname_list=["bior1.5"], thresholds=[4.0])
            for k, v in kw.items():
                setattr(p, k, v)
            return p

        run_pipeline(params(start_analysis_step=1, stop_analysis_step=2, spikes_method="thr4"),
                     log=lambda m: None)
        check("a run with a detected method goes through step 2", True)
        try:
            run_pipeline(params(start_analysis_step=2, stop_analysis_step=2,
                                spikes_method="thr5", continue_interrupted=False),
                         log=lambda m: None)
            check("step 2 on a method step 1 did not detect stops", False)
        except MissingSpikeMethod as err:
            check("step 2 on a method step 1 did not detect stops and says why",
                  "thr5" in str(err) and "recA" in str(err), str(err))


def main() -> int:
    panel_checks()
    pipeline_checks()
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
