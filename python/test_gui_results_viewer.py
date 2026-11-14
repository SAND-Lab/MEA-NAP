"""Test the in-app results viewer (prototype: per-recording figures).

Run from the repo root::

    uv run python python/test_gui_results_viewer.py

The viewer hosts the pipeline's matplotlib figures live rather than showing
pictures of them, so the things worth pinning are: that the live figure *is*
the figure the pipeline saves (same pixels), that a node says which channel it
is, and that the window draws, restyles and tears down.

Runs offscreen against the synthetic run shared with ``test_bundle_render``.

Sections:

  A. live figures — capture, pixel identity with the saved file, hover names;
  B. the window — lists, drawing, restyling, pointing at a node, closing.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

import numpy as np  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from test_bundle_render import BUNDLE_SUFFIX, _run  # noqa: E402

Check = tuple[str, bool, str]
NETWORK = "2_MEA_NetworkPlot"


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _pixels(path: Path) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGBA"))


def _live_checks(bundle: Path, tmp: Path) -> list[Check]:
    from meanap.pipeline import hover
    from meanap.pipeline.figure_output import capture_figures
    from meanap.viewer.live import live_figure
    from meanap.viewer.server import ViewerService

    checks: list[Check] = []
    service = ViewerService(bundle)
    try:
        rec = service.manifest()["recordings"][0]
        lag = rec["lags"][0]
        names = [f["name"] for f in rec["figures"][str(lag)]]

        from meanap.native import output
        from meanap.native.network_paint import NetworkPainter

        live = live_figure(service, "network", rec["name"], NETWORK, lag=lag)
        native = isinstance(live.figure, output.NativeFigure)
        checks.append(("a network plot comes back as its scene, not a picture",
                       native and live.image is None and live.figure.kind == "network",
                       repr(type(live.figure))))
        checks.append(("and nothing is left capturing afterwards",
                       not list(tmp.glob("leak*")) and _capture_is_off(capture_figures), ""))
        scene = live.figure.scene

        # The claim the viewer rests on: what it paints is what the file holds.
        saved = service.figure(rec["name"], lag, NETWORK, fmt="png",
                               overrides={}, thumbnail=False)
        again = tmp / "live.png"
        output.render_image(NetworkPainter(scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(saved), _pixels(again)
        checks.append(("painting the scene gives the saved file's pixels",
                       a.shape == b.shape and np.array_equal(a, b),
                       f"{a.shape} vs {b.shape}"))
        for fmt in ("svg", "pdf"):
            vector = service.figure(rec["name"], lag, NETWORK, fmt=fmt,
                                    overrides={}, thumbnail=False)
            head = Path(vector).read_bytes()
            ok = (b"<image" not in head and head.count(b"<text") >= 5) if fmt == "svg" \
                else head.startswith(b"%PDF")
            checks.append((f"the pipeline's {fmt.upper()} is vector, from the same painter",
                           ok, f"{len(head)} bytes"))

        checks.append(("one name and one description per drawn node",
                       len(scene.names) == len(scene.xy) == len(scene.text) > 0,
                       f"{len(scene.names)}/{len(scene.xy)}/{len(scene.text)}"))
        # Names must follow positions: each named node sits where the run's
        # own coordinates put that channel.
        channels, coords, _ = _arrays(service, rec["name"])
        where = {str(c): xy for c, xy in zip(channels, coords)} if coords is not None else None
        if where is None:
            from meanap.pipeline.channel_layout import get_coords_from_layout

            chs, xy = get_coords_from_layout(service.ctx.params.channel_layout)
            where = {str(int(c)): p for c, p in zip(chs, xy)}
        ok = all(n in where and np.allclose(where[n], p)
                 for n, p in zip(scene.names, scene.xy))
        checks.append(("each name is the channel at that position", ok,
                       str(list(zip(scene.names, scene.xy.tolist()))[:3])))
        checks.extend(_scene_rule_checks())

        drawn = 0
        for name in names:
            got = live_figure(service, "network", rec["name"], name, lag=lag)
            drawn += got.figure is not None
        checks.append(("every network figure of the recording can be had live",
                       drawn == len(names), f"{drawn}/{len(names)}"))
        try:
            live_figure(service, "network", rec["name"], "no_such_figure", lag=lag)
            raised = False
        except ValueError:
            raised = True
        checks.append(("an unknown figure is an error, not an empty view", raised, ""))
    finally:
        service.close()
    return checks


def _scene_rule_checks() -> list[Check]:
    """The scene applies plot_network's sizing and legend rules, on the same data."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from meanap.native.scene import network_scene
    from meanap.network_plot import plot_network
    from meanap.pipeline import hover

    rng = np.random.default_rng(3)
    n = 24
    adj = rng.random((n, n)) * (rng.random((n, n)) < 0.3)
    adj = np.triu(adj, 1)
    adj = adj + adj.T
    coords = rng.random((n, 2)) * 8
    degree = (adj > 0).sum(axis=1).astype(float)
    strength = adj.sum(axis=1)
    checks: list[Check] = []
    for label, kw in (
        ("degree, flat colour", dict(z=degree)),
        ("degree, coloured, thresholded", dict(z=degree, z2=strength, z2_name="strength",
                                               edge_thresh=0.4)),
        ("strength, log scaling, batch bounds", dict(
            z=strength, z_name="node strength", z2=degree, z2_name="degree",
            node_scaling_method="Log2", z_scale_override=float(strength.max()) * 2,
            z2_bounds_override=(0.0, 30.0), edge_bounds_override=(0.1, 1.0),
            node_size_scale=0.6)),
    ):
        kw = dict(kw)
        thresh = kw.pop("edge_thresh", 0.0)
        z = kw.pop("z")
        z2, z2_name = kw.pop("z2", None), kw.pop("z2_name", "None")
        fig, ax = plt.subplots()
        plot_network(ax, adj, coords, thresh, z, z2, z2_name, **kw)
        group, spec = hover.points(ax)[0], hover.legend(ax)
        patches = np.asarray(ax.collections[1].get_facecolor())
        plt.close(fig)
        scene = network_scene(adj, coords, thresh, z, z2, z2_name, **kw)
        same_nodes = (np.allclose(scene.xy, group.xy)
                      and np.allclose(scene.diameter, 2 * group.radius)
                      and np.allclose(scene.colour, patches, atol=1e-6))
        same_key = (scene.size_items == [tuple(i) for i in spec["size"]["items"]]
                    # Widths as the old plotter's; shades differ on purpose —
                    # its weakest edge was white, which is an edge not drawn.
                    and np.allclose([i[1] for i in scene.edge_items],
                                    [i[1] for i in spec["edges"]["items"]])
                    and all(0.2 - 1e-9 <= i[2] <= 0.86 + 1e-9 for i in scene.edge_items)
                    and float(scene.edge_grey.max(initial=0.0)) <= 0.86 + 1e-9
                    and [i[0] for i in scene.edge_items]
                    == [i[0] for i in spec["edges"]["items"]]
                    and (scene.colour_key is None) == (spec["colour"] is None))
        pairs = np.triu((adj > 0) & (adj >= thresh), 1)
        present = np.zeros(n, dtype=bool)
        present[scene.index] = True
        expect = int((pairs & np.outer(present, present)).sum())
        checks.append((f"the scene follows the old plotter's rules ({label})",
                       same_nodes and same_key and len(scene.edge_nodes) == expect,
                       f"nodes {same_nodes}, key {same_key}, "
                       f"{len(scene.edge_nodes)}/{expect} edges"))
    # Every edge below a batch-wide scale: still drawn, and still visible.
    from meanap.native import output
    from meanap.native.network_paint import NetworkPainter

    weak = adj * 0.05                                  # all weights under 0.1
    faint = network_scene(weak, coords, 0.0, degree, edge_bounds_override=(0.1, 1.0))
    bare = network_scene(np.zeros_like(weak), coords, 0.0, degree,
                         edge_bounds_override=(0.1, 1.0))
    with_edges = output_pixels(NetworkPainter(faint), None)
    without = output_pixels(NetworkPainter(bare), None)
    checks.append(("edges below the bottom of a batch scale are light grey, not white",
                   len(faint.edge_nodes) > 0 and np.allclose(faint.edge_grey, 0.86)
                   and not np.array_equal(with_edges, without),
                   f"{len(faint.edge_nodes)} edges, shade {faint.edge_grey[:1]}"))
    thresholded = network_scene(weak, coords, float(weak.max()) + 1, degree)
    checks.append(("and leaving weak edges out is the edge threshold's job",
                   len(thresholded.edge_nodes) == 0, f"{len(thresholded.edge_nodes)} edges"))
    return checks


