"""Viewer for a finished MEA-Stim run's firing-rate change from baseline.

Each ALI-CO's (air-liquid interface cerebral organoid slice) firing rate under
every stimulation pattern is compared, channel by channel, with its own
baseline recording (see :mod:`meanap.stim.fr_diff`, which calls them slices),
and drawn one panel per ALI-CO (:mod:`meanap.stim.fr_diff_plot`). Nothing here
is part of a pipeline run: the window reads step 2's node-level CSV and writes
only what the user saves from it.

The parameters default to the lab's and can be changed here, for this window
only and only once applied, so a run with differently named files can be
viewed without changing anything the pipeline reads.

The baselines may come from another run, for unstimulated recordings analysed
on their own: they are added to the stim run's table in memory (see
:func:`meanap.stim.fr_diff.merge_baseline`), and written out only on request.
"""

from __future__ import annotations

import re
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QWIDGETSIZE_MAX, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from meanap.gui.theme import ACCENT
from meanap.gui.wheel import _scrolling_ancestor
from meanap.gui.widgets import scrollable
from meanap.stim.fr_diff import (
    FrDiffConfig, FrDiffResult, compute_fr_diff, describe, format_note,
    merge_baseline, multi_run, panel_title, read_node_csv,
)
from meanap.stim.fr_diff_plot import (
    EXCLUDED_COLOR, SAVE_DPI, Drawing, default_columns, draw_fr_diff, figure_size,
    save_fr_diff_figure, stim_colors,
)

__all__ = [
    "FrDiffViewerWindow", "NODE_CSV", "find_node_csv", "format_channels",
    "format_patterns", "parse_channels", "parse_patterns",
]

NODE_CSV = "NeuronalActivity_NodeLevel.csv"
#: Default name for the stim run's table with the baselines merged in.
MERGED_CSV = "NeuronalActivity_NodeLevel_base_stim_merged.csv"
ALL_ALICOS = "All"
_NO_BASELINE = "Not needed if all runs were analyzed together in MEA-STIM."
#: Below these plot widths (px) the grid drops to two columns, then one, so
#: panels stay readable instead of shrinking to fit.
_TWO_COLUMNS_BELOW = 1100
_ONE_COLUMN_BELOW = 700
_SINGLE_MIN_H = 460          # px: the single-ALI-CO view fills the plot area, but no less
_GAP = 8                     # px: window margin, and space around the splitter lines
_TITLE_GAP = 3               # px: the theme's gap between a group title and its frame
_HOVER_GROW = 1              # px a hovered handle's line grows either side: 1 px -> 3 px
#: Clear px (before, after) each splitter handle's 1 px line. Pairing Details'
#: title sits under the vertical one, so it is kept _TITLE_GAP clear of the
#: line even while hovered.
_HANDLES = {"horizontal": (_GAP, _GAP), "vertical": (_GAP, _TITLE_GAP + _HOVER_GROW)}
_HAIRLINE = "rgb(218, 220, 224)"          # the theme's box borders
_HAIRLINE_HOVER = ACCENT                  # the theme's primary: the checkboxes' hover underline
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
                     for t, label in patterns.items())


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
    """Channel IDs as a sorted, comma-separated list: ``{31, 21}`` -> ``21, 31``."""
    return ", ".join(str(int(c)) for c in sorted(channels))


def parse_channels(text: str) -> list[int]:
    """Every whole number in ``text``, in order, once: ``"21, 31 41"`` -> [21, 31, 41]."""
    return list(dict.fromkeys(int(n) for n in re.findall(r"\d+", text)))


def _checkbox(text: str) -> QCheckBox:
    """A checkbox as wide as its own box and text.

    Stretched across a form row, its focus and hover highlight would run the
    whole width of the column instead of marking the box.
    """
    box = QCheckBox(text)
    box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return box


def _remove_button(tooltip: str, slot) -> QToolButton:
    """The small ✕ that removes a run or a baseline."""
    btn = QToolButton()
    btn.setText("✕")
    btn.setAutoRaise(True)
    btn.setToolTip(tooltip)
    btn.clicked.connect(slot)
    return btn


def _entry(text: str, panel_id: str | None, tooltip: str = "") -> QStandardItem:
    item = QStandardItem(text)
    item.setData(panel_id, Qt.ItemDataRole.UserRole)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def _hairline(across_x: bool, before: int, after: int, color: str, grow: int = 0) -> str:
    """A 1 px ``color`` line with ``before`` and ``after`` clear px either side of it.

    For a splitter handle ``before + 1 + after`` px wide, the gradient running
    across it (along x for a handle between side-by-side widgets). ``grow``
    widens the line by that many px either side, into the clear px, so the
    handle itself keeps its width.
    """
    n = before + 1 + after
    a, b = (before - grow) / n, (before + 1 + grow) / n
    x2, y2 = (1, 0) if across_x else (0, 1)
    return (f"qlineargradient(x1:0, y1:0, x2:{x2}, y2:{y2}, stop:0 transparent, "
            f"stop:{a:.4f} transparent, stop:{a + 0.0001:.4f} {color}, "
            f"stop:{b - 0.0001:.4f} {color}, stop:{b:.4f} transparent, stop:1 transparent)")


