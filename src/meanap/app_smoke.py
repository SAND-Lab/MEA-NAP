"""A self-check for the packaged app: ``<app> --smoke-test``.

A frozen build fails in ways a source checkout never shows — a module
PyInstaller didn't see imported, a data file left behind, worker processes that
re-launch the GUI instead of working. Each check here exercises one of those on
the built app, with no network and no data beyond what it makes itself:

* every pipeline and optional extra imports (OASIS, the sorters);
* numba compiles and runs the step-4 kernel;
* two synthetic MEA recordings run through steps 1-4 with worker
  *processes*, which is what proves ``spawn`` + ``freeze_support`` work;
* the GUI builds a window offscreen.

Prints one PASS/FAIL line per check; exits non-zero if any failed. Also runs
from a clone (``python -m meanap.app_smoke``), which is how it is tested.
"""

from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Callable

import numpy as np

FS = 12500.0
SECONDS = 20.0


def _write_recording(path: Path, seed: int) -> None:
    """60 MCS electrodes; network bursts shared by most channels, plus noise spikes."""
    import scipy.io as sio

    from meanap.pipeline.channel_layout import get_coords_from_layout

    channels, _ = get_coords_from_layout("MCS60")
    rng = np.random.default_rng(seed)
    n = int(FS * SECONDS)
    dat = rng.normal(0, 1.0, size=(n, len(channels))).astype(np.float32)
    spike = (-10.0 * np.exp(-((np.arange(-15, 16)) ** 2) / 12.0)).astype(np.float32)
    bursts = np.sort(rng.uniform(0.5, SECONDS - 1.0, size=int(SECONDS / 2)))
    for ch in range(len(channels)):
        times = list(rng.uniform(0.1, SECONDS - 0.1, size=int(SECONDS * 2)))
        for b in bursts:
            if rng.random() < 0.8:
                times += list(b + np.cumsum(rng.exponential(0.008, size=5)))
        for t in times:
            at = int(t * FS)
            if 15 <= at < n - 16:
                dat[at - 15:at + 16, ch] += spike
    sio.savemat(path, {"dat": dat, "channels": np.asarray(channels, float), "fs": FS})


def check_imports() -> str:
    import importlib

    for name in ("meanap.pipeline.runner", "meanap.catnap.pipeline", "meanap.stim.activity",
                 "meanap.stats.dataset", "meanap.viewer.server", "meanap.cli",
                 "statsmodels.formula.api", "sklearn.decomposition", "openpyxl", "h5py"):
        importlib.import_module(name)
    from meanap.catnap.denoising import oasis_available
    if not oasis_available():
        raise RuntimeError("OASIS is not available")
    from meanap.pipeline.spike_sorting import installed_sorters
    sorters = installed_sorters()
    if "mountainsort5" not in sorters:
        raise RuntimeError(f"MountainSort5 missing; sorters: {sorters}")
    return f"sorters: {', '.join(sorters)}"


def check_numba() -> str:
    import numba

    from meanap.pipeline import null_models

    if not getattr(null_models, "_HAVE_NUMBA", True):
        raise RuntimeError("null_models fell back to pure Python")
    adj = np.random.default_rng(0).random((20, 20))
    adj = np.triu(adj, 1) + np.triu(adj, 1).T
    null_models.randmio_und_signed(adj, 2, rng=np.random.default_rng(1))
    return f"numba {numba.__version__}"


