"""Did stimulation change how each slice fired?

A window for browsing a finished MEA-Stim run's firing-rate change from
baseline. Each slice's firing rate under every stimulation pattern is compared,
channel by channel, with that slice's own baseline recording (see
:mod:`meanap.stim.fr_diff`), and drawn as one panel per slice by the same code
that draws the pipeline's saved ``StimFRDiff`` figures
(:mod:`meanap.stim.fr_diff_plot`).

Port of the lab's browser viewer, ``fr_diff_viewer.html``, with the room a
window gives it: the slices are a list to step through rather than a
drop-down, clicking a panel in the grid opens that slice, the pattern
checkboxes are the legend, and hovering a dot says what it came from.

Which slices did *not* pair, and why, is as much the answer as the plot, so
the pairing details sit in the side column rather than in a log, and unpaired
slices are listed — greyed, with their reason — among the ones that did.

The protocol (which condition is the baseline, which are patterns, which
channels to leave out) defaults to the lab's and is editable here, for this
window only: a run whose files are named differently can be looked at without
changing anything the pipeline reads. The pipeline's own ``StimFRDiff`` files
always use the defaults.
"""

from __future__ import annotations

import re
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QScrollArea, QSplitter, QToolTip, QVBoxLayout, QWidget,
)

from meanap.gui.advanced import AdvancedSection
from meanap.gui.widgets import scrollable
from meanap.stim.fr_diff import (
    FrDiffConfig, FrDiffResult, compute_fr_diff_csv, describe, format_note,
    multi_run, panel_title,
)
from meanap.stim.fr_diff_plot import (
    EXCLUDED_COLOR, SAVE_DPI, Drawing, default_columns, draw_fr_diff, figure_size,
    stim_colors,
)

__all__ = [
    "FrDiffViewerWindow", "NODE_CSV", "find_node_csv", "format_channels",
    "format_patterns", "parse_channels", "parse_patterns",
]

NODE_CSV = "NeuronalActivity_NodeLevel.csv"
ALL_SLICES = "All slices"
#: Below these plot widths (px) the grid drops to two columns, then one, so
#: panels stay readable instead of shrinking to fit.
_TWO_COLUMNS_BELOW = 1100
_ONE_COLUMN_BELOW = 700
_SINGLE_MIN_H = 460          # px: the single-slice view fills the plot area, but no less
_UNBOUNDED = 16777215        # QWIDGETSIZE_MAX
_MINUS = "−"


def find_node_csv(source: Path) -> Path | None:
    """The node-level CSV inside a run folder (or its step-2 folder), or the CSV itself."""
    source = Path(source)
    if source.is_file():
        return source if source.suffix.lower() == ".csv" else None
    for candidate in (source / "2_NeuronalActivity" / NODE_CSV, source / NODE_CSV):
        if candidate.is_file():
            return candidate
    return None


def format_patterns(patterns: dict[str, str]) -> str:
    """``{"stim1": "Spatial 1"}`` as ``stim1=Spatial 1``; a bare token when unlabelled."""
    return ", ".join(t if not label or label == t else f"{t}={label}"
                     for t, label in (patterns or {}).items())


def parse_patterns(text: str) -> dict[str, str]:
    """``stim1=Spatial 1, stim3`` as ``{"stim1": "Spatial 1", "stim3": "stim3"}``."""
    patterns = {}
    for item in text.split(","):
        token, _, label = item.partition("=")
        token, label = token.strip(), label.strip()
        if token:
            patterns[token] = label or token
    return patterns


def format_channels(channels) -> str:
    return ", ".join(str(int(c)) for c in sorted(channels or ()))


def parse_channels(text: str) -> list[int]:
    """Every whole number in ``text``, in order, once: ``"21, 31 41"`` -> [21, 31, 41]."""
    return list(dict.fromkeys(int(n) for n in re.findall(r"\d+", text)))


def _fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else _MINUS
    return f"{sign}{abs(v):.{1 if abs(v) < 10 else 0}f}%"


def _fmt_log(v: float) -> str:
    sign = "+" if v >= 0 else _MINUS
    return f"{sign}{abs(v):.2f}"