def _driven(config: FrDiffConfig) -> set[int]:
    """Every channel any pattern drove: the Stimulating field's one list."""
    return set().union(*config.stimulated.values())


def _change_stamp(source: Path) -> int | None:
    """When ``source``'s node-level CSV last changed, or None if it cannot be told.

    A bundle's own file for a bundle, whose extracted CSV never changes; the
    CSV itself otherwise. Cheap: a bundle is not opened to find it.
    """
    from meanap.pipeline.bundle import is_bundle

    try:
        path = source if is_bundle(source) else find_node_csv(source)
        return path.stat().st_mtime_ns if path is not None else None
    except OSError:
        return None


def _open_source(source: Path):
    """``(bundle, csv)`` for a folder, bundle or CSV: the bundle, when it is
    one, must stay open while its extracted CSV is read. Either may be None.
    """
    from meanap.pipeline.bundle import is_bundle, open_bundle

    if is_bundle(source):
        bundle = open_bundle(source)
        return bundle, find_node_csv(bundle.root)
    return None, find_node_csv(source)


def _source_name(source: Path) -> str:
    """What to call a run: its folder's name for its node-level CSV, which
    every run's is named alike; the bundle's, folder's or CSV's name otherwise.
    """
    if source.name != NODE_CSV:
        return source.name
    folder = source.parent
    return (folder.parent if folder.name == "2_NeuronalActivity" else folder).name


def _save_dir(source: Path) -> Path:
    """Where a file saved from ``source`` goes by default: beside the run, not in it.

    A file left inside a run folder would travel in any bundle later made from it.
    """
    folder = source.parent
    return folder.parent.parent if folder.name == "2_NeuronalActivity" else folder


def _run_id_text(result: FrDiffResult | None) -> str:
    """**Run ID: R250929**, from the file names of every ALI-CO, paired or not."""
    runs = sorted({x.run for x in (result.panels + result.unpaired) if x.run}
                  if result is not None else ())
    if not runs:
        return "<b>Run ID: unknown</b>"
    return f"<b>Run ID{'s' if len(runs) > 1 else ''}: {', '.join(runs)}</b>"


def _fmt(v: float, log: bool) -> str:
    """A signed value without its unit: the status line puts it after the range."""
    digits = 2 if log else (1 if abs(v) < 10 else 0)
    return f"{'+' if v >= 0 else _MINUS}{abs(v):.{digits}f}"


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
        area = _scrolling_ancestor(self)
        if area is None:
            event.ignore()
            return
        QApplication.sendEvent(area.viewport(), event)
        event.accept()