def _activity_checks(tmp: Path) -> list[Check]:
    """The electrode heatmap and the raster: file, painter and view agree."""
    from meanap.gui.figure_canvas import FigureCanvas
    from meanap.native import output
    from meanap.native.activity_paint import HeatmapPainter, RasterPainter
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.plotting_step2 import plot_heatmap, plot_raster

    checks: list[Check] = []
    rng = np.random.default_rng(11)
    from meanap.pipeline.channel_layout import get_coords_from_layout

    channels, _ = get_coords_from_layout("MCS60")
    channels = np.asarray(channels)[:40]
    rate = rng.gamma(1.0, 2.0, len(channels))
    rate[5] = np.nan
    grounded = {int(channels[2])}
    spikes = {i: np.sort(rng.uniform(0, 95.5, int(rng.integers(0, 400))))
              for i in range(len(channels))}

    def heatmap(path):
        plot_heatmap(rate, channels, "recA", "mean firing rate (Hz)", path,
                     channel_layout="MCS60", batch_max=30.0, grounded=grounded)

    def raster(path):
        plot_raster(spikes, 95.5, path, spike_freq_max=12.0, rec_name="rec_A",
                    names=channels.tolist())

    for label, draw, painter_type in (("heatmap", heatmap, HeatmapPainter),
                                      ("raster", raster, RasterPainter)):
        saved = tmp / f"{label}.png"
        draw(saved)
        with capture_figures() as got:
            draw(tmp / f"{label}-not-written.png")
        native = got[0].figure if got else None
        ok = (saved.exists() and isinstance(native, output.NativeFigure)
              and isinstance(native.painter, painter_type)
              and not (tmp / f"{label}-not-written.png").exists())
        checks.append((f"the {label} is drawn by Qt, and captured as its scene", ok, ""))
        if not ok:
            continue
        again = tmp / f"{label}-live.png"
        output.render_image(painter_type(native.scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(saved), _pixels(again)
        checks.append(("painting its scene gives the saved file's pixels",
                       a.shape == b.shape and np.array_equal(a, b), f"{a.shape} vs {b.shape}"))
        for fmt in ("svg", "pdf"):
            draw(tmp / f"{label}.{fmt}")
        svg = (tmp / f"{label}.svg").read_text()
        checks.append(("and it writes SVG with real text, and PDF",
                       svg.count("<text") >= 4
                       and (tmp / f"{label}.pdf").read_bytes().startswith(b"%PDF"),
                       f"{svg.count('<text')} texts"))

        canvas = FigureCanvas()
        canvas.resize(1100, 700)
        canvas.show()
        canvas.show_figure(native)
        _wait()
        fig, scene = canvas.painter, canvas.scene
        heard: list[str] = []
        canvas.hovered.connect(heard.append)
        if label == "heatmap":
            values = scene.values
            checks.append(("grounded and missing electrodes have no value",
                           int(np.isnan(values).sum()) == 2 and len(scene.panels) == 2,
                           str(int(np.isnan(values).sum()))))
            finite = values[np.isfinite(values)]
            low, high = scene.panels[0][1:]
            checks.append(("its own scale runs from the lowest value to the 99th percentile, "
                           "the batch's to the batch maximum",
                           abs(low - finite.min()) < 1e-9
                           and abs(high - np.percentile(finite, 99)) < 1e-9
                           and scene.panels[1][2] == 30.0, f"{low}–{high}"))
            at = fig._pixels(1)[7]
            what = fig.under(float(at[0]), float(at[1]))
            canvas.point(what)
            checks.append(("pointing at an electrode, on either panel, names it with its value",
                           what == 7 and scene.names[7] in heard[-1]
                           and f"{values[7]:.4g}" in heard[-1], str(heard[-1:])))
            canvas.click(what)
            canvas.point(None)
            checks.append(("clicking keeps it marked", canvas.pinned == 7 and fig.marked == 7, ""))
            canvas.click(what)
            checks.append(("and clicking again lets go", canvas.pinned is None, ""))
        else:
            counts = scene.counts
            checks.append(("a row per channel and a column per second, counting every spike",
                           counts.shape == (len(channels), 96)
                           and int(counts.sum()) == sum(len(t) for t in spikes.values()),
                           str(counts.shape)))
            top, bottom = fig.axes
            x, y = float(top.x_pixel(30.5 / 60)), float(top.y_pixel(3.5))   # mid-cell
            what = fig.under(x, y)
            canvas.point(what)
            checks.append(("pointing at a cell gives the electrode, the time and the rate",
                           what == (3, 30) and scene.names[3] in heard[-1]
                           and f"{counts[3, 30]:.4g} Hz" in heard[-1], str(heard[-1:])))
            canvas.point(None)
            whole = top.xlim
            canvas._move("0", top, lambda axes, ax, ay: axes.zoom(2.0, x, y,
                                                                 along_x=ax, along_y=ay))
            checks.append(("zooming one panel zooms the other with it",
                           top.xlim != whole and bottom.xlim == top.xlim
                           and bottom.ylim == top.ylim, f"{top.xlim} / {bottom.xlim}"))
            canvas.reset_view()
            checks.append(("and Reset view shows the whole recording again",
                           top.xlim == whole and bottom.xlim == whole, ""))
        canvas.close()
    return checks


def _violin_and_circular_checks(tmp: Path) -> list[Check]:
    """Half-violins and circular networks: file, painter and view agree."""
    from meanap.gui.figure_canvas import FigureCanvas
    from meanap.gui.network_canvas import NetworkCanvas
    from meanap.native import output
    from meanap.native.network_paint import NetworkPainter
    from meanap.native.scene import chord_arcs
    from meanap.native.violin_paint import ViolinPainter
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.plotting_step2 import plot_firing_rate_distribution
    from meanap.pipeline.plotting_step4 import (
        plot_circular_cartography_network, plot_circular_module_network,
        plot_graph_metrics_by_node,
    )

    checks: list[Check] = []
    rng = np.random.default_rng(21)
    n = 30
    adj = rng.random((n, n)) * (rng.random((n, n)) < 0.2)
    adj = np.triu(adj, 1)
    adj = adj + adj.T
    nd = (adj > 0).sum(axis=1).astype(float)
    ns = adj.sum(axis=1)
    mew = np.divide(ns, nd, out=np.zeros(n), where=nd > 0)
    pc = rng.random(n)
    pc[4] = np.nan
    bc = rng.random(n)
    names = [f"E{i}" for i in range(n)]
    modules = rng.integers(1, 5, n)
    roles = rng.integers(1, 7, n)

    def metrics(path):
        plot_graph_metrics_by_node(nd, mew, ns, None, np.zeros(n), pc, bc, 10, "rec_A",
                                   path, rng=np.random.default_rng(5), names=names,
                                   noun="electrode")

    def firing(path):
        plot_firing_rate_distribution({"FR": ns}, path, seed=3, rec_name="rec_A", div=14,
                                      names=names)

    def module(path):
        plot_circular_module_network(adj, modules, nd, 10, "rec_A", path, names=names,
                                     noun="electrode")

    def cartography(path):
        plot_circular_cartography_network(adj, roles, 10, "rec_A", path, names=names,
                                          noun="electrode")

    figures = {}
    for label, draw, painter_type, kind in (
            ("graph metrics by node", metrics, ViolinPainter, "violin"),
            ("firing rate by electrode", firing, ViolinPainter, "violin"),
            ("circular module network", module, NetworkPainter, "circular"),
            ("circular cartography network", cartography, NetworkPainter, "circular")):
        stem = label.replace(" ", "_")
        saved = tmp / f"{stem}.png"
        draw(saved)
        with capture_figures() as got:
            draw(tmp / f"{stem}-not-written.png")
        native = got[0].figure if got else None
        ok = (saved.exists() and isinstance(native, output.NativeFigure)
              and isinstance(native.painter, painter_type) and native.kind == kind)
        checks.append((f"{label} is drawn by Qt, and captured as its scene", ok, ""))
        if not ok:
            continue
        figures[label] = native
        again = tmp / f"{stem}-live.png"
        output.render_image(painter_type(native.scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(saved), _pixels(again)
        checks.append(("…and painting its scene gives the saved file's pixels",
                       a.shape == b.shape and np.array_equal(a, b), f"{a.shape} vs {b.shape}"))
        draw(tmp / f"{stem}.svg")
        svg = (tmp / f"{stem}.svg").read_text()
        checks.append(("…and its SVG has real text and no picture of the plot",
                       svg.count("<text") >= 3 and (kind == "violin" or "<image" not in svg),
                       f"{svg.count('<text')} texts"))

    native = figures.get("graph metrics by node")
    if native is not None:
        scene = native.scene
        labels = [p.label for p in scene.panels]
        checks.append(("seven panels in MATLAB's order, the uncomputed ones left empty",
                       len(labels) == 7 and labels[0] == "node degree"
                       and len(scene.panels[3].values) == 0        # z-score: not given
                       and len(scene.panels[4].values) == 0        # local efficiency: all zero
                       and len(scene.panels[5].values) == n - 1,   # one NaN dropped
                       str([len(p.values) for p in scene.panels])))
        panel = scene.panels[0]
        checks.append(("a panel holds every finite value, its mean and its density",
                       np.allclose(np.sort(panel.values), np.sort(nd))
                       and abs(panel.mean - nd.mean()) < 1e-9
                       and abs(panel.curve_x.max() - 1.0) < 1e-9 and len(panel.curve_y) == 256,
                       ""))
        canvas = FigureCanvas()
        canvas.resize(1400, 620)
        canvas.show()
        canvas.show_figure(native)
        _wait()
        fig = canvas.painter
        heard: list[str] = []
        canvas.hovered.connect(heard.append)
        px, py = fig._points(0)
        what = fig.under(float(px[6]), float(py[6]))
        canvas.point(what)
        row = int(scene.panels[0].rows[6])
        # Points can coincide (several nodes of one degree): whichever is under
        # the pointer, it must be described by its own values.
        said = heard[-1] if heard else ""
        checks.append(("pointing at a point names the node, with its value in every panel",
                       what is not None and names[what] in said
                       and f"node degree: {nd[what]:.4g}" in said
                       and f"node strength: {ns[what]:.4g}" in said, said))
        checks.append(("and marks that node in the other panels",
                       fig.marked == what and what in scene.panels[2].rows, str(row)))
        canvas.point(None)
        before = fig.axes[0].ylim
        canvas._move("0", fig.axes[0], lambda axes, ax, ay: axes.zoom(
            2.0, float(px[6]), float(py[6]), along_x=ax, along_y=ay))
        checks.append(("a panel zooms along its values only, and on its own",
                       fig.axes[0].ylim != before and fig.axes[0].xlim == fig.axes[0].home[0]
                       and fig.axes[1].ylim == fig.axes[1].home[1], ""))
        canvas.close()

    native = figures.get("circular module network")
    if native is not None:
        scene = native.scene
        on_circle = np.allclose(np.hypot(*scene.xy.T), 1.0)
        arcs = scene.edge_arcs
        ends_ok = (np.allclose(arcs[:, 0], scene.xy[scene.edge_nodes[:, 0]], atol=1e-9)
                   and np.allclose(arcs[:, -1], scene.xy[scene.edge_nodes[:, 1]], atol=1e-9))
        inside = bool((np.hypot(arcs[..., 0], arcs[..., 1]) <= 1 + 1e-9).all())
        checks.append(("nodes sit on the circle and edges curve between them, inside it",
                       on_circle and ends_ok and inside and len(arcs) == int((adj > 0).sum() // 2),
                       f"{len(arcs)} edges"))
        # Each arc meets the circle at right angles: its first step points at the centre
        # of its own circle, which is perpendicular to the radius there... checked on one.
        opposite = chord_arcs([0.0], [np.pi])
        checks.append(("opposite nodes are joined by a straight line through the centre",
                       np.allclose(opposite[0, :, 1], 0.0, atol=1e-9)
                       and abs(opposite[0, 16, 0]) < 1e-9, ""))
        biggest = float(scene.diameter.max())
        gap = float(np.hypot(*(scene.xy[0] - scene.xy[1]))) if len(scene.xy) > 1 else 0
        checks.append(("the busiest node is as wide as the gap between neighbours",
                       abs(biggest - 2 * np.sin(np.pi / n)) < 1e-9, f"{biggest} vs {gap}"))
        checks.append(("its legend names the modules and gives three degree samples",
                       [i[0] for i in scene.category_key["items"]]
                       == [str(m) for m in sorted(set(modules.tolist()))]
                       and len(scene.size_items) == 3, str(scene.category_key["items"][:2])))
        canvas = NetworkCanvas()
        canvas.resize(1000, 760)
        canvas.show()
        canvas.show_scene(scene)
        _wait()
        hub = int(np.argmax(scene.diameter))
        said: list[str] = []
        canvas.picked.connect(said.append)
        canvas.click(hub)
        checks.append(("a node can be selected there too, with its connections counted",
                       canvas.selected == hub and scene.names[hub] in said[-1]
                       and f"{len(scene.neighbours(hub))} connection" in said[-1]
                       and "module" in said[-1], str(said[-1:])))
        canvas.close()
    native = figures.get("circular cartography network")
    if native is not None:
        scene = native.scene
        checks.append(("by cartography role: nodes one size, six roles named, no size key",
                       len(set(np.round(scene.diameter, 12))) == 1
                       and len(scene.category_key["items"]) == 6 and not scene.size_items
                       and scene.text[0].startswith("role: "), scene.text[0]))
    return checks


def _pair_checks(tmp: Path) -> list[Check]:
    """Two network panels side by side: the two scales, and field beside network."""
    from meanap.gui.network_canvas import NetworkCanvas
    from meanap.native import output
    from meanap.native.network_paint import NetworkPairPainter
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.plotting_step4 import (
        plot_network_beside_field, plot_spatial_network_combined,
    )

    checks: list[Check] = []
    rng = np.random.default_rng(8)
    n = 40
    coords = rng.random((n, 2)) * 400
    adj = rng.random((n, n)) * (rng.random((n, n)) < 0.12)
    adj = np.triu(adj, 1)
    adj = adj + adj.T
    degree = (adj > 0).sum(axis=1).astype(float)
    strength = adj.sum(axis=1)
    image = rng.random((64, 64))
    cells = np.arange(100, 100 + n)

    def combined(path):
        plot_spatial_network_combined(
            adj, cells, "MCS60", degree, strength, "node strength", 1000, "rec_A", path,
            z_scale_override=float(degree.max()) * 2, z2_bounds_override=(0.0, 20.0),
            edge_bounds_override=(0.1, 1.0), coords_override=coords, node_size_scale="auto")

    def field(path):
        plot_network_beside_field(
            adj, cells, "MCS60", degree, 1000, "rec_A", path,
            background=(image, (0, 400, 0, 400)), coords_override=coords,
            node_size_scale="auto")

    for label, draw, kind in (("the two-scale network", combined, "network"),
                              ("field of view beside network", field, "field")):
        stem = label.replace(" ", "_")
        saved = tmp / f"{stem}.png"
        draw(saved)
        with capture_figures() as got:
            draw(tmp / f"{stem}-not-written.png")
        native = got[0].figure if got else None
        ok = (saved.exists() and isinstance(native, output.NativeFigure)
              and isinstance(native.painter, NetworkPairPainter) and native.kind == kind)
        checks.append((f"{label} is drawn by Qt, as two panels", ok, ""))
        if not ok:
            continue
        again = tmp / f"{stem}-live.png"
        output.render_image(NetworkPairPainter(native.scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(saved), _pixels(again)
        checks.append(("…and painting its scene gives the saved file's pixels",
                       a.shape == b.shape and np.array_equal(a, b), f"{a.shape} vs {b.shape}"))
        scene = native.scene
        canvas = NetworkCanvas()
        canvas.resize(1500, 700)
        canvas.show()
        canvas.show_figure(native)
        _wait()
        fig = canvas.painter
        left, right = fig.panels
        half = fig.size[0] / 2
        at = right.to_pixel(scene.right.xy[:1])[0]
        if kind == "network":
            checks.append(("the panels differ only in what they are scaled to",
                           np.allclose(scene.left.xy, scene.right.xy)
                           and scene.left.names == scene.right.names
                           and not np.allclose(scene.left.diameter, scene.right.diameter)
                           and scene.left.colour_key["max"] != scene.right.colour_key["max"],
                           f"{scene.left.colour_key['max']} vs {scene.right.colour_key['max']}"))
            checks.append(("a node is found under the pointer on either panel",
                           fig.node_at(float(at[0]), float(at[1])) == 0
                           and fig.node_at(float(at[0]) + half, float(at[1])) == 0, ""))
        else:
            checks.append(("the left panel is the image alone, in the network's view",
                           scene.left_is_field and not left.show_network
                           and scene.left.background is not None
                           and left.scale == right.scale and left.centre == right.centre
                           and fig.node_at(float(at[0]), float(at[1])) is None
                           and fig.node_at(float(at[0]) + half, float(at[1])) == 0, ""))
            whole = _pixels(saved)
            mid = whole.shape[1] // 2
            # Node colour appears on the right half and nowhere on the left.
            cyan = lambda px: int(((px[..., 0] < 40) & (px[..., 1] > 160) & (px[..., 2] > 190)).sum())
            checks.append(("so no node is drawn over the image",
                           cyan(whole[:, :mid]) == 0 and cyan(whole[:, mid:]) > 100,
                           f"{cyan(whole[:, :mid])} / {cyan(whole[:, mid:])}"))
        before = (right.scale, right.centre)
        fig.zoom(1.5, float(at[0]) + (half if kind == "field" else 0), float(at[1]))
        checks.append(("zooming one panel zooms the other to the same view",
                       left.scale == right.scale != before[0] and left.centre == right.centre
                       and not fig.fitted, ""))
        canvas.reset_view()
        said: list[str] = []
        canvas.picked.connect(said.append)
        canvas.click(0)
        checks.append(("a node selected on one panel is selected on both, and named",
                       left.selected == right.selected == 0 and "Cell 100" in said[-1],
                       str(said[-1:])))
        for suffix in ("svg", "pdf"):
            canvas.export(str(tmp / f"{stem}-shown.{suffix}"))
        checks.append(("and it exports as shown, to SVG and PDF",
                       (tmp / f"{stem}-shown.svg").stat().st_size > 1000
                       and (tmp / f"{stem}-shown.pdf").read_bytes().startswith(b"%PDF"), ""))
        canvas.close()
    return checks


def _spike_check_data():
    """A synthetic step-1 check record: six methods, nine trace panels."""
    from meanap.pipeline.plotting import SpikeCheckData

    rng = np.random.default_rng(2)
    fs = 25000.0
    methods = ["thr4", "thr4p5", "thr5", "mea", "bior1p5", "bior1p3"]
    duration, bins, window = 300.0, 300, int(0.06 * fs) + 2
    curves = np.abs(rng.normal(2, 0.6, (len(methods), bins))) + np.arange(len(methods))[:, None]
    starts = rng.integers(0, int(duration * fs) - window, 9).astype(int)
    windows = rng.normal(0, 5, (9, window))
    frames = [[np.sort(starts[i] + rng.integers(5, window - 5, 1 + m % 3))
               for m in range(len(methods))] for i in range(9)]
    waves = {m: rng.normal(0, 4, (20 + 30 * k, 51)) for k, m in enumerate(methods)}
    waves["bior1p3"] = np.zeros((0, 51))
    return SpikeCheckData(
        rec_name="rec_A", fs=fs, methods=methods, freq_curves=curves, duration_s=duration,
        trace_channels=rng.integers(11, 88, 9), trace_windows=windows, trace_starts=starts,
        trace_views=np.column_stack([starts + 1, starts + window - 1]),
        trace_stds=np.full(9, 5.0), trace_spike_frames=frames,
        wave_channel=47, wave_std=6.0, waveforms=waves)


def _spike_check_checks(tmp: Path) -> list[Check]:
    """The three step-1 check figures: file, painter and view agree."""
    from meanap.gui.figure_canvas import FigureCanvas
    from meanap.native import output
    from meanap.native.spike_check_paint import (
        FrequenciesPainter, TracesPainter, WaveformsPainter,
    )
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.plotting import draw_spike_check_figures

    checks: list[Check] = []
    data = _spike_check_data()
    out = tmp / "spike-checks"
    written = draw_spike_check_figures(data, out)
    checks.append(("all three figures are written",
                   sorted(p.stem for p in written)
                   == ["1_ExampleTraces", "2_SpikeFrequencies", "3_Waveforms"]
                   and all(p.exists() for p in written), str([p.name for p in written])))
    only = draw_spike_check_figures(data, tmp / "one", only="3_Waveforms", fmt="svg")
    checks.append(("one can be asked for alone, as vector",
                   [p.name for p in only] == ["3_Waveforms.svg"]
                   and "<svg" in only[0].read_text()[:400], str([p.name for p in only])))
    with capture_figures() as got:
        draw_spike_check_figures(data, tmp / "not-written")
    captured = {Path(c.path).stem: c.figure for c in got}
    checks.append(("under capture nothing is written and the three scenes are handed over",
                   not (tmp / "not-written").exists() and len(captured) == 3
                   and all(isinstance(f, output.NativeFigure) for f in captured.values()), ""))
    for stem, painter_type in (("2_SpikeFrequencies", FrequenciesPainter),
                               ("1_ExampleTraces", TracesPainter),
                               ("3_Waveforms", WaveformsPainter)):
        native = captured.get(stem)
        if native is None:
            continue
        again = tmp / f"{stem}-live.png"
        output.render_image(painter_type(native.scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(out / f"{stem}.png"), _pixels(again)
        checks.append((f"{stem}: painting its scene gives the saved file's pixels",
                       isinstance(native.painter, painter_type) and a.shape == b.shape
                       and np.array_equal(a, b), f"{a.shape} vs {b.shape}"))
        canvas = FigureCanvas()
        canvas.resize(1300, 820)
        canvas.show()
        canvas.show_figure(native)
        _wait()
        fig = canvas.painter
        heard: list[str] = []
        canvas.hovered.connect(heard.append)
        if stem == "2_SpikeFrequencies":
            axes = fig.axes
            x = float(axes.x_pixel(120))
            y = float(axes.y_pixel(data.freq_curves[3, 119]))
            what = fig.under(x, y)
            canvas.point(what)
            checks.append(("pointing at a curve names its method, the time and the rate",
                           what == (3, 119) and "mea" in heard[-1] and "2 min 00 s" in heard[-1]
                           and f"{data.freq_curves[3, 119]:.4g} Hz" in heard[-1],
                           str(heard[-1:])))
            checks.append(("the time axis is marked in minutes",
                           axes.x_tick_values[:2] == [(60.0, "1"), (120.0, "2")]
                           and len(axes.x_tick_values) == 5, str(axes.x_tick_values[:2])))
            canvas.click(what)
            canvas.point(None)
            checks.append(("clicking a method keeps it; again lets go",
                           canvas.pinned == (3, 119), ""))
            canvas.click(what)
            checks.append(("…and clicking it again lets go", canvas.pinned is None, ""))
        elif stem == "1_ExampleTraces":
            frame = int(data.trace_spike_frames[2][4][0])
            x = float(fig.axes[2].x_pixel(frame))
            y = float(fig.axes[2].y_pixel(fig._marker_y(2, 4)))
            what = fig.under(x, y)
            canvas.point(what)
            checks.append(("pointing at a marker says which method found a spike, and when",
                           what == (2, 4, frame) and "bior1.5" in heard[-1]
                           and f"{frame / data.fs:.4f} s" in heard[-1], str(heard[-1:])))
            checks.append(("one panel per example, the voltage range set by the noise level",
                           len(fig.axes) == 9 and fig.axes[0].ylim == (-30.0, 25.0), ""))
            before = fig.axes[2].xlim
            canvas._move("2", fig.axes[2], lambda axes, ax, ay: axes.zoom(
                2.0, x, y, along_x=ax, along_y=ay))
            checks.append(("a panel zooms in time, on its own, and not in voltage",
                           fig.axes[2].xlim != before and fig.axes[2].ylim == (-30.0, 25.0)
                           and fig.axes[3].xlim == fig.axes[3].home[0], ""))
        else:
            checks.append(("a panel per method, on one voltage scale, the empty one left empty",
                           len(fig.axes) == 6 and len({a.ylim for a in fig.axes}) == 1
                           and not fig._clouds[5] and len(fig._clouds[0]) == 20 * 50,
                           str([len(c) for c in fig._clouds])))
            rect = fig.axes[1].rect
            what = fig.under(rect.center().x(), rect.center().y())
            canvas.point(what)
            checks.append(("pointing at a panel counts the spikes shown",
                           what == 1 and "thr4.5" in heard[-1] and "50 spikes" in heard[-1],
                           str(heard[-1:])))
            canvas._move("1", fig.axes[1], lambda axes, ax, ay: axes.zoom(
                2.0, rect.center().x(), rect.center().y(), along_x=ax, along_y=ay))
            checks.append(("zooming the voltage of one zooms them all",
                           len({a.ylim for a in fig.axes}) == 1
                           and fig.axes[0].ylim != fig.axes[0].home[1], ""))
        canvas.close()
    return checks


def _arrays(service, recording):
    from meanap.pipeline.render import _recording_arrays

    return _recording_arrays(service.ctx, recording)


def _capture_is_off(capture_figures) -> bool:
    from meanap.pipeline import figure_output

    return figure_output._capture.get() is None


def _remaining_checks(tmp: Path) -> list[Check]:
    """Burst detection, node cartography and the CAT-NAP rasters."""
    from meanap.catnap.rasters import plot_activity_raster
    from meanap.gui.figure_canvas import FigureCanvas
    from meanap.native import output
    from meanap.native.activity_paint import BurstPainter, RasterPainter
    from meanap.native.cartography_paint import CartographyPainter
    from meanap.native.figure import MatrixImage
    from meanap.native.scene import burst_scene
    from meanap.params import Params
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.network_metrics import classify_node_cartography
    from meanap.pipeline.plotting_step2 import plot_burst_detection_info
    from meanap.pipeline.plotting_step4 import plot_node_cartography

    checks: list[Check] = []
    rng = np.random.default_rng(21)
    duration = 120.0
    spans = np.array([[10.0, 11.0], [40.0, 41.5], [41.0, 43.0], [90.0, 90.5]])
    spikes = {}
    for ch in range(12):
        loose = rng.uniform(0, duration, int(rng.integers(20, 200)))
        tight = np.concatenate([rng.uniform(a, b, 15) for a, b in spans])
        spikes[ch] = np.sort(np.concatenate([loose, tight]))
    names = [str(11 + i) for i in range(12)]

    params = Params()
    pc = rng.beta(2, 3, 50) * 0.8
    z = rng.normal(0, 1.4, 50)
    z[4] = np.nan
    roles, _ = classify_node_cartography(
        pc, z, params.hub_boundary_wm_d_deg, params.peri_part_coef,
        params.non_hub_connector_part_coef, params.pro_hub_part_coef,
        params.connector_hub_part_coef)
    cells = [f"c{i}" for i in range(50)]

    binned = rng.poisson(0.3, (90, 700)).astype(np.float32)        # (bins, cells)
    binned[:, 5] = 0.0
    binned[40, 5] = 3.0                                            # one lone event

    def bursts(path):
        plot_burst_detection_info(spikes, {"burstTimes": spans}, duration, 25000.0, path,
                                  names=names)

    def cartography(path):
        plot_node_cartography(pc, z, params, 25, "recA", path, nd_cart_div=roles,
                              names=cells, noun="cell")

    def activity(path):
        plot_activity_raster(binned, path, activity="peaks", title="recA — peaks")

    def zscored(path):
        plot_activity_raster(binned, path, activity="peaks", title="recA z", zscored=True)

    for label, draw, painter_type in (("burst figure", bursts, BurstPainter),
                                      ("cartography scatter", cartography, CartographyPainter),
                                      ("activity raster", activity, RasterPainter),
                                      ("z-scored raster", zscored, RasterPainter)):
        stem = label.replace(" ", "-")
        saved = tmp / f"{stem}.png"
        draw(saved)
        with capture_figures() as got:
            draw(tmp / f"{stem}-not-written.png")
        native = got[0].figure if got else None
        ok = (saved.exists() and isinstance(native, output.NativeFigure)
              and isinstance(native.painter, painter_type)
              and not (tmp / f"{stem}-not-written.png").exists())
        checks.append((f"the {label} is drawn by Qt, and captured as its scene", ok, ""))
        if not ok:
            continue
        again = tmp / f"{stem}-live.png"
        output.render_image(painter_type(native.scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(saved), _pixels(again)
        checks.append(("painting its scene gives the saved file's pixels",
                       a.shape == b.shape and np.array_equal(a, b), f"{a.shape} vs {b.shape}"))
        for fmt in ("svg", "pdf"):
            draw(tmp / f"{stem}.{fmt}")
        svg = (tmp / f"{stem}.svg").read_text()
        checks.append(("and it writes SVG with real text, and PDF",
                       svg.count("<text") >= 4
                       and (tmp / f"{stem}.pdf").read_bytes().startswith(b"%PDF"),
                       f"{svg.count('<text')} texts"))

        canvas = FigureCanvas()
        canvas.resize(1000, 800)
        canvas.show()
        canvas.show_figure(native)
        _wait()
        fig, scene = canvas.painter, canvas.scene
        heard: list[str] = []
        canvas.hovered.connect(heard.append)
        if label == "burst figure":
            total = sum(len(t) for t in spikes.values())
            slow = sum(int(any(a <= t <= b for a, b in spans))
                       for times in spikes.values() for t in times)
            checks.append(("every spike is counted, and those inside a burst — overlapping "
                           "bursts included — as the slow way counts them",
                           int(scene.full.sum()) == total and int(scene.bursts.sum()) == slow
                           and scene.full.shape == (12, 1200),
                           f"{int(scene.bursts.sum())} vs {slow}"))
            pooled = np.sort(np.concatenate(list(spikes.values())))
            gaps = np.diff(pooled)
            mid = pooled[:-1] + gaps / 2
            inside = np.array([any(a <= m <= b for a, b in spans) for m in mid])
            checks.append(("intervals are split by where their midpoint falls",
                           scene.n_within == int(inside.sum())
                           and scene.n_outside == int((~inside).sum())
                           and len(scene.isi_edges) == 100, f"{scene.n_within}"))
            top, bottom = fig.axes
            x, y = float(top.x_pixel(40.25)), float(top.y_pixel(3.5))
            what = fig.under(x, y)
            canvas.point(what)
            count = int(scene.full[3, 402])
            checks.append(("pointing at a cell gives the electrode, the time and the spikes",
                           what == ("raster", 0, 3, 402) and "Electrode 14" in heard[-1]
                           and "0 min 40.2 s" in heard[-1]
                           and (f"{count} spike" in heard[-1]), str(heard[-1:])))
            xb, yb = float(bottom.x_pixel(40.25)), float(bottom.y_pixel(3.5))
            canvas.point(fig.under(xb, yb))
            checks.append(("and in the lower raster, only those inside bursts",
                           "inside bursts" in heard[-1], str(heard[-1:])))
            isi = fig.isi
            xi = float(isi.x_pixel(np.log10(np.sqrt(scene.isi_edges[30] * scene.isi_edges[31]))))
            what = fig.under(xi, float(isi.rect.center().y()))
            canvas.point(what)
            checks.append(("pointing at the distribution reads both densities for that interval",
                           what == ("isi", 30) and "outside bursts" in heard[-1]
                           and "within bursts" in heard[-1], str(heard[-1:])))
            canvas.point(None)
            whole = top.xlim
            canvas._move("0", top, lambda axes, ax, ay: axes.zoom(2.0, x, y,
                                                                 along_x=ax, along_y=ay))
            checks.append(("zooming one raster zooms the other; the distribution stays put",
                           top.xlim != whole and bottom.xlim == top.xlim
                           and fig.zoomable("isi") == (False, False)
                           and isi.xlim == isi.home[0], f"{top.xlim}"))
            canvas.reset_view()
            # With no spikes at all the figure is still drawn.
            empty = tmp / "burst-empty.png"
            plot_burst_detection_info({i: np.array([]) for i in range(4)}, {}, 30.0,
                                      25000.0, empty)
            none = burst_scene({i: np.array([]) for i in range(4)}, [], 30.0)
            checks.append(("a recording with no spikes still gets its figure",
                           empty.exists() and none.isi_edges is None, ""))
        elif label == "cartography scatter":
            checks.append(("a node with no z-score is not drawn, and the rest keep their roles",
                           len(fig._drawn) == 49 and 4 not in fig._drawn
                           and np.array_equal(scene.role[fig._drawn],
                                              np.asarray(roles)[fig._drawn]), ""))
            low, high = scene.xlim
            checks.append(("the range leaves room for the nodes at either end",
                           low < np.nanmin(pc) and high > np.nanmax(pc), f"{low}–{high}"))
            at = fig._pixels()[7]
            node = int(fig._drawn[7])
            what = fig.under(float(at[0]), float(at[1]))
            canvas.point(what)
            role = scene.roles[int(scene.role[node])][0]
            checks.append(("pointing at a node names it, its role and its two values",
                           what == node and f"Cell c{node}" in heard[-1] and role in heard[-1]
                           and f"{pc[node]:.3g}" in heard[-1], str(heard[-1:])))
            canvas.click(what)
            canvas.point(None)
            checks.append(("clicking keeps it marked", fig.marked == node, ""))
            canvas.click(what)
            checks.append(("the picture of the roles is under the plot",
                           scene.diagram is not None and not fig._diagram.isNull(), ""))
        elif label == "activity raster":
            checks.append(("a row per cell and a column per bin, the first cell at the top",
                           scene.counts.shape == (700, 90) and scene.noun == "cell"
                           and scene.counts[5, 40] == 3.0 and not scene.symmetric,
                           str(scene.counts.shape)))
            axes = fig.axes[0]
            x, y = float(axes.x_pixel(40.5)), float(axes.y_pixel(5.5))
            what = fig.under(x, y)
            canvas.point(what)
            checks.append(("pointing at a cell gives the cell, the time and the value",
                           what == (5, 40) and "Cell 6" in heard[-1]
                           and "3 events/s" in heard[-1], str(heard[-1:])))
            # 700 rows on a panel a few hundred pixels tall: rows share pixels,
            # and the lone event must still show.
            image = MatrixImage(scene.counts, scene.cmap, 0.0, 3.0)
            pooled = image.pooled(3, 1)
            checks.append(("rows that share a pixel are pooled, so a lone event is not skipped",
                           pooled.shape == (234, 90) and abs(pooled[1, 40] - (
                               scene.counts[3:6, 40].mean())) < 1e-6 and pooled[1, 40] >= 1.0,
                           str(pooled.shape)))
        else:
            high = scene.panels[0][1]
            checks.append(("the z-scored scale is symmetric about zero",
                           scene.symmetric and high >= 1.0 and "z-score" in scene.label,
                           f"{high}"))
        canvas.close()
    return checks


def _group_frame():
    """Recording- and node-level rows: two groups, two ages, a few recordings each."""
    import pandas as pd

    rng = np.random.default_rng(31)
    rec_rows, node_rows = [], []
    for grp in ("WT", "KO"):
        for div in ("7", "14"):
            for r in range(4):
                name = f"{grp}_DIV{div}_r{r}"
                for lag in (10, 25):
                    shift = (1.0 if grp == "KO" else 0.0) + (0.5 if div == "14" else 0.0)
                    density = float(np.clip(rng.normal(0.3 + 0.1 * shift, 0.05), 0, 1))
                    rec_rows.append({"FileName": name, "Grp": grp, "DIV": div, "Lag": lag,
                                     "Dens": density, "aN": float(rng.integers(20, 60)),
                                     "Empty": np.nan,
                                     "Partial": np.nan if r == 0 else float(rng.normal()),
                                     **{f"NCpn{i}": float(v) for i, v in
                                        enumerate(rng.dirichlet(np.ones(6)), start=1)}})
                    for ch in range(12):
                        node_rows.append({"FileName": name, "Grp": grp, "DIV": div,
                                          "Lag": lag, "Channel": ch + 1,
                                          "ND": float(rng.poisson(5 + 3 * shift)),
                                          "CellType": "E" if ch % 3 else "I"})
    return pd.DataFrame(rec_rows), pd.DataFrame(node_rows)


def _group_checks(tmp: Path) -> list[Check]:
    """Comparisons across recordings and the by-lag lines: file, painter and view agree."""
    from meanap.gui.figure_canvas import FigureCanvas
    from meanap.native import output
    from meanap.native.group_paint import ComparisonPainter, LinePainter
    from meanap.pipeline.figure_output import capture_figures
    from meanap.pipeline.palette import DEFAULT_SCHEME
    from meanap.native.chart_paint import ChartPainter
    from meanap.pipeline.plotting_step4 import (
        plot_density_landscape, plot_graph_metrics_by_lag, plot_half_violin_by_x,
        plot_node_cartography_by_lag, plot_node_cartography_proportions,
        plot_node_cartography_proportions_by_age,
    )

    checks: list[Check] = []
    df_rec, df_node = _group_frame()
    counts = df_rec.copy()
    for i in range(1, 7):
        counts[f"NCpn{i}count"] = np.round(counts[f"NCpn{i}"] * counts["aN"])
    rec10 = df_rec[df_rec["Lag"] == 10]
    node10 = df_node[df_node["Lag"] == 10]

    def by_group(path):
        plot_half_violin_by_x(rec10, "Dens", "Density", "group", path, ylim=(0, None))

    def nodes_by_age(path):
        plot_half_violin_by_x(node10, "ND", "Node degree", "DIV", path, node_noun="electrode")

    def by_type(path):
        plot_half_violin_by_x(node10, "ND", "Node degree", "group", path,
                              series_col="CellType")

    def lag_lines(path):
        out = plot_graph_metrics_by_lag(df_rec, path.parent / path.stem, only="Dens",
                                        fmt=path.suffix[1:])
        if out and out[0].exists():
            out[0].replace(path)

    def roles(path):
        out = plot_node_cartography_by_lag(df_rec, path.parent / path.stem, only=10,
                                           fmt=path.suffix[1:])
        if out and out[0].exists():
            out[0].replace(path)

    def composition(plot):
        def draw(path):
            out = plot(counts, path.parent / path.stem, only=10, fmt=path.suffix[1:])
            if out and out[0].exists():
                out[0].replace(path)
        return draw

    def landscape(path):
        rng = np.random.default_rng(5)
        plot_density_landscape(rng.beta(2, 3, 400), rng.normal(size=400),
                               (1.0, 0.1, 0.6, 0.3, 0.7), path)

    for label, draw, painter_type in (
            ("comparison by group", by_group, ComparisonPainter),
            ("node comparison by age", nodes_by_age, ComparisonPainter),
            ("comparison by cell type", by_type, ComparisonPainter),
            ("metric against lag", lag_lines, LinePainter),
            ("roles by age", roles, LinePainter),
            ("role composition by group", composition(plot_node_cartography_proportions),
             ChartPainter),
            ("role composition by age", composition(plot_node_cartography_proportions_by_age),
             ChartPainter),
            ("PC/Z landscape", landscape, ChartPainter)):
        stem = label.replace(" ", "-")
        saved = tmp / f"{stem}.png"
        draw(saved)
        with capture_figures() as got:
            draw(tmp / f"{stem}-not-written.png")
        native = got[0].figure if got else None
        ok = (saved.exists() and isinstance(native, output.NativeFigure)
              and isinstance(native.painter, painter_type)
              and not (tmp / f"{stem}-not-written.png").exists())
        checks.append((f"the {label} is drawn by Qt, and captured as its scene", ok, ""))
        if not ok:
            continue
        again = tmp / f"{stem}-live.png"
        output.render_image(painter_type(native.scene),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a, b = _pixels(saved), _pixels(again)
        checks.append(("painting its scene gives the saved file's pixels",
                       a.shape == b.shape and np.array_equal(a, b), f"{a.shape} vs {b.shape}"))
        for fmt in ("svg", "pdf"):
            draw(tmp / f"{stem}.{fmt}")
        svg = (tmp / f"{stem}.svg").read_text()
        checks.append(("and it writes SVG with real text, and PDF",
                       svg.count("<text") >= 4
                       and (tmp / f"{stem}.pdf").read_bytes().startswith(b"%PDF"),
                       f"{svg.count('<text')} texts"))

        canvas = FigureCanvas()
        canvas.resize(1100, 700)
        canvas.show()
        canvas.show_figure(native)
        _wait()
        fig, scene = canvas.painter, canvas.scene
        heard: list[str] = []
        canvas.hovered.connect(heard.append)
        if label == "role composition by group":
            # The bottom of the first bar is peripheral nodes, pooled over recordings.
            panel, axes = scene.panels[0], fig.axes[0]
            canvas.point(fig.under(float(axes.x_pixel(0)), float(axes.y_pixel(0.05))))
            said = heard[-1] if heard else ""
            checks.append(("pointing at a bar names its role and how many nodes it holds",
                           said.startswith("peripheral nodes:") and " nodes" in said
                           and panel.title == "KO", repr(said)))
        if label == "comparison by group":
            titles = [p.title for p in scene.panels]
            colours = [v.colour for v in scene.panels[0].violins]
            checks.append(("a panel per group, a violin per age in the age colours",
                           titles == ["KO", "WT"] and len(colours) == 2
                           and np.allclose(colours, DEFAULT_SCHEME.ages(2)),
                           f"{titles} {colours}"))
            # The jitter is the old plotter's: one draw from rng(0) per violin, in order.
            rng = np.random.default_rng(0)
            same = all(np.array_equal(v.jitter, rng.random(len(v.values)))
                       for p in scene.panels for v in p.violins)
            checks.append(("points sit where the old plotter put them", same, ""))
            low, high = scene.ylim
            values = rec10["Dens"].to_numpy()
            checks.append(("the pinned end is pinned and the free end covers the data",
                           low == 0.0 and high > values.max(), f"{scene.ylim}"))
            violin = scene.panels[1].violins[0]
            axes = fig.axes[1]
            x = float(axes.x_pixel(violin.pos - violin.width - violin.gap
                                   + violin.jitter[2] * violin.width))
            y = float(axes.y_pixel(violin.values[2]))
            what = fig.under(x, y)
            canvas.point(what)
            checks.append(("pointing at a point names the recording and its value",
                           what == ("point", 1, 0, 2) and violin.points[2] in heard[-1]
                           and f"{violin.values[2]:.4g}" in heard[-1], str(heard[-1:])))
            xm, ym = float(axes.x_pixel(violin.pos + violin.gap + 0.02)), \
                float(axes.y_pixel(violin.mean))
            what = fig.under(xm, ym)
            canvas.point(what)
            checks.append(("pointing at the violin gives its count, mean and error",
                           what == ("violin", 1, 0) and "4 recordings" in heard[-1]
                           and f"{violin.mean:.4g}" in heard[-1], str(heard[-1:])))
            canvas.point(None)
            top = fig.axes[0]
            whole = top.ylim
            centre = top.rect.center()
            canvas._move("0", top, lambda ax_, ax, ay: ax_.zoom(
                2.0, centre.x(), centre.y(), along_x=ax, along_y=ay))
            checks.append(("zooming one panel zooms every panel's y, and never x",
                           top.ylim != whole and fig.axes[1].ylim == top.ylim
                           and top.xlim == top.home[0], f"{top.ylim}"))
            canvas.reset_view()
        elif label == "node comparison by age":
            checks.append(("by age: a panel per age, a violin per group in the group colours",
                           [p.title for p in scene.panels] == ["Age 7", "Age 14"]
                           and np.allclose([v.colour for v in scene.panels[0].violins],
                                           DEFAULT_SCHEME.groups(2))
                           and scene.noun == "electrode", ""))
            violin = scene.panels[0].violins[0]
            k = 5
            what = ("point", 0, 0, k)
            canvas.point(what)
            checks.append(("a node says which recording and electrode it is",
                           violin.points[k] in heard[-1] and ", electrode " in heard[-1],
                           str(heard[-1:])))
            canvas.click(what)
            canvas.point(None)
            recording = violin.recordings[k]
            mine = sum(int(np.sum(np.asarray(v.recordings) == recording))
                       for p in scene.panels for v in p.violins)
            checks.append(("clicking it marks that recording's every node",
                           fig._marked_recording() == recording and mine == 12,
                           f"{recording}: {mine}"))
            canvas.click(what)
            checks.append(("and clicking again lets go", canvas.pinned is None, ""))
        elif label == "comparison by cell type":
            positions = [round(v.pos, 3) for v in scene.panels[0].violins]
            checks.append(("each age splits into a violin per cell type, with a key",
                           scene.legend is not None and scene.legend[0] == "CellType"
                           and [n for n, _ in scene.legend[1]] == ["E", "I"]
                           and len(positions) == 4 and positions[0] < 1 < positions[1],
                           str(positions)))
        elif label == "metric against lag":
            series = scene.panels[0].series[0]
            want = rec10[(rec10["Grp"] == "KO") & (rec10["DIV"] == "7")]["Dens"]
            checks.append(("a panel per group and a line per age, mean ± SEM per lag",
                           [p.title for p in scene.panels] == ["KO", "WT"]
                           and [s.label for s in scene.panels[0].series] == ["7", "14"]
                           and abs(series.means[0] - want.mean()) < 1e-12
                           and abs(series.sems[0] - want.std(ddof=0) / 2.0) < 1e-12
                           and series.counts[0] == 4 and scene.ticks == ["10", "25"],
                           f"{series.means}"))
            axes = fig.axes[0]
            what = fig.under(float(axes.x_pixel(1)), float(axes.y_pixel(series.means[0])))
            canvas.point(what)
            checks.append(("pointing at a marker reads the group, age, lag, mean and n",
                           what == (0, 0, 0) and "KO, DIV 7, 10 ms lag" in heard[-1]
                           and "n = 4" in heard[-1], str(heard[-1:])))
            canvas.click(what)
            canvas.point(None)
            checks.append(("clicking an age keeps it, in every group", fig._chosen() == "7", ""))
            canvas.click(what)
        elif label == "roles by age":
            checks.append(("six roles, a panel per group, one y range for all",
                           all(len(p.series) == 6 for p in scene.panels)
                           and scene.panels[0].ylim == scene.panels[1].ylim
                           and scene.ticks == ["7", "14"], ""))
        canvas.close()

    # A metric no recording has: still drawn, saying why it is empty.
    empty = tmp / "empty.png"
    with capture_figures() as got:
        plot_half_violin_by_x(rec10, "Empty", "Nothing", "group", empty)
    scene = got[0].figure.scene if got else None
    checks.append(("a metric nobody has is drawn empty, saying how many lack it",
                   scene is not None and "16/16 recording(s)" in (scene.empty or "")
                   and not any(p.violins for p in scene.panels), str(scene and scene.empty)))
    with capture_figures() as got:
        plot_half_violin_by_x(rec10, "Partial", "Partial", "group", tmp / "partial.png")
    scene = got[0].figure.scene if got else None
    checks.append(("and one some lack says so under the figure",
                   scene is not None and "4/16 recording(s) had no values" in scene.note,
                   str(scene and scene.note)))
    return checks


def output_pixels(figure, selected) -> np.ndarray:
    """What the painter draws with *selected* selected, as pixels."""
    from meanap.native import output

    before = figure.selected
    figure.select(selected)
    image = output.render_image(figure).convertToFormat(
        output.render_image(figure).Format.Format_RGBA8888)
    figure.select(before)
    width, height = image.width(), image.height()
    data = image.constBits()
    data.setsize(image.sizeInBytes())
    return np.frombuffer(data, dtype=np.uint8).reshape(height, image.bytesPerLine())[
        :, :width * 4].copy()


def _wait(ms: int = 30) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _settle(viewer) -> None:
    for _ in range(400):
        _wait()
        if not (viewer._drawing or viewer._queued or viewer._restyle.isActive()):
            break
    _wait(60)


def _window_checks(bundle: Path) -> list[Check]:
    from meanap.gui.results_viewer import ResultsViewer
    from meanap.pipeline import hover

    checks: list[Check] = []
    viewer = ResultsViewer()
    viewer.resize(1200, 800)
    viewer.show()
    viewer.load_run(bundle)
    _settle(viewer)

    checks.append(("the run's recordings are listed", viewer.recordings.count() >= 1,
                   str(viewer.recordings.count())))
    labels = viewer.figure_labels()
    tops = [viewer._name(viewer.figures.topLevelItem(i))
            for i in range(viewer.figures.topLevelItemCount())]
    checks.append(("with their figures, under a Network heading",
                   "Network" in tops and len(labels) > 2, str(tops)))
    order = [t for t in tops if t in ("Activity", "Network")]
    checks.append(("in a tree: activity first where there is any, then network",
                   order == sorted(order) and all(" / " in label for label in labels),
                   str(tops)))
    # The checks of the spikes everything is built on come before what is built on them.
    rec = viewer._recording()
    had = {k: rec.get(k) for k in ("spike_checks", "sorting_checks", "stim_checks",
                                    "edge_checks", "stim")}
    rec["spike_checks"] = [{"name": "1_Frequencies", "label": "Spike frequencies"}]
    rec["sorting_checks"] = [{"name": "3_UnitQuality", "label": "Unit quality"}]
    rec["stim_checks"] = [{"name": "2_StimsHeatmap", "label": "Stimulating electrodes"}]
    rec["edge_checks"] = [viewer.lag.currentData()]
    rec["stim"] = [{"name": "9_FR_before_after_stimulation", "label": "FR"},
                   {"name": "12_shuffle_test_null_dist_pattern_1", "label": "Null"},
                   {"name": "16_StimNetworkGraph_10mslag", "label": "Graph"}]
    viewer._fill_figures()
    stim = next((viewer.figures.topLevelItem(i)
                 for i in range(viewer.figures.topLevelItemCount())
                 if viewer._name(viewer.figures.topLevelItem(i)) == "Stimulation"), None)
    stim_heads = ([viewer._name(stim.child(i)) for i in range(stim.childCount())]
                  if stim is not None else [])
    with_checks = [viewer._name(viewer.figures.topLevelItem(i))
                   for i in range(viewer.figures.topLevelItemCount())]
    network = next(viewer.figures.topLevelItem(i)
                   for i in range(viewer.figures.topLevelItemCount())
                   if viewer._name(viewer.figures.topLevelItem(i)) == "Network")
    edge_leaf = [network.child(i).text(0) for i in range(network.childCount())]
    rec.update(had)
    viewer._fill_figures()
    _settle(viewer)
    checks.append(("spike detection, sorting and stimulus checks come first, before activity "
                   "and network",
                   with_checks[:3] == ["Spike detection checks", "Spike sorting checks",
                                       "Stimulus detection checks"]
                   and with_checks.index("Network") > 2, str(with_checks)))
    checks.append(("the edge threshold check sits under Network when the run kept it",
                   "Edge threshold check" in edge_leaf, str(edge_leaf)))
    checks.append(("a stimulation run's figures come last, under Stimulation, by kind",
                   with_checks[-1:] == ["Stimulation"]
                   and stim_heads == ["Responses", "Shuffle test", "Stimulus networks"],
                   f"{with_checks} {stim_heads}"))
    spatial = next(b for b in viewer._branches() if viewer._name(b) == "Spatial network")
    was = spatial.isExpanded()
    viewer._on_tree_click(spatial, 0)
    folded = spatial.isExpanded() != was and spatial.text(0).startswith("▾" if not was else "▸")
    viewer._on_tree_click(spatial, 0)
    checks.append(("a heading folds and unfolds when clicked, and shows which",
                   folded and spatial.isExpanded() == was, spatial.text(0)))
    checks.append(("the first figure is drawn without being asked",
                   viewer._stack.currentWidget() is not viewer.view or viewer.view.figure is not None,
                   viewer.status.text()))
    checks.append(("and the time it took is shown",
                   viewer.status.text().startswith("Drawn in"), viewer.status.text()))

    row = "Network / Spatial network / Node degree"
    checks.append(("the node-degree network is among them", row in labels, str(labels)))
    if row not in labels:
        viewer.close()
        return checks
    viewer.select_figure(row)
    _settle(viewer)

    # A network plot is drawn by the painter that writes the pipeline's file.
    native = viewer.native
    figure = native.painter
    scene = native.scene
    checks.append(("a network plot opens drawn by Qt",
                   viewer._stack.currentWidget() is native and scene is not None, ""))
    checks.append(("with a node per node, and its edges once each",
                   scene is not None and len(scene.xy) == len(scene.names) > 0
                   and len(scene.edge_nodes) > 0 and (scene.edge_weight > 0).all()
                   and len(np.unique(np.sort(scene.edge_nodes, axis=1), axis=0))
                   == len(scene.edge_nodes),
                   "" if scene is None else f"{len(scene.xy)} nodes, {len(scene.edge_nodes)} edges"))
    checks.append(("the title and the three size samples come from the scene",
                   bool(scene.title) and "degree" in scene.size_name.lower()
                   and len(scene.size_items) == 3, f"{scene.title!r} / {scene.size_name!r}"))

    said: list[str] = []
    heard: list[str] = []
    native.picked.connect(said.append)
    native.hovered.connect(heard.append)
    at = figure.to_pixel(scene.xy[:1])[0]
    checks.append(("the node under the pointer is found",
                   figure.node_at(at[0], at[1]) == 0 and figure.node_at(2, 2) is None, ""))
    native._point(0)
    checks.append(("pointing at a node names it",
                   bool(heard) and scene.names[0] in heard[-1], str(heard[-1:])))
    native._point(None)
    checks.append(("pointing at nothing clears the read-out", heard[-1] == "", ""))
    native.click(0)
    near = native.neighbours(0)
    checks.append(("clicking a node names it and counts its connections",
                   native.selected == 0 and scene.names[0] in said[-1]
                   and f"{len(near)} connection" in said[-1]
                   and "Selected" in viewer.selection.text(), str(said[-1:])))
    lit = sum(len(g.lines) for g in figure._lit)
    plain = output_pixels(figure, None)
    chosen = output_pixels(figure, 0)
    checks.append(("selecting keeps its connections and fades the rest",
                   lit == len(near) > 0 and not np.array_equal(plain, chosen),
                   f"{lit} edges lit"))
    native.click(0)
    checks.append(("clicking it again lets go: nothing ringed, nothing faded",
                   native.selected is None and said[-1] == "" and not figure._lit
                   and np.array_equal(output_pixels(figure, None), plain)
                   and viewer.selection.text() == "", viewer.selection.text()))
    native.click(0)
    native.click(None)
    checks.append(("so does clicking empty space", native.selected is None, ""))

    from meanap.native.network_paint import NetworkPairPainter

    both = viewer.variant.findData("combined")
    if both >= 0:
        viewer.variant.setCurrentIndex(both)
        _settle(viewer)
        checks.append(("\"Both, side by side\" shows the two scales as one figure, still styleable",
                       viewer._stack.currentWidget() is native
                       and isinstance(native.painter, NetworkPairPainter)
                       and viewer.style_button.isVisible(), type(native.painter).__name__))
        viewer.variant.setCurrentIndex(viewer.variant.findData("plain"))
        _settle(viewer)
        figure, scene = native.painter, native.scene

    sizes, to_scale = figure.size_key()
    checks.append(("at the default view the size key is to scale",
                   to_scale and sizes == sorted(sizes), str(sizes)))
    centre = figure.plot_rect.center()
    figure.zoom(20.0, centre.x(), centre.y())
    checks.append(("zoomed far in, it says it no longer is", not figure.size_key()[1], ""))
    native.reset_view()
    checks.append(("and Reset view brings it back to scale",
                   figure.size_key()[1] and figure.fitted, ""))

    out = Path(tempfile.mkdtemp())
    native.names.setChecked(True)
    for suffix in ("png", "svg", "pdf"):
        native.export(str(out / f"shown.{suffix}"))
    written = {x: (out / f"shown.{x}").stat().st_size for x in ("png", "svg", "pdf")
               if (out / f"shown.{x}").exists()}
    checks.append(("the view exports as shown, to PNG, SVG and PDF",
                   len(written) == 3 and all(written.values()), str(written)))
    svg = (out / "shown.svg").read_text()
    checks.append(("the SVG is shapes and text, with no embedded picture",
                   "<image" not in svg and svg.count("<text") >= len(scene.names)
                   and svg.count("<ellipse") + svg.count("<circle") + svg.count("<path")
                   >= len(scene.xy),
                   f"{svg.count('<image')} images, {svg.count('<text')} texts"))
    native.names.setChecked(False)

    # The connectivity statistics are drawn by Qt too, by the file's painter.
    stats_row = next((label for label in labels if label.endswith("Connectivity statistics")),
                     None)
    if stats_row is not None:
        from meanap.native import output
        from meanap.native.connectivity_paint import ConnectivityPainter

        viewer.select_figure(stats_row)
        _settle(viewer)
        stats = viewer.canvas
        fig, spec = stats.painter, stats.scene
        checks.append(("connectivity statistics open drawn by Qt",
                       viewer._stack.currentWidget() is stats and spec is not None
                       and not viewer.style_button.isVisible(), ""))
        name = next(f["name"] for f in viewer._recording()["figures"][str(viewer.lag.currentData())]
                    if f["label"] == "Connectivity statistics")
        saved = viewer._service.figure(viewer._recording()["name"], viewer.lag.currentData(),
                                       name, fmt="png", overrides={}, thumbnail=False)
        again = out / "stats-live.png"
        output.render_image(ConnectivityPainter(spec),
                            output.DEFAULT_DPI / output.LOGICAL_DPI).save(str(again))
        a_px, b_px = _pixels(saved), _pixels(again)
        checks.append(("painting its scene gives the saved file's pixels, at 300 dpi",
                       a_px.shape == b_px.shape and np.array_equal(a_px, b_px)
                       and a_px.shape[1] == round(1056 * 300 / 96),
                       f"{a_px.shape} vs {b_px.shape}"))
        adj = spec.adj
        nd = fig.histograms["nd"]
        checks.append(("from the run's numbers: the matrix and what was binned",
                       int(nd.counts.sum()) == len(spec.nd)
                       and int(fig.histograms["edge_weights"].counts.sum())
                       == len(spec.edge_weights) and len(spec.names) == len(adj),
                       f"{adj.shape}, {int(nd.counts.sum())} nodes"))
        i, j = (int(v) for v in np.argwhere(adj > 0)[0])
        x, y = float(fig.matrix.x_pixel(j + 0.5)), float(fig.matrix.y_pixel(i + 0.5))
        heard: list[str] = []
        stats.hovered.connect(heard.append)
        checks.append(("the cell under the pointer is found",
                       fig.under(x, y) == ("cell", i, j) and fig.under(3, 3) is None, ""))
        stats.point(fig.under(x, y))
        names = spec.names
        checks.append(("pointing at a matrix cell names both nodes and the value",
                       bool(heard) and names[i] in heard[-1] and names[j] in heard[-1]
                       and f"{adj[i, j]:.4g}" in heard[-1], str(heard[-1:])))
        cell, values, _bar = fig.marks()
        checks.append(("and marks it on the three histograms",
                       cell == ("cell", i, j)
                       and abs(values["edge_weights"] - adj[i, j]) < 1e-12
                       and abs(values["nd"] - float(spec.nd[i])) < 1e-12 and "ns" in values, ""))
        stats.click(fig.under(x, y))
        stats.point(None)
        checks.append(("a clicked cell stays marked when the pointer leaves",
                       stats.pinned == ("cell", i, j) and fig.marks()[0] == ("cell", i, j)
                       and "Selected" in viewer.selection.text(), viewer.selection.text()))
        stats.click(("cell", i, j))
        checks.append(("and clicking it again clears every mark",
                       stats.pinned is None and fig.marks() == (None, {}, None)
                       and viewer.selection.text() == "", ""))
        b = int(nd.counts.argmax())
        bx = float(nd.axes.x_pixel((nd.edges[b] + nd.edges[b + 1]) / 2))
        by = float(nd.axes.y_pixel(0.5))
        stats.point(fig.under(bx, by))
        checks.append(("pointing at a histogram bar gives its count",
                       fig.under(bx, by) == ("bar", "nd", b)
                       and str(int(nd.counts[b])) in heard[-1] and "degree" in heard[-1].lower()
                       and len(nd.members(b)) == nd.counts[b], str(heard[-1:])))
        stats.point(None)
        home = fig.matrix.xlim
        fig.matrix.zoom(2.0, x, y)
        zoomed = fig.matrix.xlim
        fig.matrix.zoom(0.01, x, y)
        checks.append(("the matrix zooms in, and never out past the whole of it",
                       zoomed[1] - zoomed[0] < home[1] - home[0] and fig.matrix.xlim == home,
                       f"{zoomed} then {fig.matrix.xlim}"))
        for suffix in ("png", "svg", "pdf"):
            stats.export(str(out / f"stats.{suffix}"))
        sizes = {x: (out / f"stats.{x}").stat().st_size for x in ("png", "svg", "pdf")
                 if (out / f"stats.{x}").exists()}
        svg = (out / "stats.svg").read_text()
        checks.append(("it exports as shown; in SVG the text is text",
                       len(sizes) == 3 and all(sizes.values()) and svg.count("<text") > 20,
                       f"{sizes}, {svg.count('<text')} texts"))
        checks.append(("and there is one drawing of it: nothing to choose between",
                       not hasattr(viewer, "drawing"), ""))

    viewer.select_figure(row)
    _settle(viewer)

    checks.append(("styling is offered, but closed until asked for",
                   viewer.style_button.isVisible() and not viewer._right.isVisible(), ""))
    viewer.style_button.setChecked(True)
    checks.append(("and opens from its button",
                   viewer._right.isVisible() and viewer._right.width() > 150,
                   str(viewer._right.width())))

    checks.append(("the styling controls are the viewer's set",
                   len(viewer.style_panel._widgets) >= 8,
                   str(list(viewer.style_panel._widgets))))

    figure, scene = native.painter, native.scene
    centre = figure.plot_rect.center()
    figure.zoom(1.7, centre.x() + 40, centre.y())
    colormap = viewer.style_panel._widgets["colormap"]
    colormap.setCurrentIndex((colormap.currentIndex() + 1) % colormap.count())
    _settle(viewer)
    checks.append(("changing a control redraws the figure, keeping its view",
                   native.painter is not figure and native.painter.scene is not scene
                   and native.painter.scale == figure.scale
                   and native.painter.centre == figure.centre and not native.painter.fitted,
                   f"{native.painter.scale} vs {figure.scale}"))
    request = viewer._request()
    checks.append(("with only the changed control sent as an override",
                   list(request["overrides"]) == ["colormap"], str(request["overrides"])))
    viewer.style_panel.reset()
    _settle(viewer)
    checks.append(("Reset returns to the run's own styling",
                   viewer._request()["overrides"] == {}, str(viewer._request()["overrides"])))

    viewer.select_figure("Node cartography")
    _settle(viewer)
    checks.append(("a plot that is not a network has no styling to offer",
                   not viewer.style_button.isVisible() and not viewer._right.isVisible(), ""))

    # It is drawn by Qt like the rest: what is saved is what is shown.
    from meanap.gui.results_viewer import MIN_TEXT_PX
    from meanap.native.cartography_paint import CartographyPainter

    checks.append(("and it too is drawn by Qt",
                   viewer._stack.currentWidget() is viewer.canvas
                   and isinstance(viewer.canvas.painter, CartographyPainter), ""))
    saved = Path(tempfile.mkdtemp()) / "as-shown.png"
    viewer.canvas.export(str(saved))
    checks.append(("saving it writes the figure on screen",
                   saved.exists() and _pixels(saved).shape[0] > 300, ""))

    # Across recordings: the figures that compare them, in the same order.
    has_group = viewer._scope_buttons["group"].isVisibleTo(viewer)
    checks.append(("figures across recordings are offered when the run has them",
                   has_group == viewer._has_group_figures(), str(has_group)))
    if has_group:
        before = viewer.figure_title.text()
        viewer.set_scope("group")
        _settle(viewer)
        tops = [viewer._name(viewer.figures.topLevelItem(i))
                for i in range(viewer.figures.topLevelItemCount())]
        order = [t for t in tops if t in ("Activity", "Network")]
        checks.append(("they are a separate page, not mixed into a recording's",
                       viewer.scope == "group" and not viewer._recordings_card.isVisible()
                       and bool(viewer.figure_labels()), str(tops)))
        checks.append(("in the same order: activity, then network",
                       order == sorted(order) and len(order) >= 1, str(tops)))
        from meanap.native.group_paint import ComparisonPainter

        checks.append(("the first of them is drawn, by Qt",
                       viewer.status.text().startswith("Drawn in")
                       and viewer._stack.currentWidget() is viewer.canvas
                       and isinstance(viewer.canvas.painter, ComparisonPainter),
                       viewer.status.text()))
        drawn = viewer.canvas.painter
        kept = Path(tempfile.mkdtemp()) / "group.png"
        viewer.canvas.export(str(kept))
        checks.append(("and saving it writes the figure on screen", kept.exists(), ""))
        if viewer.split.count() > 1:
            viewer.split.setCurrentIndex(1)
            _settle(viewer)
            shown = viewer.canvas.painter
            checks.append(("and redrawn with ages as its panels instead of groups",
                           shown is not drawn and shown.scene.xlabel == "Group"
                           and drawn.scene.xlabel == "Age"
                           and viewer._request()["split"] == viewer.split.itemData(1),
                           f"{shown.scene.xlabel}"))
        viewer.set_scope("recording")
        _settle(viewer)
        checks.append(("coming back returns to the figure that was open",
                       viewer.scope == "recording" and viewer.figure_title.text() == before
                       and viewer._recordings_card.isVisible(), viewer.figure_title.text()))
    checks.append(("cell tracking is not offered on a run without it",
                   not viewer._scope_buttons["tracking"].isVisibleTo(viewer), ""))

    viewer.close()
    checks.append(("closing the window closes the run", viewer._service is None, ""))
    return checks


def _finding_checks(bundle: Path, tmp: Path) -> list[Check]:
    """Filtering the recordings, one figure across DIVs, previews from a comparison."""
    from meanap.gui.results_viewer import _RECORDING_ROLE, ResultsViewer, _cultures

    checks: list[Check] = []
    recs = [{"name": n, "div": d} for n, d in (
        ("MPT200114_2A_DIV14", 14), ("MPT200114_2A_DIV21", 21), ("MPT200114_3B_DIV14", 14),
        ("OPME240517_17_20240602_P1_pup2D_WT_DIV16 David Oluigbo", 16),
        ("OPME240517_17_20240608_P1_pup2D_WT_DIV22 David Oluigbo", 22))]
    cultures = _cultures(recs)
    checks.append(("a culture is its recordings at other DIVs, youngest first",
                   cultures.get(0) == [0, 1] and cultures.get(1) == [0, 1], str(cultures)))
    checks.append(("a culture recorded once is not offered across DIVs", 2 not in cultures, ""))
    checks.append(("a note after the DIV token (an exporter's name) does not hide it",
                   cultures.get(3) == [3, 4], str(cultures)))

    viewer = ResultsViewer()
    viewer.resize(1300, 850)
    viewer.show()
    viewer.load_run(bundle)
    _settle(viewer)
    listed = lambda: [viewer.recordings.item(i) for i in range(viewer.recordings.count())]  # noqa: E731
    names = lambda: [it.text().split("\n")[0] for it in listed()  # noqa: E731
                     if it.data(_RECORDING_ROLE) is not None]
    checks.append(("every group is offered as a filter",
                   [viewer.rec_group.itemText(i) for i in range(viewer.rec_group.count())]
                   == ["All groups", "KO", "WT"], ""))
    viewer.rec_group.setCurrentIndex(viewer.rec_group.findData("KO"))
    _settle(viewer)
    checks.append(("filtering by group lists that group only, and follows to it",
                   names() == ["recB"] and viewer._recording()["name"] == "recB"
                   and viewer.rec_count.text() == "1 of 2", f"{names()} {viewer.rec_count.text()}"))
    viewer.rec_group.setCurrentIndex(0)
    viewer.rec_search.setText("reca")
    _settle(viewer)
    checks.append(("the name filter ignores case", names() == ["recA"], str(names())))
    viewer.rec_search.clear()
    viewer.rec_by.setCurrentIndex(viewer.rec_by.findData("group"))
    _settle(viewer)
    heads = [it.text() for it in listed() if it.data(_RECORDING_ROLE) is None]
    checks.append(("headings per group, which cannot be chosen",
                   heads == ["KO", "WT"] and all(
                       not it.flags() & it.flags().ItemIsSelectable
                       for it in listed() if it.data(_RECORDING_ROLE) is None), str(heads)))
    viewer.rec_by.setCurrentIndex(0)
    _settle(viewer)

    # Across DIVs: the fixture's two recordings stand in for one culture.
    viewer._manifest["recordings"][1]["div"] = 28.0
    viewer._siblings = {0: [0, 1], 1: [0, 1]}
    viewer.select_recording("recA")
    _settle(viewer)
    viewer.select_figure("Node degree")
    _settle(viewer)
    checks.append(("“Across DIVs” is offered for a culture recorded at several",
                   viewer.across_divs.isVisibleTo(viewer)
                   and viewer.across_divs.text() == "Across DIVs (2)", viewer.across_divs.text()))
    viewer.across_divs.setChecked(True)
    _settle(viewer)
    cells = viewer.montage.canvases
    checks.append(("which draws the figure once per DIV, side by side",
                   viewer._stack.currentWidget() is viewer.montage and len(cells) == 2
                   and all(getattr(c, "painter", None) is not None for c in cells),
                   str([type(c).__name__ for c in cells])))
    if len(cells) == 2 and hasattr(cells[0], "select_name"):
        cells[0].select(0)
        name = str(cells[0].painter.network.names[0])
        other = cells[1].painter.network.names
        followed = cells[1].selected is not None and str(other[cells[1].selected]) == name
        if viewer._manifest.get("mode") == "catnap":
            # Imaged cells are numbered afresh each session: cell 3 at one
            # DIV is not cell 3 at the next, so nothing follows.
            checks.append(("an imaged cell chosen in one is not “followed” in the others",
                           cells[1].selected is None, name))
        else:
            checks.append(("an electrode chosen in one is chosen in the others",
                           followed or name not in [str(n) for n in other], name))
    out = tmp / "across.svg"
    viewer.montage.export(str(out))
    checks.append(("and saves as one figure", out.exists() and out.stat().st_size > 1000, ""))
    viewer.select_recording("recB")
    _settle(viewer)
    checks.append(("it stays on for the next recording of the culture",
                   viewer._stack.currentWidget() is viewer.montage, ""))
    viewer.across_divs.setChecked(False)
    _settle(viewer)
    viewer._siblings = {}
    viewer.select_recording("recA")
    _settle(viewer)
    checks.append(("and is not offered where there are no other DIVs",
                   not viewer.across_divs.isVisibleTo(viewer)
                   and viewer._stack.currentWidget() is not viewer.montage, ""))

    # A point across recordings previews that recording, and opens it.
    viewer.set_scope("group")
    _settle(viewer)
    comparison = next((label for label in viewer.figure_labels()
                       if "Network" in label and "Recording" in label), None)
    if comparison:
        viewer.select_figure(comparison)
    _settle(viewer)
    painter = viewer.canvas.painter
    point = ("point", 0, 0, 0)
    pointed = painter.recording_of(point) if painter is not None and hasattr(
        painter.scene, "panels") else None
    checks.append(("a comparison's point names its recording", pointed in ("recA", "recB"),
                   f"{comparison} {pointed}"))
    if pointed:
        viewer.canvas.point(point)
        for _ in range(200):
            _wait()
            if not viewer._preview_busy:
                break
        pic = viewer.preview.picture.pixmap()
        checks.append(("pointing at it shows a preview of that recording",
                       viewer.preview.isVisible() and viewer.preview.name == pointed
                       and pic is not None and not pic.isNull(), viewer.preview.picture.text()))
        viewer.canvas.click(point)
        viewer.canvas.point(None)
        _wait(PREVIEW_WAIT_MS)
        checks.append(("which stays while the point is pinned", viewer.preview.isVisible(), ""))
        viewer.preview.opened.emit(viewer.preview.name)
        _settle(viewer)
        checks.append(("clicking it opens the recording, at the figure previewed",
                       viewer.scope == "recording" and viewer._recording()["name"] == pointed
                       and viewer.figures.currentItem() is not None
                       and viewer.figures.currentItem().data(0, 0x0100)["kind"]
                       in ("network", "activity") and not viewer.preview.isVisible(),
                       f"{viewer.scope} {viewer.figure_title.text()}"))
    viewer.close()
    return checks


def _scale_checks(bundle: Path) -> list[Check]:
    """The activity raster and heatmaps offer the network plots' scale choice."""
    from meanap.native.activity_paint import HeatmapPainter, RasterPainter
    from meanap.native.output import NativeFigure, render_image
    from meanap.native.scene import heatmap_scene, raster_scene
    from meanap.pipeline.render import activity_figure_variants, pick_scale
    from meanap.viewer.server import ViewerService

    checks: list[Check] = []
    rng = np.random.default_rng(3)
    heat = heatmap_scene(rng.random(60) * 10, list(range(11, 71)), "rec", "mean firing rate (Hz)",
                         channel_layout="MCS60", batch_max=25.0)
    raster = raster_scene({ch: np.sort(rng.random(50) * 60) for ch in range(8)}, 60.0,
                          title="rec", spike_freq_max=12.0)
    for label, scene, painter in (("heatmap", heat, HeatmapPainter), ("raster", raster,
                                                                      RasterPainter)):
        whole = NativeFigure(label, scene, painter(scene))
        own, batch, both = (pick_scale(whole, v) for v in ("plain", "scaled", "combined"))
        checks.append((f"{label}: “this recording's scale” keeps the recording's panel only",
                       own.scene.panels == [scene.panels[0]], str(own.scene.panels)))
        checks.append((f"{label}: “whole batch's scale” keeps the dataset's panel only",
                       batch.scene.panels == [scene.panels[1]], str(batch.scene.panels)))
        checks.append((f"{label}: “both” is the figure as the pipeline saves it",
                       both is whole, ""))
        image = render_image(own.painter)
        checks.append((f"{label}: one panel draws on its own",
                       image.width() > 100 and own.scene is not scene
                       and len(scene.panels) == 2, ""))
    service = ViewerService(bundle)
    rec = service.manifest()["recordings"][0]
    checks.append(("a CAT-NAP raster has one panel, so offers no choice",
                   all(f["variants"] == ["plain"] for f in rec["activity"])
                   and activity_figure_variants(service.ctx, rec["name"], "3_Raster") == ["plain"],
                   str([f["variants"] for f in rec["activity"]])))
    service.close()
    return checks


def _params_and_export_checks(bundle: Path, tmp: Path) -> list[Check]:
    """The run's settings on a page of their own, and every figure drawn out."""
    from meanap.gui.results_viewer import ResultsViewer
    from meanap.params import load_params

    checks: list[Check] = []
    viewer = ResultsViewer()
    viewer.resize(1300, 850)
    viewer.show()
    viewer.load_run(bundle)
    _settle(viewer)
    checks.append(("a bundle offers its settings, and exporting its figures",
                   viewer._scope_buttons["params"].isVisibleTo(viewer)
                   and viewer.export_button.isVisibleTo(viewer), ""))
    viewer.set_scope("params")
    _wait(60)
    page = viewer.params_view
    summary = viewer._manifest["params"]
    changed = summary["changed"]
    shown = lambda: [page.table.item(r, 0).text() for r in range(page.table.rowCount())  # noqa: E731
                     if page.table.item(r, 1) is not None]
    checks.append(("the Parameters page lists what the run changed",
                   viewer._pages.currentWidget() is page and len(shown()) == changed
                   and changed > 0, f"{len(shown())} of {changed}"))
    checks.append(("and says which version made the run",
                   page.made_with.text().startswith(("Made with", "Made before")),
                   page.made_with.text()))
    page.changed_only.setChecked(False)
    _wait(30)
    checks.append(("every setting is a click away", len(shown()) == summary["total"],
                   f"{len(shown())} of {summary['total']}"))
    page.search.setText("lag")
    _wait(30)
    checks.append(("and can be searched by name",
                   shown() and all("lag" in n.lower() or "lag" in page.table.item(
                       r, 1).text().lower() for r, n in enumerate(shown())), str(shown())))
    page.search.clear()
    saved = page.save(tmp / "saved_params.json")
    loaded, unknown = load_params(saved)
    checks.append(("the settings save as a params file MEA-NAP loads back",
                   loaded == viewer._service.run_params() and not unknown, str(unknown)))
    viewer.set_scope("recording")
    _settle(viewer)
    checks.append(("and the figures are where they were left",
                   viewer._pages.currentIndex() == 0 and viewer.figures.currentItem() is not None,
                   ""))

    dest = tmp / "exported"
    started = viewer.export("png", dest)
    checks.append(("exporting starts in the background, and only once",
                   started and viewer.exporting and not viewer.export("png", dest), ""))
    for _ in range(3000):
        _wait(100)
        if not viewer.exporting:
            break
    result = getattr(viewer, "last_export", None)
    pngs = list(dest.rglob("*.png"))
    checks.append(("it draws the bundle's figures into a folder, with a report",
                   result is not None and result.figures > 0 and len(pngs) >= result.figures
                   and (dest / "report.html").exists(),
                   f"{result and result.figures} figures, {len(pngs)} png"))
    checks.append(("and says where, as a link",
                   "href" in viewer.export_status.text() and dest.name in viewer.export_status.text()
                   and viewer.export_button.isEnabled(), viewer.export_status.text()))
    viewer.export("svg", tmp / "stopped")
    viewer.cancel_export()
    for _ in range(600):
        _wait(50)
        if not viewer.exporting:
            break
    checks.append(("an export can be stopped",
                   not viewer.exporting and "stopped" in viewer.export_status.text().lower()
                   and viewer.export_button.isEnabled(), viewer.export_status.text()))
    viewer.close()
    return checks


#: Longer than the preview card's grace period.
PREVIEW_WAIT_MS = 900


def main() -> int:
    app = QApplication.instance() or QApplication([])  # noqa: F841
    total_pass = total = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bundle = _run(tmp, "Express", express=True).with_suffix(BUNDLE_SUFFIX)
        for title, checks in (
            ("A. Live figures", _live_checks(bundle, tmp)),
            ("C. Activity figures", _activity_checks(tmp)),
            ("D. Half-violins and circular networks", _violin_and_circular_checks(tmp)),
            ("E. Two-panel networks", _pair_checks(tmp)),
            ("F. Spike detection checks", _spike_check_checks(tmp)),
            ("G. Bursts, cartography and CAT-NAP rasters", _remaining_checks(tmp)),
            ("H. Comparisons across recordings", _group_checks(tmp)),
            ("B. The window", _window_checks(bundle)),
            ("I. Finding and comparing recordings", _finding_checks(bundle, tmp)),
            ("J. Choosing an activity figure's scale", _scale_checks(bundle)),
            ("K. The run's settings, and exporting its figures",
             _params_and_export_checks(bundle, tmp)),
        ):
            n_pass, n = _report(title, checks)
            total_pass += n_pass
            total += n
    print(f"\n{total_pass}/{total} checks passed")
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