class _Canvas(FigureCanvasQTAgg):
    """The figure, which reports its resizes and leaves the wheel to the page.

    matplotlib's Qt canvas takes every wheel event for its own ``scroll_event``
    and accepts it, so a figure inside a scroll area stops the area scrolling
    wherever the pointer is over the plot — which in a grid is everywhere.
    Nothing here zooms on the wheel, so it is handed to the scroll area. Handed
    rather than ignored: Qt passes an ignored wheel event up to the parent only
    when it came from the device, not when it was sent.
    """

    resized = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(Figure())

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self.resized.emit()

    def wheelEvent(self, event) -> None:  # noqa: N802 — Qt override
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is None:
            event.ignore()
            return
        QApplication.sendEvent(parent.viewport(), event)
        event.accept()


class FrDiffViewerWindow(QDialog):
    """Browse each slice's per-channel firing-rate change from its own baseline.

    Non-modal, and reopened rather than rebuilt, like the spike and burst
    viewer: it is a workspace kept beside the main window.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Firing-rate change from baseline")
        # A dialog gets a bare frame on most platforms; this is a workspace to
        # keep beside the main window, minimised and resized.
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(1000, 640)
        self.resize(1400, 900)

        self._source: Path | None = None
        self._source_chosen = False
        self._bundle = None                 # an open RunBundle keeps its extraction alive
        self._csv: Path | None = None
        self._config = FrDiffConfig()
        self._result: FrDiffResult | None = None
        self._drawing = Drawing([], {})
        self._pattern_boxes: dict[str, QCheckBox] = {}

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scrollable(self._build_controls()))
        splitter.addWidget(self._build_plot())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 1060])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(splitter, 1)
        layout.addLayout(self._build_status_bar(), 0)

        # Resizing re-flows the grid; debounced so dragging the window edge
        # redraws once it settles rather than on every pixel.
        self._reflow = QTimer(self)
        self._reflow.setSingleShot(True)
        self._reflow.setInterval(120)
        self._reflow.timeout.connect(self._redraw)
        self.canvas.resized.connect(self._reflow.start)
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        self._load_protocol(self._config)
        self.set_source(None)
        # Closing the window only hides it (it is reopened, not rebuilt), and
        # the plot may still re-read the bundle's CSV after that, so its
        # extraction is let go when the source changes or the app quits.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._close_bundle)

    # ── construction ─────────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(4, 4, 8, 4)
        layout.addWidget(self._build_run_box())
        layout.addWidget(self._build_slices_box(), stretch=2)
        layout.addWidget(self._build_view_box())
        layout.addWidget(self._build_protocol())
        layout.addWidget(self._build_details_box(), stretch=1)
        return column

    def _build_run_box(self) -> QWidget:
        box = QGroupBox("Run")
        layout = QVBoxLayout(box)
        self.choose_btn = QPushButton("\U0001f4c2  Choose run…")
        self.choose_btn.setObjectName("secondary")
        self.choose_btn.setToolTip(
            "Pick a finished run's output folder, a .meanap bundle, or a "
            "NeuronalActivity_NodeLevel.csv. Opens on this session's run when "
            "there is one.")
        self.choose_btn.clicked.connect(self._on_choose)
        layout.addWidget(self.choose_btn)

        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_label.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self.source_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        return box

    def _build_slices_box(self) -> QWidget:
        box = QGroupBox("Slices")
        layout = QVBoxLayout(box)
        self.slice_list = QListWidget()
        self.slice_list.setToolTip(
            "Choose a slice to see it on its own, or All slices for the grid. "
            "The arrow keys step through them; clicking a panel in the grid "
            "opens that slice too. Greyed slices did not pair — hover for why.")
        self.slice_list.currentRowChanged.connect(self._on_view_changed)
        layout.addWidget(self.slice_list)
        return box

    def _build_view_box(self) -> QWidget:
        box = QGroupBox("View")
        form = QFormLayout(box)
        self.measure_combo = QComboBox()
        self.measure_combo.addItem("% change", "pct")
        self.measure_combo.addItem("log₂ ratio", "log2")
        self.measure_combo.setToolTip(
            "The percentage runs from −100% to unbounded above; log₂ "
            "(stim / baseline) is symmetric, halving −1 and doubling +1. "
            "A 0 Hz reading under stimulation has no log₂ and is drawn as "
            "▼ at the foot of its panel.")
        self.measure_combo.currentIndexChanged.connect(self._on_view_changed)
        form.addRow("Measure", self.measure_combo)

        self.same_y = QCheckBox("Same y-axis for all panels")
        self.same_y.setChecked(True)
        self.same_y.setToolTip(
            "One shared range keeps a +10% slice from looking like a +900% one. "
            "Untick to scale each panel to its own data.")
        self.same_y.toggled.connect(self._on_view_changed)
        form.addRow(self.same_y)

        # One coloured switch per pattern: the plot's legend, and the way to
        # hide a pattern in every panel at once.
        self._patterns_widget = QWidget()
        self._patterns_layout = QVBoxLayout(self._patterns_widget)
        self._patterns_layout.setContentsMargins(0, 0, 0, 0)
        self._patterns_layout.setSpacing(2)
        form.addRow("Patterns", self._patterns_widget)

        self.export_btn = QPushButton("Export…")
        self.export_btn.setObjectName("secondary")
        self.export_btn.setToolTip(
            f"Save the view as it is now — the slices, measure and patterns "
            f"shown — as PNG ({SAVE_DPI} dpi), SVG or PDF, with a legend.")
        self.export_btn.clicked.connect(self._on_export)
        form.addRow(self.export_btn)
        return box

    def _build_protocol(self) -> QWidget:
        section = AdvancedSection("Protocol")
        section.header.setToolTip(
            "Which recordings are compared with which, read from the file "
            "names, and which channels say nothing about the tissue. Changes "
            "here re-pair at once and last while this window is open; the "
            "pipeline's own StimFRDiff files use the lab defaults.")
        form = section.form()
        self.baseline_edit = QLineEdit()
        self.baseline_edit.setToolTip(
            "The condition of the baseline recording: the token after DIV<n>_ in "
            "its file name, e.g. prestim in R250929CT1A_DIV250_prestim. Each "
            "slice's stimulated recordings are compared with its own baseline, "
            "matched on the run ID and slice (R250929 and CT1A).")
        self.patterns_edit = QLineEdit()
        self.patterns_edit.setPlaceholderText("stim1=Spatial 1, stim3=Spatial 3")
        self.patterns_edit.setToolTip(
            "The stimulation conditions, comma-separated, each as token=legend "
            "name (or just the token). Recordings of any other condition are "
            "ignored.")
        self.require_all = QCheckBox("Only slices recorded under every pattern")
        self.require_all.setToolTip(
            "When ticked a slice needs its baseline and every pattern above to "
            "be plotted; when not, its baseline and any one of them will do.")
        self.grounded_edit = QLineEdit()
        self.grounded_edit.setToolTip(
            "Channels left out of every comparison, e.g. a grounded reference "
            "electrode. Comma-separated channel IDs.")
        self.stimulating_edit = QLineEdit()
        self.stimulating_edit.setToolTip(
            "The stimulating electrodes, left out of every pattern: they read "
            "0 Hz by design. Comma-separated channel IDs.")
        self.reset_protocol_btn = QPushButton("Reset to lab defaults")
        self.reset_protocol_btn.clicked.connect(
            lambda: (self._load_protocol(FrDiffConfig()), self._on_protocol_edited()))

        form.addRow("Baseline", self.baseline_edit)
        form.addRow("Patterns", self.patterns_edit)
        form.addRow(self.require_all)
        form.addRow("Grounded", self.grounded_edit)
        form.addRow("Stimulating", self.stimulating_edit)
        form.addRow(self.reset_protocol_btn)

        for edit in (self.baseline_edit, self.patterns_edit, self.grounded_edit,
                     self.stimulating_edit):
            edit.editingFinished.connect(self._on_protocol_edited)
        self.require_all.toggled.connect(self._on_protocol_edited)
        self.protocol_section = section
        return section

    def _build_details_box(self) -> QWidget:
        box = QGroupBox("Pairing details")
        layout = QVBoxLayout(box)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setObjectName("log")
        # One slice per line, as in the pipeline's pairing file: wrapped, a
        # slice's exclusions run into the next slice's name.
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.details.setMinimumHeight(120)
        self.details.setToolTip(
            "Which slices were plotted, which were not and why, and anything "
            "else worth knowing about the recordings — the same text the "
            "pipeline writes to StimFRDiff_pairing.txt.")
        layout.addWidget(self.details)
        return box

    def _build_plot(self) -> QWidget:
        self.canvas = _Canvas()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Reserved even when the grid is short: otherwise a tall grid brings the
        # scrollbar in only after the figure has sized itself to the full width.
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.canvas)
        return self.scroll

    def _build_status_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        row.addWidget(self.status_label)
        row.addStretch(1)
        self.excluded_note = QLabel(
            f"Channel numbers in <b style='color:{EXCLUDED_COLOR}'>red</b> were "
            f"excluded (grounded, stimulating, or 0 Hz at baseline)")
        self.silent_note = QLabel(
            "▼ at a panel's foot: 0 Hz under that pattern "
            "(log₂ = −∞)")
        for note in (self.excluded_note, self.silent_note):
            note.setStyleSheet("color: gray; font-size: 12px;")
            row.addWidget(note)
        return row

    # ── public ───────────────────────────────────────────────────────────────

    def source(self) -> Path | None:
        return self._source

    def source_chosen(self) -> bool:
        """Whether the user picked the source here, so a new run should not replace it."""
        return self._source_chosen

    def result(self) -> FrDiffResult | None:
        return self._result

    def config(self) -> FrDiffConfig:
        return self._config

    def set_config(self, config: FrDiffConfig) -> None:
        """Use ``config`` from now on, showing it and re-pairing if it changed."""
        self._load_protocol(config)
        self._apply_config(config)

    def set_source(self, source: Path | None) -> None:
        """Read ``source`` (folder, bundle or CSV); None clears the window."""
        source = Path(source) if source is not None else None
        if source is not None and source == self._source and self._result is not None:
            return
        self._close_bundle()
        self._source = source
        self._csv = None
        if source is None:
            self.source_label.setText(
                "No run yet. Run the pipeline in MEA-Stim mode through step 2, "
                "or choose a finished run.")
            self.summary_label.setText("")
            self._show_result(None)
            return
        try:
            self._csv = self._resolve_csv(source)
        except Exception as e:                        # a corrupt bundle, say
            self.source_label.setText(f"{source}\nCould not open it: {e}")
            self.summary_label.setText("")
            self._show_result(None)
            return
        if self._csv is None:
            self.source_label.setText(f"{source}\nNo {NODE_CSV} here — step 2 has not run on it.")
            self.summary_label.setText("")
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

    # ── loading ──────────────────────────────────────────────────────────────

    def _on_choose(self) -> None:
        source = self.choose_source_dialog()
        if source is None:
            return
        self._source_chosen = True
        self.set_source(source)

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
            self._show_result(None)
            return
        self.summary_label.setText(self._summary(result))
        self._show_result(result)

    # ── protocol ─────────────────────────────────────────────────────────────

    def _load_protocol(self, config: FrDiffConfig) -> None:
        """Show ``config`` in the Protocol fields, without re-pairing."""
        widgets = (self.baseline_edit, self.patterns_edit, self.require_all,
                   self.grounded_edit, self.stimulating_edit)
        for w in widgets:
            w.blockSignals(True)
        self.baseline_edit.setText(config.baseline)
        self.patterns_edit.setText(format_patterns(config.stim_labels))
        self.require_all.setChecked(config.require_all_patterns)
        self.grounded_edit.setText(format_channels(config.grounded))
        # The fields hold one list of stimulating channels; a config driving
        # different channels per pattern shows them all.
        driven = set().union(*config.stimulated.values()) if config.stimulated else set()
        self.stimulating_edit.setText(format_channels(driven))
        for w in widgets:
            w.blockSignals(False)

    def _config_from_fields(self) -> FrDiffConfig:
        patterns = parse_patterns(self.patterns_edit.text())
        stimulating = frozenset(parse_channels(self.stimulating_edit.text()))
        return FrDiffConfig(
            baseline=self.baseline_edit.text().strip(),
            stim_labels=patterns,
            grounded=frozenset(parse_channels(self.grounded_edit.text())),
            stimulated={t: stimulating for t in patterns} if stimulating else {},
            require_all_patterns=self.require_all.isChecked(),
        )

    def _on_protocol_edited(self, *_args) -> None:
        self._apply_config(self._config_from_fields())

    def _apply_config(self, config: FrDiffConfig) -> None:
        if config == self._config:
            return
        self._config = config
        if self._csv is not None:
            self._load()

    # ── showing a result ─────────────────────────────────────────────────────

    def _show_result(self, result: FrDiffResult | None) -> None:
        self._result = result
        has = result is not None and bool(result.panels)
        for widget in (self.measure_combo, self.same_y, self.export_btn):
            widget.setEnabled(has)
        if result is None:
            self.details.setPlainText("")
        else:
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
                f"compared with its own <i>{cfg.baseline or '(no baseline set)'}</i> "
                f"recording under {patterns}.")
        if not result.panels:
            text += (f"<br>Nothing paired. A slice needs a <i>{cfg.baseline}</i> recording "
                     f"and {'every one' if cfg.require_all_patterns else 'at least one'} of "
                     f"its patterns with the same run ID and slice, e.g. "
                     f"R250929CT1A_DIV250_{cfg.baseline}. Check the Protocol section "
                     f"against the file names.")
        if result.notes:
            text += f" {len(result.notes)} note(s) under Pairing details."
        return text

    def _fill_slices(self, result: FrDiffResult | None) -> None:
        keep = self._selected()
        self.slice_list.blockSignals(True)
        self.slice_list.clear()
        if result is not None and result.panels:
            multi = multi_run(result.panels)
            all_item = QListWidgetItem(ALL_SLICES)
            all_item.setData(Qt.ItemDataRole.UserRole, None)
            self.slice_list.addItem(all_item)
            for p in result.panels:
                item = QListWidgetItem(panel_title(p, multi))
                item.setData(Qt.ItemDataRole.UserRole, p.id)
                item.setToolTip(f"{p.run} {p.slice} ({p.grp}): {p.base_file} and "
                                f"{len(p.stim_files)} stimulated recording(s)")
                self.slice_list.addItem(item)
            # Listed where they would be browsed, so a missing slice is noticed
            # rather than silently absent from the grid.
            for u in sorted(result.unpaired, key=lambda u: (u.run, u.slice)):
                label = f"{u.run} {u.slice}" if multi or not u.slice else u.slice
                item = QListWidgetItem(f"{label}  — not paired")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                reason = (f"incomplete: no {', '.join(u.missing)}" if u.missing
                          else u.reason)
                item.setToolTip(f"{u.run} {u.slice}: {', '.join(u.conditions)} ({reason})")
                self.slice_list.addItem(item)
            row = next((i for i in range(self.slice_list.count())
                        if self.slice_list.item(i).data(Qt.ItemDataRole.UserRole) == keep
                        and self.slice_list.item(i).flags() & Qt.ItemFlag.ItemIsEnabled), 0)
            self.slice_list.setCurrentRow(row)
        self.slice_list.blockSignals(False)

    def _fill_patterns(self, result: FrDiffResult | None) -> None:
        hidden = self._hidden()
        while self._patterns_layout.count():
            item = self._patterns_layout.takeAt(0)
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
            self._patterns_layout.addWidget(box)
            self._pattern_boxes[token] = box

    def _hidden(self) -> set[str]:
        return {t for t, box in self._pattern_boxes.items() if not box.isChecked()}

    def _selected(self) -> str | None:
        item = self.slice_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def select_slice(self, panel_id: str | None) -> None:
        for i in range(self.slice_list.count()):
            if self.slice_list.item(i).data(Qt.ItemDataRole.UserRole) == panel_id:
                self.slice_list.setCurrentRow(i)
                return

    def _measure(self) -> str:
        return self.measure_combo.currentData() or "pct"

    def _n_shown(self) -> int:
        if self._result is None or not self._result.panels:
            return 0
        return 1 if self._selected() else len(self._result.panels)

    def _columns(self) -> int:
        ncols = default_columns(self._n_shown())
        width = self.canvas.width()
        if width < _TWO_COLUMNS_BELOW:
            ncols = min(ncols, 2)
        if width < _ONE_COLUMN_BELOW:
            ncols = 1
        return ncols

    def _on_view_changed(self, *_args) -> None:
        self.scroll.verticalScrollBar().setValue(0)
        self._redraw()

    def _redraw(self) -> None:
        fig = self.canvas.figure
        result = self._result
        n = self._n_shown()
        self.same_y.setVisible(n > 1)
        if not n:
            fig.clear()
            self._drawing = Drawing([], {})
            self.status_label.setText("")
            self.excluded_note.hide()
            self.silent_note.hide()
            self._set_canvas_height(0, _UNBOUNDED)
            self.canvas.draw_idle()
            return

        # The grid's height is set by its rows, not the window: the canvas asks
        # for exactly that and the scroll area scrolls. One slice fills the view.
        ncols = self._columns()
        if n > 1:
            px_per_in = fig.dpi / self.canvas.device_pixel_ratio
            height = int(figure_size(n, ncols, 1.0, legend=False)[1] * px_per_in)
            self._set_canvas_height(height, height)
        else:
            self._set_canvas_height(_SINGLE_MIN_H, _UNBOUNDED)
        self._drawing = draw_fr_diff(
            fig, result, measure=self._measure(), same_y=self.same_y.isChecked(),
            selected=self._selected(), hidden=self._hidden(), ncols=ncols, legend=False)
        self.canvas.draw_idle()
        self._update_status()

    def _set_canvas_height(self, low: int, high: int) -> None:
        # The resize this causes lands after the current draw, and redraws at
        # the new size through the canvas's resized signal.
        if (self.canvas.minimumHeight(), self.canvas.maximumHeight()) != (low, high):
            self.canvas.setMinimumHeight(low)
            self.canvas.setMaximumHeight(high)

    def _update_status(self) -> None:
        result = self._result
        panels = [p for p in result.panels if self._selected() in (None, p.id)]
        log = self._measure() == "log2"
        parts = [f"{len(panels)} slice{'' if len(panels) == 1 else 's'}"]
        stim_only = sum(len(p.missing_base) for p in panels)
        if stim_only:
            parts.append(f"{stim_only} stim-only channel(s)")
        values = [v for p in panels for d in p.diffs
                  if (v := (d.log2 if log else d.pct)) is not None]
        text = " · ".join(parts)
        if values:
            fmt = _fmt_log if log else _fmt_pct
            text += (f"   |   range {fmt(min(values))} … {fmt(max(values))}"
                     + (" (log₂)" if log else ""))
        self.status_label.setText(text)
        self.excluded_note.setVisible(any(p.unplotted for p in panels))
        self.silent_note.setVisible(any(dp.silent for dp in self._drawing.points))

    # ── hover, click and export ──────────────────────────────────────────────

    def _on_hover(self, event) -> None:
        if event.inaxes is None:
            QToolTip.hideText()
            return
        for dp in self._drawing.points:
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

    def _on_click(self, event) -> None:
        """A click on a panel in the grid opens that slice on its own."""
        if self._selected() is not None or event.inaxes is None:
            return
        panel = self._drawing.panels.get(event.inaxes)
        if panel is not None:
            self.select_slice(panel.id)

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
        # The view as it is on screen, at its on-screen width, plus the legend
        # and the line explaining the red numbers and triangles, which the
        # window says beside the plot and a saved file has to say itself.
        n, ncols = self._n_shown(), self._columns()
        px_per_in = self.canvas.figure.dpi / self.canvas.device_pixel_ratio
        width = self.canvas.width() / px_per_in
        fig = Figure(figsize=figure_size(n, ncols, width, caption=True))
        draw_fr_diff(fig, self._result, measure=self._measure(),
                     same_y=self.same_y.isChecked(), selected=sel, hidden=self._hidden(),
                     ncols=ncols, caption=True)
        fig.savefig(path, dpi=SAVE_DPI, facecolor="white")
