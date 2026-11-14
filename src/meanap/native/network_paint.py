"""The spatial network plot, drawn with ``QPainter``.

One :class:`NetworkPainter` draws one :class:`~meanap.native.scene.NetworkScene`
— title, network, legend — into a box of logical pixels. The pipeline calls it
to write the file; the application's canvas calls the same ``paint`` on every
repaint, after setting what an interactive view adds (where it is zoomed to,
which node is selected, whether names are shown).

Sizes: node diameters and positions are in the scene's units and scale with the
view; line widths and text are in logical pixels and do not, so text is the
same size however far in the view is zoomed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QFontMetricsF, QImage, QLinearGradient, QPainter, QPen, QPolygonF, QTransform,
)

from meanap.native.output import figure_font
from meanap.native.scene import DEFAULT_NODE_COLOUR, NetworkScene

__all__ = ["NetworkPainter", "NetworkPairPainter", "NetworkGridScene", "NetworkGridPainter",
           "STANDARD_SIZE", "SELECTED", "INK", "GROUND"]

#: The figure the pipeline saves, in logical pixels (10 × 7.9 inches).
STANDARD_SIZE = (960, 760)
PX_PER_POINT = 96 / 72
GROUND = QColor("#ffffff")
INK = QColor("#16181d")
MUTED = QColor("#6b7280")
SELECTED = QColor("#d62728")

MARGIN = 14
TITLE_H = 34
KEY_W = 196
#: Edges are grouped into this many widths: one ``drawLines`` per group.
EDGE_GROUPS = 16
#: Qt draws a wide smoothed line some forty times slower than an unsmoothed one
#: or a hairline, and an imaging field can have 150 000 edges. So only this
#: many edges — the strongest — are drawn at their width, the rest as
#: hairlines in their own grey...
WIDE_EDGES = 1000
#: ...and past this many hairlines they are never smoothed, and sit out
#: altogether while the view is moving or a node is selected.
MANY_EDGES = 20000
#: Past this many edges in all, smoothing is left off while the view moves.
SMOOTH_ALWAYS = 300
#: A curved hairline is drawn through every this-many-th point of its curve.
ARC_THIN_STEP = 4
#: ...and when the hairlines are so many that they are a haze, every this-many-th.
ARC_HAZE_STEP = 8
#: With a node selected, what is not its connections fades to this.
FADED = 0.13
#: The largest node sample the size key draws at true size.
KEY_SAMPLE_PX = 112
#: Above this many nodes, names are not drawn — they would be a smear.
MAX_LABELS = 400


def _grey(value: float, alpha: float = 1.0) -> QColor:
    v = float(np.clip(value, 0, 1))
    return QColor.fromRgbF(v, v, v, alpha)


def _rgba(colour, alpha: float = 1.0) -> QColor:
    c = [float(np.clip(v, 0, 1)) for v in colour]
    return QColor.fromRgbF(c[0], c[1], c[2], (c[3] if len(c) > 3 else 1.0) * alpha)


def _pen(colour: QColor, width_px: float, *, round_cap: bool = False, dash=None) -> QPen:
    pen = QPen(colour, max(float(width_px), 0.1))
    pen.setCosmetic(True)               # a width in pixels, whatever the zoom
    if round_cap:
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    if dash:
        pen.setDashPattern([max(float(d), 0.1) for d in dash])
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen


def _dashes(style, width_pt: float):
    """A matplotlib dash pattern (points) as Qt's (multiples of the pen width)."""
    if isinstance(style, str) or style is None:
        return None
    pattern = style[1] if len(style) == 2 and not np.isscalar(style[1]) else style
    width = max(width_pt, 0.25)
    return [float(v) / width for v in pattern]


class _EdgeGroup:
    """Edges that share a pen."""

    def __init__(self, lines: list[QLineF], width_px: float, grey: float, thin: bool):
        self.lines, self.width_px, self.grey, self.thin = lines, width_px, grey, thin