class FrDiffViewerWindow(QDialog):
    """Browse each ALI-CO's per-channel firing-rate change from its own baseline.

    Non-modal, and reopened rather than rebuilt, like the spike and burst
    viewer: it is a workspace kept beside the main window. What it shows is
    not kept, though: closing it unloads the run and puts the parameters
    and view back to the lab's defaults (see _unload), so reopening reads the
    CSV afresh rather than showing numbers a later run has replaced.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Firing-rate change from baseline")
        # A dialog gets a bare frame on most platforms; this is a workspace to
        # keep beside the main window, minimised and resized.
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(1000, 640)
        # The theme adds unseen 1 px frames and margins to splitters, scroll
        # areas and handles; they are removed so _GAP and the handles' hairlines
        # are the only spacing. Group titles sit 2 px in, as one column.
        self.setStyleSheet(
            "QGroupBox::title { left: 2px; margin: 0px; padding: 0px; } "
            "QSplitter { border: none; } "
            "QSplitter::handle { margin: 0px; image: none; } "
            "QScrollArea { margin: 0px; } "
            "QScrollArea#controls { border: none; } "
            "QPlainTextEdit#log { margin: 0px; } "
            + "".join(f"QSplitter::handle:{o}{state} {{ background: "
                      f"{_hairline(o == 'horizontal', *_HANDLES[o], color, grow)}; }} "
                      for o in _HANDLES
                      for state, color, grow in (("", _HAIRLINE, 0),
                                                 (":hover", _HAIRLINE_HOVER, _HOVER_GROW))))
        self.resize(1400, 900)

        self._source: Path | None = None
        self._source_chosen = False
        self._bundle = None                 # an open RunBundle keeps its extraction alive
        self._csv: Path | None = None
        self._stamp: int | None = None      # _change_stamp of the source as last read
        # Baselines from another run (see set_baseline), read once.
        self._baseline_source: Path | None = None
        self._baseline_stamp: int | None = None
        self._baseline_table = None         # a DataFrame, or None
        self._config = FrDiffConfig()
        self._result: FrDiffResult | None = None
        self._drawing = Drawing([], {})
        self._pattern_boxes: dict[str, QCheckBox] = {}

        controls = scrollable(self._build_controls())
        controls.setObjectName("controls")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(controls)
        splitter.addWidget(self._build_plot())
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(sum(_HANDLES["horizontal"]) + 1)
        # Wide enough for the Parameters form, whose longest row is the checkbox
        # sitting in its field column.
        splitter.setSizes([420, 980])

        # The pairing text runs one ALI-CO to a line, wider than the plot, so
        # it spans the window under both the controls and the plot, edge to
        # edge with them.
        body = QSplitter(Qt.Orientation.Vertical)
        body.addWidget(splitter)
        body.addWidget(self._build_details_box())
        body.setStretchFactor(0, 1)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(sum(_HANDLES["vertical"]) + 1)
        body.setSizes([720, 150])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_GAP, _GAP, _GAP, _GAP)
        layout.addWidget(body, 1)
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

        self._fit_parameter_fields()
        self._clear_parameters()
        self.set_source(None)
        # A bundle's extraction is closed on close (see _unload); this covers
        # quitting with the window still open.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._close_bundle)

    # ── construction ─────────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        # No margins: the boxes' edges are the column's, level with the plot's
        # top and with Pairing Details on the left; the handle beside it
        # holds the gap to the plot.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_run_box())
        layout.addWidget(self._build_view_box())
        layout.addWidget(self._build_parameters())
        layout.addStretch(1)
        return column

    def _build_run_box(self) -> QWidget:
        # Untitled: the button and the run ID say what it is. Without a title
        # the theme's room for one above the box is only a gap.
        box = QGroupBox()
        # The button's text is set as a panel title is (theme.py's QGroupBox).
        box.setStyleSheet("QGroupBox { margin-top: 0px; } "
                          "QPushButton { font-size: 12px; font-weight: 600; }")
        layout = QVBoxLayout(box)
        self.choose_btn = QPushButton("\U0001f4c2  Choose Run")
        self.choose_btn.setObjectName("secondary")
        self.choose_btn.setToolTip(
            "Pick a .meanap bundle or a NeuronalActivity_NodeLevel.csv. Opens "
            "on this session's run when there is one.")
        self.choose_btn.clicked.connect(self._on_choose)
        layout.addWidget(self.choose_btn)

        row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.source_label, 1)
        self.clear_source_btn = _remove_button("Remove run", self._on_clear_source)
        row.addWidget(self.clear_source_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)

        # Hidden while empty (see _set_summary): the box fits what it says,
        # only the button and a line until a run is chosen.
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.hide()
        layout.addWidget(self.summary_label)

        self.baseline_btn = QPushButton("\U0001f4c2  Choose Baseline")
        self.baseline_btn.setObjectName("secondary")
        self.baseline_btn.setToolTip("Baseline recordings from another MEA-NAP run.")
        self.baseline_btn.clicked.connect(self._on_choose_baseline)
        layout.addWidget(self.baseline_btn)

        # The baseline file and the way to remove it; a note without one.
        self._baseline_row = QWidget()
        row = QHBoxLayout(self._baseline_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.baseline_label = QLabel()
        self.baseline_label.setWordWrap(True)
        self.baseline_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.baseline_label, 1)
        self.clear_baseline_btn = _remove_button("Remove baseline",
                                                 lambda: self.set_baseline(None))
        row.addWidget(self.clear_baseline_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.baseline_label.setText(_NO_BASELINE)
        self.clear_baseline_btn.hide()
        layout.addWidget(self._baseline_row)

        self.save_merged_btn = QPushButton("Save Merged CSV")
        self.save_merged_btn.setObjectName("secondary")
        self.save_merged_btn.setToolTip(
            "Write the stim run's table with the baseline recordings added, as "
            "used here, to a CSV.")
        self.save_merged_btn.clicked.connect(self._on_save_merged)
        self.save_merged_btn.hide()
        layout.addWidget(self.save_merged_btn)
        return box

    def _build_view_box(self) -> QWidget:
        box = QGroupBox("View")
        form = QFormLayout(box)
        self.alico_combo = QComboBox()
        self.alico_combo.setModel(QStandardItemModel(self.alico_combo))
        self.alico_combo.setToolTip(
            "Choose an ALI-CO to see it on its own, or All for the grid; "
            "clicking a panel in the grid opens that ALI-CO too. Entries marked "
            "not paired have no panel: hover them for why.")
        self.alico_combo.currentIndexChanged.connect(self._on_view_changed)
        form.addRow("ALI-CO", self.alico_combo)

        self.measure_combo = QComboBox()
        self.measure_combo.addItem("% Change", "pct")
        self.measure_combo.addItem("log₂ Ratio", "log2")
        self.measure_combo.setToolTip(
            "The percentage runs from −100% to unbounded above; log₂ "
            "(stim / baseline) is symmetric, halving −1 and doubling +1. "
            "A 0 Hz reading under stimulation has no log₂ and is drawn as "
            "▼ at the foot of its panel.")
        self.measure_combo.currentIndexChanged.connect(self._on_view_changed)
        form.addRow("Measure", self.measure_combo)

        self.same_y = _checkbox("Same Y-axis for all panels")
        self.same_y.setChecked(True)
        self.same_y.setToolTip(
            "One shared range keeps a +10% ALI-CO from looking like a +900% one. "
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

        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("secondary")
        self.export_btn.setToolTip(
            f"Save the view as it is now — the ALI-COs, measure and patterns "
            f"shown — as PNG ({SAVE_DPI} dpi), SVG or PDF, with a legend.")
        self.export_btn.clicked.connect(self._on_export)
        form.addRow(self.export_btn)
        return box

    def _build_parameters(self) -> QWidget:
        box = QGroupBox("Parameters")
        box.setToolTip(
            "Which recordings are compared with which, read from the file "
            "names, and which channels say nothing about the tissue. Changes "
            "take effect when applied and last while this window is open; the "
            "pipeline's settings are not touched.")
        # The theme's primary button is larger than its secondary one; this
        # matches Apply and Reset in size here only, keeping Apply's colour,
        # with their text the size of the form's (the app font, theme.py).
        box.setStyleSheet("QPushButton { font-size: 10pt; font-weight: 600; "
                          "padding: 5px 14px; border-radius: 6px; }")
        form = QFormLayout(box)
        self.baseline_edit = QLineEdit()
        self.baseline_edit.setToolTip(
            "The condition of the baseline recording: the token after DIV<n>_ in "
            "its file name, e.g. prestim in R250929CT1A_DIV250_prestim. Each "
            "ALI-CO's stimulated recordings are compared with its own baseline, "
            "matched on the run ID and the ALI-CO (R250929 and CT1A).")
        self.patterns_edit = QLineEdit()
        self.patterns_edit.setToolTip(
            "The stimulation conditions, comma-separated, each as token=legend "
            "name (or just the token). Recordings of any other condition are "
            "ignored.")
        self.require_all = _checkbox("Only ALI-COs recorded under every pattern")
        self.require_all.setToolTip(
            "When ticked an ALI-CO needs its baseline and every pattern above to "
            "be plotted; when not, its baseline and any one of them will do.")
        self.grounded_edit = QLineEdit()
        self.grounded_edit.setToolTip(
            "Channels left out of every comparison, e.g. a grounded reference "
            "electrode. Comma-separated channel IDs.")
        self.stimulating_edit = QLineEdit()
        self.stimulating_edit.setToolTip(
            "The stimulating electrodes, left out of every pattern: they read "
            "0 Hz by design. Comma-separated channel IDs.")
        self._edits = (self.baseline_edit, self.patterns_edit, self.grounded_edit,
                       self.stimulating_edit)
        # Before a run is loaded the fields are empty, showing the lab's values
        # in grey: the format to follow, and what an untouched field means
        # (see _config_from_fields). Loading a run takes the fields as they
        # are and writes the values it used in (see set_source).
        lab = FrDiffConfig()
        for edit, text in ((self.baseline_edit, lab.baseline),
                           (self.patterns_edit, format_patterns(lab.stim_labels)),
                           (self.grounded_edit, format_channels(lab.grounded)),
                           (self.stimulating_edit, format_channels(_driven(lab)))):
            edit.setPlaceholderText(text)
            edit.setToolTip(edit.toolTip() + " Left empty, the lab's value (in grey) "
                            "is used" + ("; to leave none out, write none."
                                         if edit in (self.grounded_edit,
                                                     self.stimulating_edit) else "."))

        # Nothing re-pairs until Apply: otherwise a half-typed baseline empties
        # the plot the moment the field loses focus.
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setToolTip("Re-pair the run with these parameters.")
        self.apply_btn.clicked.connect(self._on_apply_parameters)
        self.reset_parameters_btn = QPushButton("Reset to Defaults")
        self.reset_parameters_btn.setObjectName("secondary")
        self.reset_parameters_btn.setToolTip(
            "Put the lab's parameters back in the fields; Apply to use them.")
        self.reset_parameters_btn.clicked.connect(self._on_reset_parameters)
        # Equal halves of the row, each as tall as the row: the themes differ
        # on which of the two has a border, so their own heights may not agree.
        buttons = QHBoxLayout()
        for btn in (self.apply_btn, self.reset_parameters_btn):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            buttons.addWidget(btn, 1)
        self.pending_label = QLabel("*Unapplied changes*")
        self.pending_label.setStyleSheet("color: gray; font-size: 11px;")

        form.addRow("Baseline", self.baseline_edit)
        form.addRow("Patterns", self.patterns_edit)
        # In the field column, under the Patterns box it qualifies.
        form.addRow("", self.require_all)
        form.addRow("Grounded", self.grounded_edit)
        form.addRow("Stimulating", self.stimulating_edit)
        # Fields as wide as the checkbox between them (see
        # _fit_parameter_fields): grown to it, where macOS would leave them
        # at their own width, and kept to the left rather than centred.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.addRow(buttons)
        form.addRow(self.pending_label)

        for edit in self._edits:
            edit.textChanged.connect(self._on_parameters_edited)
        self.require_all.toggled.connect(self._on_parameters_edited)
        self.parameters_box = box
        self.parameters_form = form
        return box

    def _build_details_box(self) -> QWidget:
        box = QGroupBox("Pairing Details")
        # The same 5 px all round the text box: the theme pads a group box's
        # top more than its sides, so its padding is left to the layout here.
        box.setStyleSheet("QGroupBox { padding: 0px; }")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(5, 5, 5, 5)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setObjectName("log")
        # One ALI-CO per line: wrapped, one ALI-CO's exclusions run into the
        # next one's name.
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.details.setMinimumHeight(120)
        self.details.setToolTip(
            "Which ALI-COs were plotted, which were not and why, and anything "
            "else worth knowing about the recordings.")
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
        # One line at the bottom right: what the plot's marks mean, then what
        # it shows. Filled by _update_status.
        row = QHBoxLayout()
        row.addStretch(1)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                       | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.status_label)
        return row

    def _fit_parameter_fields(self) -> None:
        """End the Parameters fields where the require-all checkbox's text ends.

        The checkbox sits in the same field column, so a field no wider than
        it lines up with it on the right.
        """
        self.require_all.ensurePolished()
        width = self.require_all.sizeHint().width()
        for edit in self._edits:
            edit.setMaximumWidth(width)

    # ── public ───────────────────────────────────────────────────────────────

    def source(self) -> Path | None:
        """The folder, bundle or CSV being shown, or None."""
        return self._source

    def baseline_source(self) -> Path | None:
        """The other run the baselines come from, or None."""
        return self._baseline_source

    def source_chosen(self) -> bool:
        """Whether the user picked the source here, so a new run should not replace it."""
        return self._source_chosen

    def result(self) -> FrDiffResult | None:
        """The pairing on screen, or None when nothing is loaded."""
        return self._result

    def config(self) -> FrDiffConfig:
        """The parameters in use, which are not necessarily what the fields say."""
        return self._config

    def set_source(self, source: Path | None) -> None:
        """Read ``source`` (folder, bundle or CSV); None clears the window."""
        source = Path(source) if source is not None else None
        # The same run is not read twice, unless its CSV has been rewritten
        # since (a re-run into the same folder, say).
        if (source is not None and source == self._source and self._result is not None
                and _change_stamp(source) == self._stamp):
            return
        self._close_bundle()
        self._source = source
        self._csv = None
        self.clear_source_btn.setVisible(source is not None)
        self.source_label.setToolTip("")
        if source is None:
            empty = "Choose a .meanap bundle or a NeuronalActivity_NodeLevel.csv (step 2 output)."
        else:
            try:
                self._bundle, self._csv = _open_source(source)
                empty = (None if self._csv is not None
                         else f"{source}\nNo {NODE_CSV} here — step 2 has not run on it.")
            except Exception as e:                        # a corrupt bundle, say
                empty = f"{source}\nCould not open it: {e}"
        if empty is not None:
            self.source_label.setText(empty)
            self._set_summary("")
            self._show_result(None)
            return
        # The run ID is what identifies a run at a glance; the path is there
        # on hover, for when it does not.
        self.source_label.setToolTip(str(source) if self._csv == source
                                     else f"{source}\n→ {self._csv.name}")
        self._stamp = _change_stamp(source)
        # A run is read with the fields as they stand, applied or not, and
        # the values it was read with are then written in, the lab's included.
        self._config = self._config_from_fields()
        self._load()
        self._load_parameters(self._config)

    def choose_source_dialog(self) -> Path | None:
        """Ask for a .meanap bundle or a node-level CSV."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a .meanap bundle or a node-level CSV", "",
            "MEA-NAP bundle or CSV (*.meanap *.csv)")
        return Path(path) if path else None

    def _set_summary(self, text: str) -> None:
        """Show ``text`` under the run ID, taking no room when there is none."""
        self.summary_label.setText(text)
        self.summary_label.setVisible(bool(text))

    # ── loading ──────────────────────────────────────────────────────────────

    def _on_choose(self) -> None:
        source = self.choose_source_dialog()
        # On macOS a native file dialog hands focus back to the application's
        # main window when it closes, leaving this one behind it.
        self.raise_()
        self.activateWindow()
        if source is None:
            return
        self._source_chosen = True
        self.set_source(source)

    def _on_clear_source(self) -> None:
        """Let go of the run; the baseline and the parameters stay."""
        self._source_chosen = False
        self.set_source(None)

    def done(self, result: int) -> None:
        """Closing (the window's close button, or Esc) unloads the run."""
        super().done(result)
        self._unload()

    def _unload(self) -> None:
        """Back to the window as first built: no run, lab parameters, default view.

        The window itself is kept for reopening; a later run, or the same
        folder rewritten, is then read afresh rather than shown as it was.
        """
        self._source_chosen = False
        self._config = FrDiffConfig()
        with QSignalBlocker(self.measure_combo), QSignalBlocker(self.same_y):
            self.measure_combo.setCurrentIndex(0)
            self.same_y.setChecked(True)
        self.set_baseline(None)
        self.set_source(None)
        self._clear_parameters()

    def _close_bundle(self) -> None:
        if self._bundle is not None:
            self._bundle.close()
            self._bundle = None

    def set_baseline(self, source: Path | None) -> None:
        """Take the baseline recordings from ``source`` too; None stops.

        ``source`` is another run's folder, bundle or CSV. Its table is read
        here, once, and kept whole: which of its recordings are baselines
        depends on the Baseline parameter, so they are picked out at each
        pairing. A bundle is closed once its table is read. It stays when
        the run changes, until removed or the window is closed.
        """
        source = Path(source) if source is not None else None
        if (source is not None and source == self._baseline_source
                and self._baseline_table is not None
                and _change_stamp(source) == self._baseline_stamp):
            return
        self._baseline_source, self._baseline_table = source, None
        if source is not None:
            bundle = None
            try:
                bundle, csv = _open_source(source)
                if csv is None:
                    error = f"No {NODE_CSV} here — step 2 has not run on it."
                else:
                    self._baseline_stamp = _change_stamp(source)
                    self._baseline_table = read_node_csv(csv)
                    error = None
            except Exception as e:                        # a corrupt bundle, say
                error = f"Could not open it: {e}"
            finally:
                if bundle is not None:
                    bundle.close()
            self.baseline_label.setText(f"Baseline: <b>{_source_name(source)}</b>"
                                        + (f"<br>{error}" if error else ""))
            self.baseline_label.setToolTip(str(source))
        else:
            self.baseline_label.setText(_NO_BASELINE)
            self.baseline_label.setToolTip("")
        has = self._baseline_table is not None
        self.clear_baseline_btn.setVisible(source is not None)
        self.save_merged_btn.setVisible(has)
        self.save_merged_btn.setEnabled(has and self._csv is not None)
        if self._csv is not None:
            self._load()

    def _on_choose_baseline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the baseline run: a .meanap bundle or a node-level CSV", "",
            "MEA-NAP bundle or CSV (*.meanap *.csv)")
        # See _on_choose.
        self.raise_()
        self.activateWindow()
        if path:
            self.set_baseline(Path(path))

    def _merged_table(self):
        """The stim run's table with the baselines added, as paired now."""
        return merge_baseline(read_node_csv(self._csv), self._baseline_table,
                              self._config)[0]

    def _on_save_merged(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save merged CSV", str(_save_dir(self._source) / MERGED_CSV), "CSV (*.csv)")
        self.raise_()
        self.activateWindow()
        if not path:
            return
        path = Path(path)
        inputs = [p for p in (self._csv, self._source, self._baseline_source) if p]
        if any(path.resolve() == p.resolve() for p in inputs):
            QMessageBox.warning(self, "Save merged CSV",
                                f"{path.name} is one of the inputs; choose another name.")
            return
        try:
            self._merged_table().to_csv(path, index=False)
        except Exception as e:
            QMessageBox.critical(self, "Save merged CSV", f"Could not write {path}: {e}")

    def _load(self) -> None:
        try:
            result = compute_fr_diff(read_node_csv(self._csv), self._config,
                                     self._baseline_table)
        except Exception as e:
            self.source_label.setText(_run_id_text(None))
            self._set_summary(f"Could not read {self._csv.name}: {e}")
            self._show_result(None)
            return
        self.source_label.setText(_run_id_text(result))
        self._set_summary(self._summary(result))
        self._show_result(result)

    # ── parameters ───────────────────────────────────────────────────────────

    def _parameter_widgets(self) -> tuple:
        return (*self._edits, self.require_all)

    def _load_parameters(self, config: FrDiffConfig) -> None:
        """Write ``config`` into the Parameters fields, without re-pairing.

        An empty channel list is written as ``none``: an empty field means the
        lab's channels.
        """
        blockers = [QSignalBlocker(w) for w in self._parameter_widgets()]
        self.baseline_edit.setText(config.baseline)
        self.patterns_edit.setText(format_patterns(config.stim_labels))
        self.require_all.setChecked(config.require_all_patterns)
        # The fields hold one list of stimulating channels; a config driving
        # different channels per pattern shows them all.
        for edit, channels in ((self.grounded_edit, config.grounded),
                               (self.stimulating_edit, _driven(config))):
            edit.setText(format_channels(channels) or "none")
        for b in blockers:
            b.unblock()
        self._on_parameters_edited()

    def _clear_parameters(self) -> None:
        """Empty the fields, so they show the lab's values in grey and mean them."""
        blockers = [QSignalBlocker(w) for w in self._parameter_widgets()]
        for edit in self._edits:
            edit.clear()
        self.require_all.setChecked(FrDiffConfig().require_all_patterns)
        for b in blockers:
            b.unblock()
        self._on_parameters_edited()

    def _on_reset_parameters(self) -> None:
        """The lab's values: in grey before a run is loaded, written in after."""
        if self._csv is None:
            self._clear_parameters()
        else:
            self._load_parameters(FrDiffConfig())

    def _config_from_fields(self) -> FrDiffConfig:
        """The fields as a config; an empty one is the lab's value (its grey text)."""
        lab = FrDiffConfig()
        patterns = (parse_patterns(self.patterns_edit.text())
                    if self.patterns_edit.text().strip() else dict(lab.stim_labels))

        def channels(edit: QLineEdit, default) -> frozenset[int]:
            text = edit.text()
            return frozenset(parse_channels(text) if text.strip() else default)

        stimulating = channels(self.stimulating_edit, _driven(lab))
        return FrDiffConfig(
            baseline=self.baseline_edit.text().strip() or lab.baseline,
            stim_labels=patterns,
            grounded=channels(self.grounded_edit, lab.grounded),
            stimulated={t: stimulating for t in patterns} if stimulating else {},
            require_all_patterns=self.require_all.isChecked(),
        )

    def has_unapplied_parameters(self) -> bool:
        """Whether the Parameters fields differ from the config in use."""
        return self._config_from_fields() != self._config

    def _on_parameters_edited(self, *_args) -> None:
        """Offer Apply only while the fields say something other than what is in use.

        Before a run is loaded there is nothing to apply to: loading one takes
        the fields as they are.
        """
        pending = self._csv is not None and self.has_unapplied_parameters()
        self.apply_btn.setEnabled(pending)
        self.pending_label.setVisible(pending)

    def _on_apply_parameters(self) -> None:
        self._apply_config(self._config_from_fields())
        self._on_parameters_edited()

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
        self.save_merged_btn.setEnabled(self._csv is not None
                                        and self._baseline_table is not None)
        if result is None:
            self.details.setPlainText("")
        else:
            notes = [line for note in result.notes for line in format_note(note, 20)]
            self.details.setPlainText("\n".join(describe(result) + ([""] + notes
                                                                   if notes else [])))
        self._fill_alicos(result)
        self._fill_patterns(result)
        self._on_parameters_edited()            # Apply only with a run to apply to
        self._redraw()

    def _summary(self, result: FrDiffResult) -> str:
        cfg = result.config
        total = len(result.panels) + len(result.unpaired)
        patterns = ", ".join(cfg.label(t) for t in cfg.stims) or "no patterns set"
        text = (f"<b>{len(result.panels)} of {total} ALI-CO(s) plotted</b> — each "
                f"compared with its own <i>{cfg.baseline or '(no baseline set)'}</i> "
                f"recording under '{patterns}'.")
        if not result.panels:
            text += (f"<br><br>Nothing paired. An ALI-CO needs a <i>{cfg.baseline}</i> recording "
                     f"and {'every one' if cfg.require_all_patterns else 'at least one'} of "
                     f"its patterns with the same run ID and ALI-CO, e.g. "
                     f"R250929CT1A_DIV250_{cfg.baseline}. Check the Parameters panel "
                     f"against the file names.")
        if result.notes:
            text += f" {len(result.notes)} note(s) under Pairing Details."
        return text

    def _fill_alicos(self, result: FrDiffResult | None) -> None:
        keep = self._selected()
        combo = self.alico_combo
        model = combo.model()
        combo.blockSignals(True)
        model.clear()
        if result is not None and result.panels:
            multi = multi_run(result.panels)
            model.appendRow(_entry(ALL_ALICOS, None))
            for p in result.panels:
                model.appendRow(_entry(
                    panel_title(p, multi), p.id,
                    f"{p.run} {p.slice} ({p.grp}): {p.base_file} and "
                    f"{len(p.stim_files)} stimulated recording(s)"))
            # Listed where they would be chosen, so a missing ALI-CO is noticed
            # rather than silently absent from the grid.
            for u in sorted(result.unpaired, key=lambda u: (u.run, u.slice)):
                label = f"{u.run} {u.slice}" if multi or not u.slice else u.slice
                reason = (f"incomplete: no {', '.join(u.missing)}" if u.missing
                          else u.reason)
                item = _entry(f"{label}  — not paired", None,
                              f"{u.run} {u.slice}: {', '.join(u.conditions)} ({reason})")
                item.setEnabled(False)
                model.appendRow(item)
            row = next((i for i in range(model.rowCount())
                        if model.item(i).isEnabled()
                        and model.item(i).data(Qt.ItemDataRole.UserRole) == keep), 0)
            combo.setCurrentIndex(row)
        combo.blockSignals(False)

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
            box = _checkbox(result.config.label(token))
            box.setChecked(token not in hidden)
            box.setToolTip(f"Show {token} in every panel.")
            box.setStyleSheet(f"QCheckBox {{ color: {colors[token]}; font-weight: 600; }}")
            box.toggled.connect(self._on_view_changed)
            self._patterns_layout.addWidget(box)
            self._pattern_boxes[token] = box

    def _hidden(self) -> set[str]:
        return {t for t, box in self._pattern_boxes.items() if not box.isChecked()}

    def _selected(self) -> str | None:
        return self.alico_combo.currentData(Qt.ItemDataRole.UserRole)

    def select_alico(self, panel_id: str | None) -> None:
        """Show ``panel_id`` on its own, or the grid for None; an unknown id is ignored."""
        index = self.alico_combo.findData(panel_id, Qt.ItemDataRole.UserRole)
        if index >= 0:
            self.alico_combo.setCurrentIndex(index)

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
            self._set_canvas_height(0, QWIDGETSIZE_MAX)
            self.canvas.draw_idle()
            return

        # The grid's height is set by its rows, not the window: the canvas asks
        # for exactly that and the scroll area scrolls. One ALI-CO fills the view.
        ncols = self._columns()
        if n > 1:
            px_per_in = fig.dpi / self.canvas.device_pixel_ratio
            height = int(figure_size(n, ncols, 1.0, legend=False)[1] * px_per_in)
            self._set_canvas_height(height, height)
        else:
            self._set_canvas_height(_SINGLE_MIN_H, QWIDGETSIZE_MAX)
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
        parts = []
        if any(p.unplotted for p in panels):
            parts.append(f"Channel numbers in <b style='color:{EXCLUDED_COLOR}'>red</b> "
                         f"are excluded (grounded/stimulating/0 Hz baseline)")
        if any(dp.silent for dp in self._drawing.points):
            parts.append("▼ at a panel's foot: 0 Hz under that pattern (log₂ = −∞)")
        parts.append(f"{len(panels)} ALI-CO{'' if len(panels) == 1 else 's'}")
        stim_only = sum(len(p.missing_base) for p in panels)
        if stim_only:
            parts.append(f"{stim_only} stim-only channel(s)")
        values = [v for p in panels for d in p.diffs
                  if (v := (d.log2 if log else d.pct)) is not None]
        if values:
            parts.append(f"Range: {_fmt(min(values), log)} – {_fmt(max(values), log)} "
                         f"({'log₂' if log else '%'})")
        self.status_label.setText("&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts))

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
        """A click on a panel in the grid opens that ALI-CO on its own."""
        if self._selected() is not None or event.inaxes is None:
            return
        panel = self._drawing.panels.get(event.inaxes)
        if panel is not None:
            self.select_alico(panel.id)

    def _on_export(self) -> None:
        sel = self._selected()
        name = ("fr_diff_" + (sel.replace("/", "_") if sel else "all")
                + ("_log2" if self._measure() == "log2" else ""))
        path, _ = QFileDialog.getSaveFileName(
            self, "Export figure", str(_save_dir(self._source) / f"{name}.png"),
            "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path:
            return
        # At the on-screen width, so the file matches the view; the saved
        # figure adds the legend and caption the window shows beside the plot.
        px_per_in = self.canvas.figure.dpi / self.canvas.device_pixel_ratio
        save_fr_diff_figure(self._result, path, measure=self._measure(),
                            same_y=self.same_y.isChecked(), selected=sel,
                            hidden=self._hidden(), ncols=self._columns(),
                            width=self.canvas.width() / px_per_in)
