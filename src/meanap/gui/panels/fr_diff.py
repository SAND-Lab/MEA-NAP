"""The Stim FR Δ tab: did stimulation change how each slice fired?

A diagnostic over a finished MEA-Stim run. Each slice's firing rate under every
stimulation pattern is compared, channel by channel, with the same slice's own
baseline recording (see :mod:`meanap.stim.fr_diff`), and drawn as one panel per
slice by the same code that draws the pipeline's saved figure
(:mod:`meanap.stim.fr_diff_plot`).

Port of the lab's browser viewer, ``fr_diff_viewer.html``: the slice, measure
and shared-axis controls are its drop-downs, the pattern checkboxes stand in
for clicking its legend, and hovering a dot says what it came from.

Like the Stats tab it reads a run rather than configuring one — a folder, a
``.meanap`` bundle or the node-level CSV itself — and says what it found there
before anything else. Which slices did *not* pair, and why, is as much the
answer as the plot, so it is one click away rather than in a log. The protocol
(which condition is the baseline, which are patterns) is the Stimulation tab's,
read each time this tab is shown, so correcting a mistyped condition there
redraws here without running anything again.
"""

from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QToolButton, QToolTip, QVBoxLayout,
    QWidget,
)

from meanap.stim.fr_diff import (
    FrDiffConfig, FrDiffResult, compute_fr_diff_csv, describe, format_note,
    multi_run, panel_title,
)
from meanap.stim.fr_diff_plot import (
    EXCLUDED_COLOR, SAVE_DPI, default_columns, draw_fr_diff, figure_size, stim_colors,
)

__all__ = ["FrDiffPanel", "NODE_CSV", "find_node_csv"]

NODE_CSV = "NeuronalActivity_NodeLevel.csv"
ALL_SLICES = "All slices"
#: Below these canvas widths (px) the grid drops to two columns, then one, so
#: panels stay readable instead of the figure growing past the window.
_TWO_COLUMNS_BELOW = 1100
_ONE_COLUMN_BELOW = 700
_SINGLE_MIN_H = 460          # px: the single-slice view fills the tab, but no less
_UNBOUNDED = 16777215        # QWIDGETSIZE_MAX


def find_node_csv(source: Path) -> Path | None:
    """The node-level CSV inside a run folder (or its step-2 folder), or the CSV itself."""
    source = Path(source)
    if source.is_file():
        return source if source.suffix.lower() == ".csv" else None
    for candidate in (source / "2_NeuronalActivity" / NODE_CSV, source / NODE_CSV):
        if candidate.is_file():
            return candidate
    return None


def _fmt_pct(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.{1 if abs(v) < 10 else 0}f}%"


def _fmt_log(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f}"


class _Canvas(FigureCanvasQTAgg):
    """The figure, told when its size changed so the grid can re-flow."""

    resized = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(Figure())

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self.resized.emit()