class NetworkPainter:
    """Draws one network scene. Set the view attributes, then :meth:`paint`."""

    def __init__(self, scene: NetworkScene, size: tuple[float, float] = STANDARD_SIZE):
        self.scene = scene
        self.size = (float(size[0]), float(size[1]))
        #: Interactive state; a saved figure leaves all of it as it starts.
        self.selected: int | None = None
        self.hovered: int | None = None
        self.names = False
        #: Draw for speed, not finish: the view is being moved.
        self.moving = False
        #: Draw the nodes, edges and legend. Off, only the backdrop is drawn —
        #: at full strength — in exactly the view the network would have.
        self.show_network = True
        #: The title band and its text, and whether there is a key beside the
        #: network: a grid of panels gives its titles more room and has one key.
        self.title_h = TITLE_H
        self.title_size = 15
        self.key = True
        self._lit: list[_EdgeGroup] = []
        self._background: QImage | None = None
        #: Legend headings as last painted, and what each is about.
        self._info_boxes: list[tuple[QRectF, str]] = []

        widths = scene.edge_width
        count = len(widths)
        self._bins = np.zeros(count, dtype=int)
        if count:
            low, high = float(widths.min()), float(widths.max())
            if high > low:
                self._bins = np.minimum(
                    ((widths - low) / (high - low) * EDGE_GROUPS).astype(int), EDGE_GROUPS - 1)
        wide = np.ones(count, dtype=bool)
        if count > WIDE_EDGES:
            wide[np.argsort(scene.edge_weight, kind="stable")[:-WIDE_EDGES]] = False
        self._segments = scene.segments
        self.thin_count = int((~wide).sum())
        self._groups = self._edge_groups(~wide, thin=True) + self._edge_groups(wide)
        self.fit()

    # ── geometry ─────────────────────────────────────────────────────────────

    @property
    def network(self) -> NetworkScene:
        """The network this draws (a pair of panels has one too)."""
        return self.scene

    @property
    def plot_rect(self) -> QRectF:
        width, height = self.size
        key = KEY_W if self.key else 0
        return QRectF(MARGIN, self.title_h + MARGIN / 2, width - 2 * MARGIN - key,
                      height - self.title_h - 1.5 * MARGIN)

    def fit(self) -> None:
        """Show the whole network: the view a saved figure has."""
        scene, plot = self.scene, self.plot_rect
        x0, x1, y0, y1 = scene.extent
        pad = (float(scene.diameter.max()) / 2 if len(scene.diameter) else 0.0) + 0.3
        if scene.cell_types is not None:
            pad += 0.2
        span_x, span_y = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
        self.centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.scale = 0.97 * min(plot.width() / max(span_x, 1e-9),
                                plot.height() / max(span_y, 1e-9))
        self.fitted = True

    def resize(self, size: tuple[float, float]) -> None:
        self.size = (float(size[0]), float(size[1]))
        if self.fitted:
            self.fit()

    def to_pixel(self, xy) -> np.ndarray:
        xy = np.asarray(xy, dtype=float)
        centre = self.plot_rect.center()
        return np.column_stack([
            centre.x() + (xy[..., 0] - self.centre[0]) * self.scale,
            centre.y() - (xy[..., 1] - self.centre[1]) * self.scale])

    def to_data(self, x: float, y: float) -> tuple[float, float]:
        centre = self.plot_rect.center()
        return (self.centre[0] + (x - centre.x()) / self.scale,
                self.centre[1] - (y - centre.y()) / self.scale)

    def zoom(self, factor: float, x: float, y: float) -> None:
        """Magnify by *factor*, keeping the point under pixel (x, y) where it is."""
        before = self.to_data(x, y)
        self.scale = float(np.clip(self.scale * factor, 1e-6, 1e9))
        after = self.to_data(x, y)
        self.centre = (self.centre[0] + before[0] - after[0],
                       self.centre[1] + before[1] - after[1])
        self.fitted = False

    def pan(self, dx: float, dy: float) -> None:
        self.centre = (self.centre[0] - dx / self.scale, self.centre[1] + dy / self.scale)
        self.fitted = False

    def _paint_markers(self, painter: QPainter) -> None:
        """The scene's markers, a fixed size however far the view is zoomed."""
        if not self.scene.markers:
            return
        painter.save()
        painter.setClipRect(self.plot_rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for marker in self.scene.markers:
            (x, y), = self.to_pixel(np.array([marker["xy"]], dtype=float)).tolist()
            r = float(marker.get("size", 12)) * PX_PER_POINT / 2
            colour = QColor(marker.get("colour", "#8a8f98"))
            if marker.get("shape") == "star":
                angle = np.pi / 2 + np.arange(10) * np.pi / 5
                radius = np.where(np.arange(10) % 2, r * 0.42, r)
                points = QPolygonF([QPointF(x + a * np.cos(t), y - a * np.sin(t))
                                    for a, t in zip(radius, angle)])
                painter.setPen(_pen(GROUND, 1.2))
                painter.setBrush(colour)
                painter.drawPolygon(points)
            else:
                painter.setPen(_pen(colour, 1.5))
                painter.drawLine(QPointF(x - r, y - r), QPointF(x + r, y + r))
                painter.drawLine(QPointF(x - r, y + r), QPointF(x + r, y - r))
        painter.restore()

    def marker_at(self, x: float, y: float) -> dict | None:
        """The marker under pixel (x, y), if any."""
        for marker in self.scene.markers:
            (mx, my), = self.to_pixel(np.array([marker["xy"]], dtype=float)).tolist()
            if np.hypot(mx - x, my - y) <= float(marker.get("size", 12)) * PX_PER_POINT / 2 + 2:
                return marker
        return None

    def node_at(self, x: float, y: float) -> int | None:
        """The node under pixel (x, y): the nearest whose disc holds the point."""
        scene = self.scene
        if not len(scene.xy) or not self.plot_rect.contains(QPointF(x, y)):
            return None
        at = np.asarray(self.to_data(x, y))
        distance = np.hypot(*(scene.xy - at).T)
        reach = np.maximum(scene.diameter / 2, 4.0 / self.scale)
        inside = np.flatnonzero(distance <= reach)
        return int(inside[np.argmin(distance[inside])]) if len(inside) else None

    def select(self, node: int | None) -> None:
        self.selected = node
        self._lit = []
        if node is not None:
            touching = (self.scene.edge_nodes == node).any(axis=1)
            self._lit = self._edge_groups(touching)

    def describe(self, node: int) -> str:
        scene = self.scene
        return f"{scene.noun.capitalize()} {scene.names[node]}\n{scene.text[node]}"

    def size_key(self) -> tuple[list[float], bool]:
        """Sample diameters in pixels, and whether they are to scale.

        To scale while the largest fits the key; zoomed further in the samples
        shrink together, keeping their ratios, and the key says so.
        """
        true = [d * self.scale for _, d in self.scene.size_items]
        largest = max(true, default=0.0)
        if largest <= KEY_SAMPLE_PX:
            return [max(d, 2.0) for d in true], True
        return [max(d * KEY_SAMPLE_PX / largest, 2.0) for d in true], False

    def _edge_groups(self, pick: np.ndarray, *, thin: bool = False) -> list[_EdgeGroup]:
        scene, groups = self.scene, []
        if not pick.any():
            return groups
        for b in np.unique(self._bins[pick]):
            members = pick & (self._bins == b)
            if scene.edge_arcs is None:
                lines = [QLineF(x0, y0, x1, y1)
                         for (x0, y0), (x1, y1) in self._segments[members].tolist()]
            else:
                # A curve is its points joined up; a hairline needs fewer of them.
                step = 1 if not thin else (ARC_HAZE_STEP if self.thin_count > MANY_EDGES
                                           else ARC_THIN_STEP)
                arcs = scene.edge_arcs[members][:, ::step]
                joined = np.concatenate([arcs[:, :-1], arcs[:, 1:]], axis=2).reshape(-1, 4)
                lines = [QLineF(x0, y0, x1, y1) for x0, y0, x1, y1 in joined.tolist()]
            width = max(float(scene.edge_width[members].mean()) * PX_PER_POINT, 0.6)
            groups.append(_EdgeGroup(lines, 1.0 if thin else width,
                                     float(scene.edge_grey[members].mean()), thin))
        return groups

    def info_at(self, x: float, y: float) -> str | None:
        """What part of the figure (x, y) is on, for a card about it:
        "title", or a legend heading's "size", "colour", "category", "edges"."""
        if 4 <= y <= 4 + self.title_h and MARGIN <= x <= self.size[0] - MARGIN:
            return "title"
        for box, role in self._info_boxes:
            if box.adjusted(-4, -3, 4, 3).contains(QPointF(x, y)):
                return role
        return None

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        width, height = self.size
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        painter.setPen(INK)
        painter.setFont(figure_font(self.title_size))
        painter.drawText(QRectF(MARGIN, 4, width - 2 * MARGIN, self.title_h),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         self.scene.title)
        self._paint_network(painter)
        if self.show_network:
            self._paint_markers(painter)
            if self.key:
                self._paint_key(painter)
        painter.restore()

    def _paint_network(self, painter: QPainter) -> None:
        scene, plot = self.scene, self.plot_rect
        painter.save()
        painter.setClipRect(plot)
        centre = plot.center()
        to_pixels = QTransform(self.scale, 0, 0, -self.scale,
                               centre.x() - self.centre[0] * self.scale,
                               centre.y() + self.centre[1] * self.scale)
        painter.setTransform(to_pixels, True)

        if scene.background is not None:
            self._paint_background(painter)
        if not self.show_network:
            painter.restore()
            return

        chosen = self.selected
        many = len(scene.edge_nodes) > SMOOTH_ALWAYS
        hazy = self.thin_count > MANY_EDGES
        for group in self._groups:
            if group.thin and hazy and (self.moving or chosen is not None):
                continue
            smooth = not ((self.moving and many) or (group.thin and hazy))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, smooth)
            painter.setPen(_pen(_grey(group.grey, FADED if chosen is not None else 1.0),
                                group.width_px, round_cap=not group.thin))
            painter.drawLines(group.lines)
        for group in self._lit:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, not self.moving)
            painter.setPen(_pen(_grey(group.grey), group.width_px, round_cap=True))
            painter.drawLines(group.lines)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        keep = None
        if chosen is not None:
            keep = np.zeros(len(scene.xy), dtype=bool)
            keep[scene.neighbours(chosen)] = True
            keep[chosen] = True
        outline = _pen(GROUND, 1.0)
        for i, ((x, y), d, colour) in enumerate(zip(scene.xy.tolist(), scene.diameter.tolist(),
                                                    scene.colour)):
            alpha = 1.0 if keep is None or keep[i] else FADED * 2
            painter.setPen(outline)
            painter.setBrush(_rgba(colour, alpha))
            painter.drawEllipse(QPointF(x, y), d / 2, d / 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if scene.cell_types is not None:
            self._paint_rings(painter, keep)
        for node, colour in ((self.hovered, SELECTED), (chosen, SELECTED)):
            if node is not None and node < len(scene.xy):
                (x, y), d = scene.xy[node], float(scene.diameter[node])
                r = d / 2 if node != chosen else d * 0.625 + 0.075
                painter.setPen(_pen(colour, 2.5))
                painter.drawEllipse(QPointF(float(x), float(y)), r, r)
        painter.restore()

        if self.names and len(scene.xy) <= MAX_LABELS:
            painter.save()
            painter.setClipRect(plot)
            painter.setPen(INK)
            font = figure_font(11)
            painter.setFont(font)
            line = QFontMetricsF(font).height()
            at = self.to_pixel(scene.xy)
            for (x, y), name, d in zip(at.tolist(), scene.names, scene.diameter.tolist()):
                top = y - d * self.scale / 2 - line - 1
                painter.drawText(QRectF(x - 60, top, 120, line),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                                 name)
            painter.restore()

    def _paint_background(self, painter: QPainter) -> None:
        image, (x0, x1, y0, y1) = self.scene.background
        if self._background is None:
            pixels = np.asarray(image, dtype=float)
            finite = pixels[np.isfinite(pixels)]
            if not finite.size:
                return
            low, high = np.percentile(finite, [1, 99])
            if high <= low:
                low, high = float(finite.min()), float(finite.max()) or 1.0
            grey = np.clip((np.nan_to_num(pixels, nan=low) - low) / max(high - low, 1e-12), 0, 1)
            data = np.ascontiguousarray((grey * 255).astype(np.uint8))
            self._bg_data = data            # the QImage does not own its pixels
            self._background = QImage(data.data, data.shape[1], data.shape[0],
                                      data.shape[1], QImage.Format.Format_Grayscale8)
        painter.save()
        painter.setOpacity(0.85 if self.show_network else 1.0)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Row 0 of the image is the bottom of the field, and y runs upward here.
        painter.drawImage(QRectF(x0, y0, x1 - x0, y1 - y0), self._background)
        painter.restore()

    def _paint_rings(self, painter: QPainter, keep) -> None:
        from meanap.network_plot import _ring_radii

        scene = self.scene
        count = scene.cell_types.shape[1]
        radii = _ring_radii(count)
        for i, ((x, y), d) in enumerate(zip(scene.xy.tolist(), scene.diameter.tolist())):
            fade = 1.0 if keep is None or keep[i] else FADED * 2
            rel = float(np.clip(d / max(scene.node_size_scale, 1e-9), 0.3, 1.0))
            centre = QPointF(x, y)
            for k in range(count):
                r = radii[k] * d / 2
                style = scene.cell_type_styles[k % len(scene.cell_type_styles)]
                if scene.cell_types[i, k] == 1:
                    painter.setPen(_pen(QColor.fromRgbF(0, 0, 0, 0.55 * fade),
                                        2.2 * rel * PX_PER_POINT))
                    painter.drawEllipse(centre, r, r)
                    painter.setPen(_pen(QColor.fromRgbF(1, 1, 1, fade),
                                        1.1 * rel * PX_PER_POINT,
                                        dash=_dashes(style, 1.1 * rel)))
                    painter.drawEllipse(centre, r, r)
                else:
                    painter.setPen(_pen(QColor.fromRgbF(1, 1, 1, 0.18 * fade),
                                        0.5 * rel * PX_PER_POINT,
                                        dash=_dashes(style, 0.5 * rel)))
                    painter.drawEllipse(centre, r, r)

    def _paint_key(self, painter: QPainter) -> None:
        scene = self.scene
        width, _height = self.size
        left = width - MARGIN - KEY_W + 10
        right = width - MARGIN
        text_font, head_font = figure_font(12), figure_font(12, bold=True)
        line = QFontMetricsF(text_font).height()
        y = self.title_h + MARGIN / 2 + 4

        self._info_boxes = []

        def heading(text: str, role: str | None = None) -> None:
            nonlocal y
            painter.setFont(head_font)
            painter.setPen(INK)
            box = painter.boundingRect(
                QRectF(left, y, right - left, 200),
                int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), text)
            if role is not None:
                self._info_boxes.append((QRectF(box), role))
            painter.drawText(box, int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                             text)
            y += box.height() + 6
            painter.setFont(text_font)

        def note(text: str) -> None:
            nonlocal y
            painter.setFont(figure_font(11))
            painter.setPen(MUTED)
            flags = int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
            box = painter.boundingRect(QRectF(left, y, right - left, 200), flags, text)
            painter.drawText(box, flags, text)
            y += box.height() + 4
            painter.setFont(text_font)

        # Where colour is a category, shown first: it is what the plot is of.
        if scene.category_key is not None:
            heading(_title(f"Node colour: {scene.category_key['name']}"), "category")
            for label, rgb in scene.category_key["items"]:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(_rgba(rgb))
                painter.drawEllipse(QPointF(left + 14, y + line / 2), 7, 7)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(INK)
                painter.drawText(QRectF(left + 30, y, right - left - 30, line),
                                 Qt.AlignmentFlag.AlignVCenter, str(label))
                y += line + 5
            y += 8

        # Node size: samples at the size nodes are on screen now.
        sizes, to_scale = self.size_key()
        if scene.size_items:
            heading(_title(f"Node size: {scene.size_name}"), "size")
        column = max(max(sizes, default=0.0), 24.0)
        for (label, _), d in zip(scene.size_items, sizes):
            row = max(d, line)
            # Samples in the plain node colour — or, where colour means a
            # category, in outline, so that a sample is not read as one.
            if scene.category_key is not None:
                painter.setPen(QPen(INK, 1))
                painter.setBrush(GROUND)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(_rgba(DEFAULT_NODE_COLOUR))
            painter.drawEllipse(QPointF(left + 4 + column / 2, y + row / 2), d / 2, d / 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(INK)
            painter.drawText(QRectF(left + column + 14, y, right - left - column - 14, row),
                             Qt.AlignmentFlag.AlignVCenter, label)
            y += row + 6
        if scene.size_items and not to_scale:
            note("not to scale at this zoom")
        if scene.size_items:
            y += 8

        heading("Edge weight", "edges")
        for label, width_pt, grey in scene.edge_items:
            painter.setPen(_pen(_grey(grey), max(width_pt * PX_PER_POINT, 1.0), round_cap=True))
            painter.drawLine(QPointF(left + 8, y + line / 2), QPointF(left + 52, y + line / 2))
            painter.setPen(INK)
            painter.drawText(QRectF(left + 66, y, right - left - 66, line),
                             Qt.AlignmentFlag.AlignVCenter, label)
            y += line + 6
        if self.thin_count:
            note(f"{len(scene.edge_nodes):,} edges. The {WIDE_EDGES:,} strongest are "
                 "drawn at their width, the rest as hairlines.")
        y += 8

        key = scene.colour_key
        if key is not None:
            import matplotlib

            heading(_title(f"Node colour: {key['name']}"), "colour")
            bar = QRectF(left + 8, y + 4, 22, 138)
            cmap = matplotlib.colormaps[key["colormap"]]
            gradient = QLinearGradient(bar.bottomLeft(), bar.topLeft())
            for i in range(32):
                gradient.setColorAt(i / 31, _rgba(cmap(i / 31)))
            painter.fillRect(bar, gradient)
            painter.setPen(INK)
            painter.drawText(QRectF(bar.right() + 10, bar.top() - 2, 120, line),
                             Qt.AlignmentFlag.AlignVCenter, f"{key['max']:.3g}")
            painter.drawText(QRectF(bar.right() + 10, bar.bottom() - line + 2, 120, line),
                             Qt.AlignmentFlag.AlignVCenter, f"{key['min']:.3g}")
            # The value of the node pointed at, on the bar.
            node = self.hovered if self.hovered is not None else self.selected
            if (node is not None and scene.value is not None and key["max"] > key["min"]
                    and np.isfinite(scene.value[node])):
                t = float(np.clip((scene.value[node] - key["min"])
                                  / (key["max"] - key["min"]), 0, 1))
                at = bar.bottom() - t * bar.height()
                painter.setPen(QPen(INK, 2))
                painter.drawLine(QPointF(bar.left() - 4, at), QPointF(bar.right() + 4, at))
            y = bar.bottom() + 14

        if scene.cell_types is not None:
            heading("Genetic identity")
            for k, name in enumerate(scene.cell_type_names):
                style = scene.cell_type_styles[k % len(scene.cell_type_styles)]
                a, b = QPointF(left + 8, y + line / 2), QPointF(left + 52, y + line / 2)
                painter.setPen(_pen(QColor.fromRgbF(0, 0, 0, 0.55), 3.2 * PX_PER_POINT))
                painter.drawLine(a, b)
                painter.setPen(_pen(GROUND, 1.7 * PX_PER_POINT, dash=_dashes(style, 1.7)))
                painter.drawLine(a, b)
                painter.setPen(INK)
                painter.drawText(QRectF(left + 66, y, right - left - 66, line),
                                 Qt.AlignmentFlag.AlignVCenter, str(name))
                y += line + 6
            note("bright ring = positive, faint = negative")


class NetworkPairPainter:
    """Two network panels side by side, moved and pointed at as one.

    Offers what :class:`NetworkPainter` offers an interactive view, so the same
    canvas shows either: a zoom, a pan, a selection or a pointed-at node made
    on one panel is made on both.
    """

    def __init__(self, scene, size: tuple[float, float] | None = None):
        self.scene = scene
        self.size = tuple(float(v) for v in (size or (2 * STANDARD_SIZE[0], STANDARD_SIZE[1])))
        half = (self.size[0] / 2, self.size[1])
        self.panels = [NetworkPainter(scene.left, half), NetworkPainter(scene.right, half)]
        self.panels[0].show_network = not scene.left_is_field
        self._share_fit()

    def _share_fit(self) -> None:
        """Give both panels one view: the wider of the two each would fit to.

        Each panel leaves room for its own largest node, and the same network
        on two scales has nodes of two sizes.
        """
        if all(panel.fitted for panel in self.panels):
            scale = min(panel.scale for panel in self.panels)
            for panel in self.panels:
                panel.scale = scale

    @property
    def network(self) -> NetworkScene:
        return self.scene.right

    def _each(self, name: str, value) -> None:
        for panel in self.panels:
            setattr(panel, name, value)

    # What a view sets or copies, kept the same on both panels.
    centre = property(lambda self: self.panels[1].centre, lambda self, v: self._each("centre", v))
    scale = property(lambda self: self.panels[1].scale, lambda self, v: self._each("scale", v))
    fitted = property(lambda self: self.panels[1].fitted, lambda self, v: self._each("fitted", v))
    hovered = property(lambda self: self.panels[1].hovered, lambda self, v: self._each("hovered", v))
    names = property(lambda self: self.panels[1].names, lambda self, v: self._each("names", v))
    moving = property(lambda self: self.panels[1].moving, lambda self, v: self._each("moving", v))
    selected = property(lambda self: self.panels[1].selected)
    thin_count = property(lambda self: max(panel.thin_count for panel in self.panels))

    def resize(self, size: tuple[float, float]) -> None:
        self.size = (float(size[0]), float(size[1]))
        for panel in self.panels:
            panel.resize((self.size[0] / 2, self.size[1]))
        self._share_fit()

    def fit(self) -> None:
        for panel in self.panels:
            panel.fit()
        self._share_fit()

    def _local(self, x: float) -> tuple[NetworkPainter, float]:
        """The panel pixel column *x* is in, and *x* within it."""
        half = self.size[0] / 2
        return (self.panels[1], x - half) if x >= half else (self.panels[0], x)

    def zoom(self, factor: float, x: float, y: float) -> None:
        panel, local = self._local(x)
        panel.zoom(factor, local, y)
        self.centre, self.scale, self.fitted = panel.centre, panel.scale, False

    def pan(self, dx: float, dy: float) -> None:
        for panel in self.panels:
            panel.pan(dx, dy)

    def node_at(self, x: float, y: float) -> int | None:
        panel, local = self._local(x)
        return panel.node_at(local, y) if panel.show_network else None

    def select(self, node: int | None) -> None:
        for panel in self.panels:
            panel.select(node)

    def describe(self, node: int) -> str:
        return self.panels[1].describe(node)

    def info_at(self, x: float, y: float) -> str | None:
        panel, local = self._local(x)
        return panel.info_at(local, y)

    def paint(self, painter: QPainter) -> None:
        painter.save()
        self.panels[0].paint(painter)
        painter.translate(self.size[0] / 2, 0)
        self.panels[1].paint(painter)
        painter.restore()


@dataclass
class NetworkGridScene:
    """Networks in rows and columns over one array, with a title and row names.

    Every panel is a network of the same nodes (electrodes) on the same scales,
    so a node is one thing in every panel: pointing at it in one marks it in
    all. ``panels[r][c]`` is ``None`` where a row has no network for a column.
    """

    title: str
    panels: list                    # rows of NetworkScene | None
    row_names: list[str] = field(default_factory=list)
    title_size: float = 13.0
    #: Each panel's size in logical pixels; the last column is wider by the key.
    cell: tuple[float, float] = (500.0, 430.0)


#: The figure title band of a grid, and the column of row names beside it.
GRID_TITLE_H = 64
GRID_ROW_W = 34


class NetworkGridPainter:
    """A grid of network panels, moved, zoomed and pointed at as one.

    Offers what :class:`NetworkPainter` offers an interactive view, as
    :class:`NetworkPairPainter` does for two. One key, beside the last column,
    serves every panel: they share their scales.
    """

    def __init__(self, scene: NetworkGridScene, size: tuple[float, float] | None = None):
        self.scene = scene
        rows = len(scene.panels)
        cols = max((len(r) for r in scene.panels), default=1)
        self._shape = (rows, cols)
        natural = (GRID_ROW_W + cols * scene.cell[0] + KEY_W, GRID_TITLE_H + rows * scene.cell[1])
        self.size = tuple(float(v) for v in (size or natural))
        self.panels: list[tuple[int, int, NetworkPainter]] = []
        for r, row in enumerate(scene.panels):
            for c, network in enumerate(row):
                if network is None:
                    continue
                panel = NetworkPainter(network, (1.0, 1.0))
                panel.title_h, panel.title_size = 40, 11
                panel.key = c == cols - 1 and r == 0
                self.panels.append((r, c, panel))
        self._focus = self.panels[0][2] if self.panels else None
        self._hovered: int | None = None
        self._selected: int | None = None
        self._layout()

    # ── geometry ─────────────────────────────────────────────────────────────

    def _cell_size(self) -> tuple[float, float]:
        rows, cols = self._shape
        width = (self.size[0] - GRID_ROW_W - KEY_W) / max(cols, 1)
        height = (self.size[1] - GRID_TITLE_H) / max(rows, 1)
        return width, height

    def _origin(self, r: int, c: int) -> tuple[float, float]:
        width, height = self._cell_size()
        return GRID_ROW_W + c * width, GRID_TITLE_H + r * height

    def _layout(self) -> None:
        width, height = self._cell_size()
        for _r, _c, panel in self.panels:
            panel.resize((width + (KEY_W if panel.key else 0), height))
            panel.fit()
        self._share_fit()

    def _share_fit(self) -> None:
        """One scale for every panel: the smallest any of them fits to."""
        if self.panels and all(p.fitted for _r, _c, p in self.panels):
            scale = min(p.scale for _r, _c, p in self.panels)
            for _r, _c, p in self.panels:
                p.scale = scale

    def resize(self, size: tuple[float, float]) -> None:
        self.size = (float(size[0]), float(size[1]))
        fitted = self.fitted
        self._layout()
        if not fitted:
            self.fitted = False

    def fit(self) -> None:
        self._layout()

    def _local(self, x: float, y: float):
        """The panel pixel (x, y) is over, and the point within it."""
        width, height = self._cell_size()
        for r, c, panel in self.panels:
            x0, y0 = self._origin(r, c)
            if x0 <= x < x0 + width + (KEY_W if panel.key else 0) and y0 <= y < y0 + height:
                return panel, x - x0, y - y0
        return None, x, y

    # ── one node across panels ───────────────────────────────────────────────

    @staticmethod
    def _row_of(panel: NetworkPainter, node: int | None):
        return None if node is None else int(panel.scene.index[node])

    @staticmethod
    def _node_in(panel: NetworkPainter, row) -> int | None:
        if row is None:
            return None
        hit = np.flatnonzero(panel.scene.index == row)
        return int(hit[0]) if hit.size else None

    @property
    def network(self) -> NetworkScene:
        """The network of the panel last pointed at."""
        return self._focus.scene

    def node_at(self, x: float, y: float) -> int | None:
        panel, lx, ly = self._local(x, y)
        if panel is None:
            return None
        node = panel.node_at(lx, ly)
        if node is not None:
            self._focus = panel
        return node

    def _spread(self, name: str, node: int | None) -> None:
        row = self._row_of(self._focus, node)
        for _r, _c, panel in self.panels:
            value = node if panel is self._focus else self._node_in(panel, row)
            if name == "select":
                panel.select(value)
            else:
                setattr(panel, name, value)

    hovered = property(lambda self: self._hovered,
                       lambda self, node: (setattr(self, "_hovered", node),
                                           self._spread("hovered", node)))

    @property
    def selected(self) -> int | None:
        return self._selected

    def select(self, node: int | None) -> None:
        self._selected = node
        self._spread("select", node)

    def describe(self, node: int) -> str:
        return self._focus.describe(node)

    def _each(self, name: str, value) -> None:
        for _r, _c, panel in self.panels:
            setattr(panel, name, value)

    centre = property(lambda self: self._focus.centre, lambda self, v: self._each("centre", v))
    scale = property(lambda self: self._focus.scale, lambda self, v: self._each("scale", v))
    fitted = property(lambda self: self._focus.fitted, lambda self, v: self._each("fitted", v))
    names = property(lambda self: self._focus.names, lambda self, v: self._each("names", v))
    moving = property(lambda self: self._focus.moving, lambda self, v: self._each("moving", v))
    thin_count = property(lambda self: max((p.thin_count for _r, _c, p in self.panels),
                                           default=0))

    def zoom(self, factor: float, x: float, y: float) -> None:
        panel, lx, ly = self._local(x, y)
        if panel is None:
            return
        panel.zoom(factor, lx, ly)
        self.centre, self.scale, self.fitted = panel.centre, panel.scale, False

    def pan(self, dx: float, dy: float) -> None:
        for _r, _c, panel in self.panels:
            panel.pan(dx, dy)

    # ── drawing ──────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        width, height = self.size
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(QRectF(0, 0, width, height), GROUND)
        for r, c, panel in self.panels:
            painter.save()
            painter.translate(*self._origin(r, c))
            panel.paint(painter)
            painter.restore()
        painter.setPen(INK)
        painter.setFont(figure_font(self.scene.title_size))
        painter.drawText(QRectF(MARGIN, 4, width - 2 * MARGIN, GRID_TITLE_H - 6),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         self.scene.title)
        _w, cell_h = self._cell_size()
        painter.setFont(figure_font(14, bold=True))
        for r, name in enumerate(self.scene.row_names):
            y = GRID_TITLE_H + (r + 0.5) * cell_h
            painter.save()
            painter.translate(GRID_ROW_W / 2 + 2, y)
            painter.rotate(-90)
            painter.drawText(QRectF(-cell_h / 2, -GRID_ROW_W / 2, cell_h, GRID_ROW_W),
                             Qt.AlignmentFlag.AlignCenter, str(name))
            painter.restore()
        painter.restore()


def _title(text: str) -> str:
    return text[:1].upper() + text[1:]