def check_pipeline() -> str:
    import pandas as pd

    from meanap.params import Params
    from meanap.pipeline.runner import run_pipeline

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "raw"
        raw.mkdir()
        names = ["smokeA_DIV14", "smokeB_DIV14"]
        for i, name in enumerate(names):
            _write_recording(raw / f"{name}.mat", seed=i)
        pd.DataFrame([{"Recording filename": n, "DIV": 14, "Group": g}
                      for n, g in zip(names, ["WT", "KO"])]).to_csv(tmp / "recs.csv", index=False)
        params = Params(
            raw_data=str(raw), output_data_folder=str(tmp), output_data_folder_name="Smoke",
            spreadsheet_file_name=str(tmp / "recs.csv"), spreadsheet_range="2:100",
            start_analysis_step=1, stop_analysis_step=4, channel_layout="MCS60",
            func_con_lag_val=[10], prob_thresh_rep_num=20, random_seed=3,
            min_number_of_nodes_to_cal_net_met=2,
            # Worker *processes*, not threads: the frozen spawn path is the point.
            spike_detection_channel_workers=2, recording_workers=2,
        )
        lines: list[str] = []
        root = run_pipeline(params, log=lines.append)
        degraded = [ln for ln in lines if "could not start worker processes" in ln]
        if degraded:
            raise RuntimeError(f"worker processes did not start: {degraded[0]}")
        need = [root / "2_NeuronalActivity" / "NeuronalActivity_RecordingLevel.csv",
                root / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv"]
        missing = [str(p.relative_to(root)) for p in need if not p.exists()]
        if missing:
            raise RuntimeError(f"missing outputs: {missing}")
        pngs = len(list(root.rglob("*.png")))
        if not pngs:
            raise RuntimeError("no figures were drawn")
        return f"{pngs} figures"


def check_gui() -> str:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from meanap.gui import theme
    from meanap.gui.main_window import MainWindow

    theme.enable_hi_dpi()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    theme.apply(app)
    window = MainWindow()
    window.show()
    app.processEvents()
    size = window.grab().size()
    window.close()
    return f"window {size.width()}x{size.height()}"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("imports and optional extras", check_imports),
    ("numba JIT", check_numba),
    ("steps 1-4 on synthetic recordings, with worker processes", check_pipeline),
    ("GUI window (offscreen)", check_gui),
]


#: What the main window pulls in, heaviest first — timed one by one by
#: :func:`time_startup`, so a slow start on someone's PC can be pinned on a
#: library rather than guessed at.
STARTUP_IMPORTS = ("numpy", "scipy.signal", "scipy.stats", "matplotlib.pyplot",
                   "pandas", "numba", "sklearn.decomposition", "h5py",
                   "seaborn", "spikeinterface.sorters", "meanap.pipeline.runner",
                   "meanap.gui.main_window")


def time_startup() -> int:
    """``<app> --time-startup``: how long the GUI takes to come up, and why.

    Run it twice: the first run after an install (or a reboot) is the one that
    pays for disk reads and the antivirus scan of every library, the second
    shows what is left once those are cached.
    """
    import importlib
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    started = time.perf_counter()
    lap = started

    def report(what: str) -> None:
        nonlocal lap
        now = time.perf_counter()
        print(f"  {now - lap:6.2f} s  {what}", flush=True)
        lap = now

    print("startup timing:", flush=True)
    from PyQt6.QtWidgets import QApplication

    from meanap.gui import theme
    app = QApplication.instance() or QApplication(sys.argv[:1])
    theme.apply(app)
    report("Qt (the splash screen appears after this)")
    for name in STARTUP_IMPORTS:
        importlib.import_module(name)
        report(f"import {name}")
    from meanap.gui.main_window import MainWindow
    window = MainWindow()
    window.show()
    app.processEvents()
    report("build and show the main window")
    print(f"  {time.perf_counter() - started:6.2f} s  total", flush=True)
    window.close()
    return 0


def main() -> int:
    from meanap.version import all_versions, build_label

    print(f"MEA-NAP smoke test — {all_versions()} {build_label() or ''}".rstrip(), flush=True)
    failed = 0
    for name, fn in CHECKS:
        start = time.monotonic()
        try:
            detail = fn()
            print(f"  PASS  {name}  ({detail}; {time.monotonic() - start:.0f}s)", flush=True)
        except Exception:  # noqa: BLE001 - report every failure, then carry on
            failed += 1
            print(f"  FAIL  {name}\n{traceback.format_exc()}", flush=True)
    print("smoke test " + ("passed" if not failed else f"FAILED ({failed})"), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
