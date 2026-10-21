# PyInstaller spec for the MEA-NAP desktop app. Build with packaging/build_app.py,
# which makes the icons and the build-info file this reads first.
#
# One-folder build (not one-file): a one-file app unpacks ~1 GB into a temp
# folder on every launch, which is slow and trips antivirus scanners.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
BUILD = Path(SPECPATH) / "build"
ICON = BUILD / ("icon.icns" if sys.platform == "darwin" else "icon.ico")

datas = [
    (str(ROOT / "src/meanap/gui/assets"), "meanap/gui/assets"),
    (str(ROOT / "src/meanap/pipeline/assets"), "meanap/pipeline/assets"),
    # Beside the package, where meanap.version looks when there is no repo.
    (str(ROOT / "version.txt"), "meanap"),
    (str(ROOT / "versions.json"), "meanap"),
    (str(BUILD / "_build_info.json"), "meanap"),
    # The step-4 summary figure's metric schematics (meanap.frozen.bundle_dir).
    (str(ROOT / "matlab/Images"), "matlab/Images"),
]
# Pure-data packages the hooks don't cover.
for pkg in ("sciplotlib", "probeinterface"):
    datas += collect_data_files(pkg)

hiddenimports = (
    # Much of MEA-NAP is imported lazily, inside functions, and some of it by
    # name (the GUI's panels, --run-module targets): take all of it.
    collect_submodules("meanap")
    # SpikeInterface registers sorters and extractors by import path.
    + collect_submodules("spikeinterface.sorters")
    + collect_submodules("spikeinterface.extractors")
    + collect_submodules("spikeinterface.postprocessing")
    + collect_submodules("spikeinterface.qualitymetrics")
    + ["mountainsort5", "hdbscan", "oasis", "oasis.functions", "certifi"]
)

excludes = [
    # Not used, and each would drag in hundreds of MB if something optional
    # imported it.
    "tkinter", "IPython", "jupyter", "notebook", "torch", "tensorflow",
    "PyQt5", "PySide2", "PySide6",
]

a = Analysis(
    [str(Path(SPECPATH) / "meanap_app.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MEA-NAP",
    icon=str(ICON),
    # No console window behind the GUI. Output goes to the log file instead
    # (meanap.frozen.prepare_runtime). --smoke-test still prints on macOS and
    # Linux; on Windows CI reads the log.
    console=False,
    # Keep UPX off: it saves little on these libraries and is a common reason
    # antivirus flags an unsigned app.
    upx=False,
    # macOS: the architecture of the Python building it — one build on an
    # Apple-silicon runner, one on an Intel runner (not a universal2 app:
    # numba, scipy etc. ship separate wheels per architecture).
    target_arch=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="MEA-NAP", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MEA-NAP.app",
        icon=str(ICON),
        bundle_identifier="org.sandlab.meanap",
        version=(ROOT / "version.txt").read_text().strip(),
        info_plist={
            "CFBundleDisplayName": "MEA-NAP",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