class FrDiffPanel(QWidget):
    """Load a run's node-level results and draw each slice's change from baseline."""

    choose_source_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: Path | None = None
        self._bundle = None                 # an open RunBundle keeps its extraction alive
        self._csv: Path | None = None
        self._config = FrDiffConfig()
        self._result: FrDiffResult | None = None
        self._drawn = []
        self._pattern_boxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self._build_source_box())
        layout.addWidget(self._build_controls())
        layout.addWidget(self._build_canvas(), stretch=1)

        # Resizing re-flows the grid; debounced so dragging the window edge
        # redraws once it settles rather than on every pixel.
        self._reflow = QTimer(self)
        self._reflow.setSingleShot(True)
        self._reflow.setInterval(120)
        self._reflow.timeout.connect(self._redraw)
        self.canvas.resized.connect(self._reflow.start)
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)

        self.set_source(None)

    # ── construction ─────────────────────────────────────────────────────────

    def _build_source_box(self) -> QWidget:
        box = QGroupBox("Run to inspect")
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        self.choose_btn = QPushButton("\U0001f4c2  Choose run…")
        self.choose_btn.setFixedHeight(36)
        self.choose_btn.setObjectName("secondary")
        self.choose_btn.setToolTip(
            "Pick a finished run's output folder, a .meanap bundle, or a "
            "NeuronalActivity_NodeLevel.csv. Defaults to this session's run "
            "when there is one.")
        self.choose_btn.clicked.connect(self.choose_source_requested)
        row.addWidget(self.choose_btn)
        row.addStretch(1)
        outer.addLayout(row)

        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_label.setStyleSheet("font-size: 11px; color: gray;")
        outer.addWidget(self.source_label)

        summary_row = QHBoxLayout()
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_row.addWidget(self.summary_label, stretch=1)
        self.details_btn = QToolButton()
        self.details_btn.setText("Pairing details")
        self.details_btn.setCheckable(True)
        self.details_btn.setToolTip(
            "Which slices were plotted, which were not and why, and anything "
            "else worth knowing about the recordings — the same text the "
            "pipeline writes to StimFRDiff_pairing.txt.")
        self.details_btn.toggled.connect(lambda on: self.details.setVisible(on))
        summary_row.addWidget(self.details_btn, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addLayout(summary_row)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setObjectName("log")
        self.details.setMaximumHeight(180)
        # One slice per line, as in the pipeline's pairing file: wrapped, a
        # slice's exclusions run into the next slice's name.
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.details.hide()
        outer.addWidget(self.details)
        return box

    def _build_controls(self) -> QWidget:
        bar = QWidget()
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel("Slice"))
        self.slice_combo = QComboBox()
        self.slice_combo.setMinimumContentsLength(14)
        self.slice_combo.currentIndexChanged.connect(self._on_view_changed)
        row.addWidget(self.slice_combo)

        row.addSpacing(12)
        row.addWidget(QLabel("Measure"))
        self.measure_combo = QComboBox()
        self.measure_combo.addItem("% change", "pct")
        self.measure_combo.addItem("log₂ ratio", "log2")
        self.measure_combo.setToolTip(
            "The percentage runs from −100% to unbounded above; log₂ "
            "(stim / baseline) is symmetric, halving −1 and doubling +1. "
            "A 0 Hz reading under stimulation has no log₂ and is drawn as "
            "▼ at the foot of its panel.")
        self.measure_combo.currentIndexChanged.connect(self._on_view_changed)
        row.addWidget(self.measure_combo)

        row.addSpacing(12)
        self.same_y = QCheckBox("Same y-axis for all panels")
        self.same_y.setChecked(True)
        self.same_y.setToolTip(
            "One shared range keeps a +10% slice from looking like a +900% one. "
            "Untick to scale each panel to its own data.")
        self.same_y.toggled.connect(self._on_view_changed)
        row.addWidget(self.same_y)

        row.addSpacing(12)
        self._patterns_row = QHBoxLayout()
        row.addLayout(self._patterns_row)
        row.addStretch(1)

        self.export_btn = QPushButton("Export…")
        self.export_btn.setObjectName("secondary")
        self.export_btn.setToolTip(
            f"Save the view as it is now — the slice, measure and patterns "
            f"shown — as PNG ({SAVE_DPI} dpi), SVG or PDF.")
        self.export_btn.clicked.connect(self._on_export)
        row.addWidget(self.export_btn)
        outer.addLayout(row)

        status = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        status.addWidget(self.status_label)
        status.addStretch(1)
        self.excluded_note = QLabel(
            f"Channel numbers in <b style='color:{EXCLUDED_COLOR}'>red</b> were excluded "
            f"(grounded, stimulating, or 0\u00a0Hz at baseline)")
        self.silent_note = QLabel(
            "▼ at a panel's foot: 0\u00a0Hz under that pattern "
            "(log₂ = −∞)")
        for note in (self.excluded_note, self.silent_note):
            note.setStyleSheet("color: gray; font-size: 12px;")
            status.addWidget(note)
        outer.addLayout(status)
        return bar

    def _build_canvas(self) -> QWidget:
        self.canvas = _Canvas()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Reserved even when the grid is short: otherwise a tall grid brings the
        # scrollbar in only after the figure has sized itself to the full width.
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.canvas)
        return self.scroll

    # ── state ────────────────────────────────────────────────────────────────

    def source(self) -> Path | None:
        return self._source

    def result(self) -> FrDiffResult | None:
        return self._result

    def set_config(self, config: FrDiffConfig) -> None:
        """Use ``config`` from now on, recomputing if it changed what pairs."""
        if config == self._config:
            return
        self._config = config
        if self._csv is not None:
            self._load()

    def set_source(self, source: Path | None) -> None:
        """Read ``source`` (folder, bundle or CSV); None clears the tab."""
        source = Path(source) if source is not None else None
        if source is not None and source == self._source and self._result is not None:
            return
        self._close_bundle()
        self._source = source
        self._csv = None
        if source is None:
            self.source_label.setText(
                "No run yet. Run the pipeline in MEA-Stim mode, or choose a finished run.")
            self._show_result(None)
            return
        try:
            self._csv = self._resolve_csv(source)
        except Exception as e:                        # a corrupt bundle, say
            self.source_label.setText(f"{source}\nCould not open it: {e}")
            self._show_result(None)
            return
        if self._csv is None:
            self.source_label.setText(
                f"{source}\nNo {NODE_CSV} here — step 2 has not run on it.")
            self._show_result(None)
            return
        self.source_label.setText(str(source) if self._csv == source
                                  else f"{source}\n→ {self._csv.name}")
        self._load()

    def choose_source_dialog(self) -> Path | None:
        """Ask for a folder, or failing that a bundle or CSV.

        Two dialogs, as on the Stats tab: Qt's cannot offer folders and files
        together, and a run folder is the common case.
        """
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a run output folder (cancel to pick a bundle or CSV)")
        if folder:
            return Path(folder)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a .meanap bundle or a node-level CSV", "",
            "MEA-NAP bundle or CSV (*.meanap *.csv)")
        return Path(path) if path else None

    def _resolve_csv(self, source: Path) -> Path | None:
        from meanap.pipeline.bundle import is_bundle, open_bundle

        if is_bundle(source):
            self._bundle = open_bundle(source)
            return find_node_csv(self._bundle.root)
        return find_node_csv(source)

    def _close_bundle(self) -> None:
        if self._bundle is not None:
            self._bundle.close()
            self._bundle = None

    def _load(self) -> None:
        try:
            result = compute_fr_diff_csv(self._csv, self._config)
        except Exception as e:
            self.summary_label.setText(f"Could not read {self._csv.name}: {e}")
            self._show_result(None, keep_summary=True)
            return
        self._show_result(result)

    # ── showing a result ─────────────────────────────────────────────────────

    def _show_result(self, result: FrDiffResult | None, keep_summary: bool = False) -> None:
        self._result = result
        has = result is not None and bool(result.panels)
        for widget in (self.slice_combo, self.measure_combo, self.same_y, self.export_btn):
            widget.setEnabled(has)
        self.details_btn.setEnabled(result is not None)

        if result is None:
            if not keep_summary:
                self.summary_label.setText("")
            self.details.setPlainText("")
        else:
            self.summary_label.setText(self._summary(result))
            notes = [line for note in result.notes for line in format_note(note, 20)]
            self.details.setPlainText("\n".join(describe(result) + ([""] + notes
                                                                   if notes else [])))
        self._fill_slices(result)
        self._fill_patterns(result)
        self._redraw()

    def _summary(self, result: FrDiffResult) -> str:
        cfg = result.config
        total = len(result.panels) + len(result.unpaired)
        patterns = ", ".join(cfg.label(t) for t in cfg.stims) or "no patterns set"
        text = (f"<b>{len(result.panels)} of {total} slice(s) plotted</b> — each "
                f"compared with its own <i>{cfg.baseline}</i> recording under {patterns}.")
        if not result.panels:
            text += (f"<br>Nothing paired. A slice needs a <i>{cfg.baseline}</i> recording "
                     f"and {'every one' if cfg.require_all_patterns else 'at least one'} of "
                     f"its patterns with the same run ID and slice, e.g. "
                     f"R250929CT1A_DIV250_{cfg.baseline}. The conditions are set on the "
                     f"Stimulation tab.")
        elif result.unpaired:
            text += " See Pairing details for the rest."
        if result.notes:
            text += f" {len(result.notes)} note(s) in Pairing details."
        return text

    def _fill_slices(self, result: FrDiffResult | None) -> None:
        keep = self.slice_combo.currentData()
        self.slice_combo.blockSignals(True)
        self.slice_combo.clear()
        if result is not None and result.panels:
            self.slice_combo.addItem(ALL_SLICES, None)
            multi = multi_run(result.panels)
            for p in result.panels:
                self.slice_combo.addItem(panel_title(p, multi), p.id)
            index = self.slice_combo.findData(keep)
            self.slice_combo.setCurrentIndex(max(index, 0))
        self.slice_combo.blockSignals(False)

    def _fill_patterns(self, result: FrDiffResult | None) -> None:
        hidden = self._hidden()
        while self._patterns_row.count():
            item = self._patterns_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._pattern_boxes = {}
        if result is None or not result.panels:
            return
        present = {d.stim for p in result.panels for d in p.diffs}
        colors = stim_colors(result)
        for token in result.config.stims:
            if token not in present:
                continue
            box = QCheckBox(result.config.label(token))
            box.setChecked(token not in hidden)
            box.setToolTip(f"Show {token} in every panel.")
            box.setStyleSheet(f"QCheckBox {{ color: {colors[token]}; font-weight: 600; }}")
            box.toggled.connect(self._on_view_changed)
            self._patterns_row.addWidget(box)
            self._pattern_boxes[token] = box

    def _hidden(self) -> set[str]:
        return {t for t, box in self._pattern_boxes.items() if not box.isChecked()}

    def _selected(self) -> str | None:
        return self.slice_combo.currentData()

    def _measure(self) -> str:
        return self.measure_combo.currentData() or "pct"

    def _n_shown(self) -> int:
        if self._result is None:
            return 0
        return 1 if self._selected() else len(self._result.panels)

    def _columns(self) -> int:
        n = self._n_shown()
        ncols = default_columns(n)
        width = self.canvas.width()
        if width < _TWO_COLUMNS_BELOW:
            ncols = min(ncols, 2)
        if width < _ONE_COLUMN_BELOW:
            ncols = 1
        return ncols

    def _on_view_changed(self, *_args) -> None:
        self._redraw()

    def _redraw(self) -> None:
        fig = self.canvas.figure
        result = self._result
        n = self._n_shown()
        self.same_y.setVisible(n != 1)
        if result is None:
            fig.clear()
            self._drawn = []
            self.status_label.setText("")
            self.excluded_note.hide()
            self.silent_note.hide()
            self.canvas.setMinimumHeight(0)
            self.canvas.setMaximumHeight(_UNBOUNDED)
            self.canvas.draw_idle()
            return

        # The grid's height is set by its rows, not the window: the canvas asks
        # for exactly that and the scroll area scrolls. One slice fills the view.
        ncols = self._columns()
        if n > 1:
            px_per_in = fig.dpi / self.canvas.device_pixel_ratio
            low = high = int(figure_size(n, ncols, 1.0)[1] * px_per_in)
        else:
            low, high = _SINGLE_MIN_H, _UNBOUNDED
        if (self.canvas.minimumHeight(), self.canvas.maximumHeight()) != (low, high):
            self.canvas.setMinimumHeight(low)
            self.canvas.setMaximumHeight(high)
            # The resize lands after this returns, and redraws at the new size.
        self._drawn = draw_fr_diff(
            fig, result, measure=self._measure(), same_y=self.same_y.isChecked(),
            selected=self._selected(), hidden=self._hidden(), ncols=ncols)
        self.canvas.draw_idle()
        self._update_status()

    def _update_status(self) -> None:
        result = self._result
        panels = [p for p in result.panels if self._selected() in (None, p.id)]
        log = self._measure() == "log2"
        parts = [f"{len(panels)} slice{'' if len(panels) == 1 else 's'}"]
        stim_only = sum(len(p.missing_base) for p in panels)
        if stim_only:
            parts.append(f"{stim_only} stim-only")
        values = [v for p in panels for d in p.diffs
                  if (v := (d.log2 if log else d.pct)) is not None]
        text = " · ".join(parts)
        if values:
            fmt = _fmt_log if log else _fmt_pct
            text += (f"   |   range {fmt(min(values))} … {fmt(max(values))}"
                     + (" (log₂)" if log else ""))
        self.status_label.setText(text)
        self.excluded_note.setVisible(any(p.unplotted for p in panels))
        self.silent_note.setVisible(any(dp.silent for dp in self._drawn))

    # ── hover and export ─────────────────────────────────────────────────────

    def _on_hover(self, event) -> None:
        if event.inaxes is None:
            QToolTip.hideText()
            return
        for dp in self._drawn:
            if dp.collection.axes is not event.inaxes:
                continue
            hit, info = dp.collection.contains(event)
            if hit and len(info["ind"]):
                d = dp.diffs[info["ind"][0]]
                QToolTip.showText(QCursor.pos(), self._hover_text(dp, d), self.canvas)
                return
        QToolTip.hideText()

    def _hover_text(self, dp, d) -> str:
        cfg = self._result.config
        title = panel_title(dp.panel, multi_run(self._result.panels))
        if d.log2 is None and self._measure() == "log2":
            change = "silent, log₂ = −∞ (−100%)"
        elif self._measure() == "log2":
            change = f"log₂ {d.log2:+.3g} ({d.pct:+.4g}%)"
        else:
            change = f"{d.pct:+.4g}%"
        return (f"{title} · Channel {d.channel}\n{cfg.label(d.stim)}: {change}\n"
                f"{cfg.baseline} {d.base_fr:.4g} Hz → stim {d.stim_fr:.4g} Hz")

    def _on_export(self) -> None:
        if self._result is None or not self._result.panels:
            return
        sel = self._selected()
        name = ("fr_diff_" + (sel.replace("/", "_") if sel else "all")
                + ("_log2" if self._measure() == "log2" else ""))
        start = str((self._source.parent if self._source else Path.home()) / f"{name}.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export figure", start, "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path:
            return
        # The view as it is on screen, at its on-screen width, plus the line
        # explaining the red numbers and triangles the tab says beside it.
        n, ncols = self._n_shown(), self._columns()
        width = self.canvas.width() / (self.canvas.figure.dpi / self.canvas.device_pixel_ratio)
        fig = Figure(figsize=figure_size(n, ncols, width, caption=True))
        if n == 1:
            fig.set_size_inches(width, max(self.canvas.height() / (
                self.canvas.figure.dpi / self.canvas.device_pixel_ratio), 4.6) + 0.3)
        draw_fr_diff(fig, self._result, measure=self._measure(),
                     same_y=self.same_y.isChecked(), selected=sel, hidden=self._hidden(),
                     ncols=ncols, caption=True)
        fig.savefig(path, dpi=SAVE_DPI, facecolor="white")

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._close_bundle()
        super().closeEvent(event)
