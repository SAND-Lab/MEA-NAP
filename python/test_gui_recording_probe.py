"""Test reading the electrode layout and sampling rate from the recordings.

Run from the repo root::

    uv run python python/test_gui_recording_probe.py [screenshot-dir]

  A. probing: rate and channels read from each format's header, on files
     written here (v7.3 and v7 ``.mat``, an MCS ``.h5``), and the corner check
     that tells a 64-channel Axion well from a padded MCS array;
  B. the decision, including the cases no file here can produce (Axion
     ``.raw``, disagreeing recordings, an unknown channel count);
  C. the simple view: the step fills itself in and folds, flags mixed rates
     only in passing, flags an indirect guess, respects a layout the person
     picks, and asks when there is nothing to read.

GUI settings go to a temporary folder, so this never touches the person's own.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import h5py  # noqa: E402
import numpy as np  # noqa: E402
import scipy.io as sio  # noqa: E402
from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="meanap-settings-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)

from meanap.gui.simple_checks import check_recording_settings, describe_rates  # noqa: E402
from meanap.pipeline.recording_probe import (  # noqa: E402
    CORNER_CHANNELS, RecordingProbe, detect_layout, probe_folder, probe_recording,
)

FAILURES: list[str] = []
ERRORS: list[str] = []


def _excepthook(kind, value, tb) -> None:
    ERRORS.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)


sys.excepthook = _excepthook


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def pump(ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


GRID = np.array([10 * c + r for c in range(1, 9) for r in range(1, 9)])  # 11..88
MCS60 = np.array([c for c in GRID if c not in CORNER_CHANNELS])


def write_mat73(path: Path, channels, fs: float, live_corners: bool = True) -> Path:
    """A v7.3-style .mat: HDF5 holding dat (n_channels, n_samples), channels, fs."""
    rng = np.random.default_rng(0)
    dat = rng.normal(0, 2.5e-6, (len(channels), int(fs))).astype(np.float32)
    if not live_corners:
        dat[np.isin(channels, CORNER_CHANNELS)] = 0
    with h5py.File(path, "w") as f:
        f["dat"] = dat
        f["channels"] = np.asarray(channels, dtype=float)[None, :]
        f["fs"] = np.array([[fs]])
    return path


def write_mat7(path: Path, channels, fs: float) -> Path:
    dat = np.zeros((100, len(channels)))
    sio.savemat(path, {"dat": dat, "channels": np.asarray(channels, float)[:, None],
                       "fs": np.array([[fs]])})
    return path


def write_mcs_h5(path: Path, channels, fs: float) -> Path:
    """The parts of an MCS DataManager file the probe reads."""
    info = np.zeros(len(channels), dtype=[("Label", "S16"), ("Tick", "<i8"),
                                          ("ConversionFactor", "<i8"), ("ADZero", "<i4"),
                                          ("Exponent", "<i4")])
    info["Label"] = [f"E-00155 {c}".encode() for c in channels]
    info["Tick"] = int(round(1e6 / fs))
    with h5py.File(path, "w") as f:
        stream = f.create_group("Data/Recording_0/AnalogStream/Stream_0")
        stream["InfoChannel"] = info
        stream["ChannelData"] = np.zeros((len(channels), 100), dtype=np.int32)
    return path


# ── A. Probing ───────────────────────────────────────────────────────────────

def probe_section(tmp: Path) -> dict[str, Path]:
    print("A. Reading rate and channels from the files")
    folders = {name: tmp / name for name in
               ("axion", "padded", "mcs", "mixed", "v7_64", "empty", "unknown")}
    for folder in folders.values():
        folder.mkdir()
    write_mat73(folders["axion"] / "well_DIV14_A1.mat", GRID, 12500)
    write_mat73(folders["axion"] / "well_DIV14_A2.mat", GRID, 12500)
    write_mat73(folders["padded"] / "mcs_DIV7.mat", GRID, 25000, live_corners=False)
    write_mcs_h5(folders["mcs"] / "chip_div6.h5", MCS60, 25000)
    write_mcs_h5(folders["mixed"] / "chip_div6.h5", MCS60, 10000)
    write_mat7(folders["mixed"] / "chip_div7.mat", MCS60, 25000)
    write_mat7(folders["v7_64"] / "plate_DIV21_B3.mat", GRID, 12500)
    (folders["empty"] / "placeholder.mat").write_bytes(b"")
    write_mat7(folders["unknown"] / "odd.mat", np.arange(1, 33), 20000)

    p = probe_recording(folders["axion"] / "well_DIV14_A1.mat")
    check("v7.3 .mat: rate, channels, and live corners",
          (p.format, p.fs, p.n_channels, p.corners_live) == ("mat", 12500, 64, True), str(p))
    p = probe_recording(folders["padded"] / "mcs_DIV7.mat")
    check("padded MCS .mat: corners read as empty", p.corners_live is False, str(p))
    p = probe_recording(folders["mcs"] / "chip_div6.h5")
    check("MCS .h5: rate from the sample interval, channels from the labels",
          (p.format, p.fs, p.n_channels) == ("mcs", 25000, 60), str(p))
    p = probe_recording(folders["v7_64"] / "plate_DIV21_B3.mat")
    check("v7 .mat: header only, corners not read",
          (p.fs, p.n_channels, p.corners_live) == (12500, 64, None), str(p))
    check("an unreadable file is skipped, not fatal", probe_folder(folders["empty"]) == [])
    probes = probe_folder(folders["axion"])
    check("only one file per folder has its corners read",
          [p.corners_live for p in probes] == [True, None], str(probes))
    return folders


# ── B. Deciding ──────────────────────────────────────────────────────────────

def decide_section(folders: dict[str, Path]) -> None:
    print("B. Deciding the layout")

    def guess(name):
        return detect_layout(probe_folder(folders[name]))

    g = guess("axion")
    check("live corners: Axion64, sure", (g.layout, g.sure) == ("Axion64", True), str(g))
    g = guess("padded")
    check("empty corners: MCS60, sure", (g.layout, g.sure) == ("MCS60", True), str(g))
    g = guess("mcs")
    check("an MCS file: MCS60, sure", (g.layout, g.sure) == ("MCS60", True), str(g))
    g = guess("mixed")
    check("MCS files at two rates: MCS60, sure, both rates kept",
          (g.layout, g.sure, sorted(g.rates)) == ("MCS60", True, [10000, 25000]), str(g))
    g = guess("v7_64")
    check("64 channels unread at 12.5 kHz: Axion64, flagged as a guess",
          (g.layout, g.sure) == ("Axion64", False) and "couldn't be checked" in g.reason, str(g))
    g = guess("unknown")
    check("a channel count no layout has: no layout", g.layout is None, str(g))
    check("nothing readable: no layout", guess("empty").layout is None)

    def probe(n, fmt="mat", fs=25000.0, corners=None):
        return RecordingProbe("x", fmt, fs, n, corners)

    check("Axion .raw: 16 or 64 electrodes per well",
          detect_layout([probe(16, "axion")]).layout == "Axion16"
          and detect_layout([probe(64, "axion")]).layout == "Axion64")
    check("59 channels: MCS59", detect_layout([probe(59)]).layout == "MCS59")
    g = detect_layout([probe(60), probe(60), probe(16)])
    check("disagreeing recordings: the majority, flagged",
          (g.layout, g.sure) == ("MCS60", False) and "don't agree" in g.reason, str(g))

    check("rates described in kHz",
          describe_rates([12500]) == "12.5 kHz" and describe_rates([25000, 10000, 25000])
          == "10–25 kHz", describe_rates([25000, 10000]))
    c = check_recording_settings(guess("mixed"), "MCS60")
    check("mixed rates are a note, not a warning",
          c.state == "ok" and "different sampling rates" in c.message
          and c.summary == "MCS60 · 10–25 kHz", repr(c))
    c = check_recording_settings(guess("axion"), "MCS60")
    check("a layout that disagrees with the files is flagged",
          c.state == "warn" and "look like Axion64" in c.message, repr(c))
    check("nothing to go on: ask", check_recording_settings(None, "MCS60") is None)


# ── C. The simple view ───────────────────────────────────────────────────────

def view_section(folders: dict[str, Path], shots: Path | None) -> None:
    print("C. Simple view")
    from meanap.gui.main_window import MainWindow

    w = MainWindow()
    w.resize(1100, 860)
    w.show()
    w._set_simple_view(True)
    sv = w._simple_view
    data = w._data_panel
    data.channel_layout.setCurrentText("MCS60")
    data.spreadsheet.set_value("")

    def step():
        return next(s for s in sv._steps if s.key == "recording")

    def answer(folder: Path) -> None:
        # Skip past the spreadsheet: this is about the step after it.
        data.raw_data.set_value(str(folder))
        sv._confirmed.discard("recording")
        names = sorted(p.stem for p in folder.iterdir())
        sheet = folder / "sheet.csv"
        sheet.write_text("Recording Filename,DIV group,Genotype\n"
                         + "".join(f"{n},14,WT\n" for n in names))
        data.spreadsheet.set_value(str(sheet))
        pump(1500)

    check("the simple view no longer asks for a sampling rate",
          not any(isinstance(wd, type(data.fs)) for wd in step().card.findChildren(type(data.fs))))

    answer(folders["axion"])
    card = step().card
    check("the layout is read from the files and the step folds by itself",
          card.state == "done" and card.badge.text() == "✓"
          and data.channel_layout.currentText() == "Axion64"
          and card.summary.text() == "Axion64 · 12.5 kHz",
          f"{card.state} {card.badge.text()} {data.channel_layout.currentText()} "
          f"{card.summary.text()!r}")
    check("and the rate goes into the settings, for the record", data.fs.value() == 12500)
    if shots:
        w.grab().save(str(shots / "recording_detected.png"))

    answer(folders["mixed"])
    card = step().card
    check("recordings at different rates: done with a tick, the range in the summary",
          card.state == "done" and card.badge.text() == "✓"
          and card.summary.text() == "MCS60 · 10–25 kHz", card.summary.text())

    answer(folders["v7_64"])
    card = step().card
    check("an indirect guess is used but flagged",
          card.state == "done" and card.badge.text() == "!"
          and data.channel_layout.currentText() == "Axion64", card.badge.text())

    data.channel_layout.setCurrentText("MCS60")
    pump(800)
    check("a layout the person picks stays, flagged as differing from the files",
          data.channel_layout.currentText() == "MCS60" and step().card.badge.text() == "!"
          and "look like Axion64" in step().card.status.text(), step().card.status.text())

    answer(folders["unknown"])
    check("nothing to read: the step asks, with Continue",
          step().card.state == "active", step().card.state)
    sv._confirm_current()
    pump(1300)
    check("and moves on once confirmed", step().card.state == "done")
    w.close()


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as tmp:
        folders = probe_section(Path(tmp))
        decide_section(folders)
        view_section(folders, shots)
    if ERRORS:
        FAILURES.append("uncaught exceptions: " + "; ".join(ERRORS[:3]))
    print(f"\n{'ALL PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
