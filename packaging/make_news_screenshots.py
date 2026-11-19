"""Screenshots of the simple view, for the News post and the README.

Run from the repo root::

    uv run python packaging/make_news_screenshots.py [out_dir]

Writes to ``docs/news/imgs/simple-view/`` by default:

* ``analyse.png``: Analyse recordings, every question answered (ExampleData);
* ``steps.gif``: the same questions being answered, one coming up after another;
* ``search.gif``: "spike detection" typed in the search box, and a result chosen;
* ``viewer.png``: the results viewer on a network plot (participation coefficient);
* ``viewer.gif``: selecting a hub to see its connections, then the Spring layout.

Drawn headlessly (``QT_QPA_PLATFORM=offscreen``) at 1.5x scale so text stays
sharp, from ExampleData and a simulated step-4 run built here, so no one's own
data ends up in the docs. The window is only as wide as the page's column, and
the empty background below the content is trimmed off.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1.5")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "python"))

from PyQt6.QtCore import QBuffer, QIODevice, QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_SETTINGS = tempfile.mkdtemp(prefix="meanap-shots-")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _SETTINGS)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS)

from meanap.gui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply(app)
QSettings("SAND Lab", "MEA-NAP").setValue("tutorial/seen", True)

#: Simulated recordings: two genotypes at two ages.
RECS = [f"Culture{i}_DIV{div}_{g}" for i, (div, g) in enumerate(
    [(14, "WT"), (14, "KO"), (14, "WT"), (21, "KO"), (21, "WT"), (21, "KO")])]
#: The page's column is 560 px wide: a little either side, no more.
PAGE = (660, 1000)
VIEWER = (1180, 820)
VIEWER_GIF = (1560, 860)
#: Frame interval for the GIF, and how long it rests on the finished page.
FRAME_MS = 70
END_HOLD_MS = 2500


def _image(widget):
    """*widget* as a Pillow image."""
    from PIL import Image

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    widget.grab().save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")


def pump(ms: int, frames: list | None = None, widget=None) -> None:
    """Let Qt run for *ms*, grabbing a frame of *widget* every FRAME_MS if asked."""
    end = time.monotonic() + ms / 1000
    next_frame = 0.0
    while time.monotonic() < end:
        app.processEvents()
        if frames is not None and time.monotonic() >= next_frame:
            frames.append(_image(widget))
            next_frame = time.monotonic() + FRAME_MS / 1000
        time.sleep(0.005)


def content_height(image, margin: int = 24) -> int:
    """Where the plain background below the content starts, plus *margin*."""
    from PIL import Image, ImageChops

    background = image.getpixel((image.width // 2, image.height - 2))
    box = ImageChops.difference(image, Image.new("RGB", image.size, background)).getbbox()
    return image.height if box is None else min(image.height, box[3] + margin)


def simulated_run(tmp: Path, name: str) -> Path:
    """A finished step-4 run over RECS on an MCS 60-electrode array.

    Seeded spike times and sparse connectivity that falls off with distance,
    so a network plot of it looks like a culture's rather than a hairball.
    """
    import numpy as np
    import pandas as pd

    from meanap.pipeline.atomic import atomic_savez
    from meanap.pipeline.channel_layout import get_coords_from_layout
    from meanap.pipeline.io import save_spike_times_npz
    from meanap.pipeline.output_folders import create_output_folders
    from meanap.pipeline.runner import run_pipeline
    from test_continue_interrupted import _step4_params

    lag = 25
    channels, coords = get_coords_from_layout("MCS60")
    n_ch = len(channels)
    dist = np.linalg.norm(coords[:, None] - coords[None], axis=-1)
    sheet = tmp / "cultures.csv"
    pd.DataFrame([{"Recording Filename": r, "DIV group": int(r.split("DIV")[1][:2]),
                   "Genotype": r.rsplit("_", 1)[1]} for r in RECS]).to_csv(sheet, index=False)
    root = create_output_folders(tmp, name, ["KO", "WT"])
    for i, rec in enumerate(RECS):
        rng = np.random.default_rng(i)
        rates = rng.lognormal(0.5, 0.8, n_ch)
        save_spike_times_npz(
            root / "1_SpikeDetection" / "1A_SpikeDetectedData" / f"{rec}_spikes.npz",
            {ch: {"bior1p5": np.sort(rng.uniform(0, 60, int(40 * r) + 5))}
             for ch, r in zip(range(n_ch), rates)},
            channels, 2000.0, duration_s=60.0)
        hubs = rng.uniform(0.3, 1.0, n_ch)
        p_edge = 0.9 * np.exp(-dist / 1.6) * np.sqrt(np.outer(hubs, hubs))
        adj = np.where(rng.uniform(0, 1, (n_ch, n_ch)) < p_edge,
                       rng.uniform(0.1, 0.7, (n_ch, n_ch)), 0.0)
        adj = np.triu(adj, 1)
        adj = adj + adj.T
        atomic_savez(root / "ExperimentMatFiles" / f"{rec}_adjM.npz", channels=channels,
                     **{f"adjM{lag}mslag": adj, f"adjM{lag}mslag_raw": adj})
    params = _step4_params(tmp, name, spreadsheet_file_name=str(sheet),
                           raw_data=str(tmp / "recordings"), channel_layout="MCS60")
    return run_pipeline(params, log=lambda m: None)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs/news/imgs/simple-view"
    out.mkdir(parents=True, exist_ok=True)
    from meanap.gui.main_window import MainWindow

    # The paths typed on screen: short, and nobody's home folder.
    demo = Path(tempfile.gettempdir()) / "MEA-NAP-demo"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "recordings").mkdir()
        shutil.rmtree(demo, ignore_errors=True)
        demo.mkdir()
        (demo / "ExampleData").symlink_to(REPO / "ExampleData")
        results = demo / "Results"
        results.mkdir()

        w = MainWindow()
        w.resize(*PAGE)
        w.show()
        sv = w._simple_view
        data = w._data_panel
        data.spreadsheet_range.setText("A2:A3")   # its two rows, as Test pipeline
        sv._steps[3].card.body.edit.setText("")   # so the last question waits too
        pump(400)

        def type_into(edit, text: str) -> None:
            edit.setFocus()
            for i in range(1, len(text) + 1):
                edit.setText(text[:i])
                edit.textEdited.emit(edit.text())
                pump(22, frames, w)

        # The questions, answered one after another, as a person would.
        frames: list = []
        pump(1200, frames, w)
        type_into(sv._steps[0].card.body.edit, str(demo / "ExampleData"))
        pump(1800, frames, w)
        type_into(sv._steps[1].card.body.edit, str(demo / "ExampleData" / "exampleData.csv"))
        pump(1800, frames, w)
        sv._confirm_current()                     # Recording settings: read from the files
        pump(1500, frames, w)
        type_into(sv._steps[3].card.body.edit, str(results))
        pump(1000, frames, w)
        pump(END_HOLD_MS, frames, w)
        height = max(content_height(f) for f in frames)
        frames = [f.crop((0, 0, f.width, height)) for f in frames]
        frames[0].save(out / "steps.gif", save_all=True, append_images=frames[1:],
                       duration=FRAME_MS, loop=0, optimize=True)
        print(f"  {out / 'steps.gif'} ({len(frames)} frames)")

        final = _image(w)
        final.crop((0, 0, final.width, content_height(final))).save(
            out / "analyse.png", optimize=True)
        print(f"  {out / 'analyse.png'}")

        # Search: typed a letter at a time, then the wavelet setting it turned up.
        frames = []
        box = sv.search_box
        pump(500, frames, w)
        box.setFocus()
        for ch in "spike detection":
            box.setText(box.text() + ch)
            box.textEdited.emit(box.text())
            pump(110, frames, w)
        pump(2200, frames, w)
        hit = next((i for i, e in enumerate(box.matches()) if "Wavelet" in e.title), None)
        if hit is not None:
            box._choose(hit)
        pump(3000, frames, w)
        frames[0].save(out / "search.gif", save_all=True, append_images=frames[1:],
                       duration=FRAME_MS, loop=0, optimize=True)
        print(f"  {out / 'search.gif'} ({len(frames)} frames)")

        # The results viewer on a network plot.
        run = simulated_run(tmp, "OutputData19Nov2026")
        sv.show_page("results")
        sv.results_page.set_source(run, open_viewer=False)
        pump(600)
        sv.results_page.open_viewer("results")     # the native viewer, not the browser
        pump(4000)
        viewers = [tw for tw in app.topLevelWidgets()
                   if tw is not w and tw.isVisible() and tw.width() > 400]
        if not viewers:
            print("  (no viewer window opened)")
            return 1
        from meanap.gui.results_viewer import ResultsViewer

        window = viewers[-1]
        window.resize(*VIEWER)
        pump(800)
        viewer = window if isinstance(window, ResultsViewer) else window.findChild(ResultsViewer)
        labels = viewer.figure_labels() if viewer is not None else []
        label = os.environ.get("NEWS_FIGURE") or next(
            (l for l in labels if l.endswith("Spatial network / Participation coefficient")), "")
        if not label or not viewer.select_figure(label):
            print("  (no network figure to show); figures:\n    " + "\n    ".join(labels))
            return 1
        print(f"  showing: {label}")
        pump(3000)
        _image(window).save(out / "viewer.png", optimize=True)
        print(f"  {out / 'viewer.png'}")

        # The viewer GIF: pick out a hub's connections, then lay the network
        # out by its connections rather than by electrode, the hub still picked.
        from meanap.gui.network_canvas import NetworkCanvas

        canvas = next(c for c in window.findChildren(NetworkCanvas) if c.isVisible())
        network = canvas.painter.network
        hub = max(range(len(network.names) if hasattr(network, "names") else len(canvas.scene.xy)),
                  key=lambda n: len(network.neighbours(n)))
        # Styling open from the start, in a window wide enough for it: the
        # window grows when it opens, and a GIF's frames must be one size.
        viewer.style_button.setChecked(True)
        pump(800)
        window.resize(*VIEWER_GIF)
        pump(2500)
        frames = []
        pump(1500, frames, window)
        canvas.click(hub)
        pump(2800, frames, window)
        viewer.style_panel._widgets["layout"].setCurrentText("Spring (force)")
        pump(4000, frames, window)
        canvas.click(None)
        pump(2500, frames, window)
        size = frames[0].size
        frames = [f.resize((round(size[0] * 0.6), round(size[1] * 0.6))) for f in frames]
        frames[0].save(out / "viewer.gif", save_all=True, append_images=frames[1:],
                       duration=FRAME_MS, loop=0, optimize=True)
        print(f"  {out / 'viewer.gif'} ({len(frames)} frames)")
        for tw in app.topLevelWidgets():
            tw.close()
    shutil.rmtree(demo, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
