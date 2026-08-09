"""The Run tab: start one analysis, or work through a queue of them.

These were two tabs, and most of each was the same tab. Both had a Run button
and a Stop button, both had a progress bar with an estimate under it, both had a
log — duplicated widgets, duplicated wiring, and a guard in the window to stop
someone starting a single run while the queue was going.

The difference between them is one question: *what does Run start?* So that is
what the switch at the top asks, and everything that was the same in both is
shared underneath it:

* the run controls — one Run button, one Stop button, whose labels follow the
  switch;
* the progress display, which shows a queue's position ("Run 2 of 6") in the
  same place a single run shows its phase;
* the log, so the morning's reading is one transcript rather than two.

Sharing the buttons is also what deletes the overlap guard. There is one Run
button, disabled while anything is running, so "start a single run during the
queue" stops being a state the window has to refuse and starts being a state it
cannot reach.

The two pages hold only what is genuinely different: the pipeline's settings
(:class:`~meanap.gui.panels.pipeline.PipelinePanel`) and the queue's list of
saved runs (:class:`~meanap.gui.panels.queue.QueuePanel`).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup, QGroupBox, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QRadioButton, QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from meanap.gui.panels.pipeline import PipelinePanel
from meanap.gui.panels.queue import QueuePanel
from meanap.params import Params
from meanap.pipeline.progress import Progress, format_bytes, format_duration

__all__ = ["RunPanel", "THIS_RUN", "QUEUE"]

#: What the Run button will start.
THIS_RUN, QUEUE = "this_run", "queue"


class RunPanel(QWidget):
    """One tab for starting work, whether that is one run or several."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_elapsed = 0.0
        self._running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.settings = PipelinePanel()
        self.queue = QueuePanel()
        self.queue.log_message.connect(self.append_log)

        layout.addWidget(self._build_switch())
        layout.addWidget(self._build_stack(), stretch=5)
        layout.addWidget(self._build_controls())
        layout.addWidget(self._build_progress())
        layout.addWidget(self._build_log(), stretch=2)

        self._on_switch()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_switch(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 4)

        self.this_run_radio = QRadioButton("This run")
        self.this_run_radio.setChecked(True)
        self.this_run_radio.setToolTip(
            "Run the analysis the other tabs describe, once.")
        self.queue_radio = QRadioButton("Queue of saved runs")
        self.queue_radio.setToolTip(
            "Work through several saved parameter files one after another — "
            "for a set of analyses to leave running overnight."
        )
        self._group = QButtonGroup(self)
        self._group.addButton(self.this_run_radio)
        self._group.addButton(self.queue_radio)
        self._group.buttonToggled.connect(self._on_switch)

        layout.addWidget(QLabel("<b>Run:</b>"))
        layout.addWidget(self.this_run_radio)
        layout.addWidget(self.queue_radio)
        layout.addStretch()
        return row

    def _build_stack(self) -> QWidget:
        # The settings scroll; the run controls, progress and log below them do
        # not, so the button you are waiting on never scrolls off the tab.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.settings)

        self._stack = QStackedWidget()
        self._stack.addWidget(scroll)
        self._stack.addWidget(self.queue)
        return self._stack

    def _build_controls(self) -> QWidget:
        box = QGroupBox("Start")
        row = QHBoxLayout(box)

        self.test_btn = QPushButton("🧪  Test pipeline")
        self.test_btn.setFixedHeight(40)
        self.test_btn.setToolTip(
            "Download the example dataset and run the pipeline on it, "
            "to check your setup is working"
        )

        self.run_btn = QPushButton("▶  Run pipeline")
        self.run_btn.setFixedHeight(40)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)

        for widget in (self.test_btn, self.run_btn, self.stop_btn):
            row.addWidget(widget)
        return box

    def _build_progress(self) -> QWidget:
        # Hidden until a run starts: an empty bar sitting at 0% before anything
        # has been asked for reads as "stuck", not as "idle".
        self.progress_box = QGroupBox("Progress")
        layout = QVBoxLayout(self.progress_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)  # per-mille, so the bar creeps
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(18)

        self.progress_label = QLabel("Waiting to start…")
        self.progress_label.setWordWrap(True)

        self.progress_eta = QLabel("")
        self.progress_eta.setStyleSheet("font-size: 11px; color: gray;")

        # Transfers get their own bar: during the first recording of a remote
        # run it is the only thing moving, and the estimate depends on it.
        # Deliberately slimmer than the run bar — two bars of equal weight
        # invite the reader to compare percentages that measure different things.
        self.transfer_bar = QProgressBar()
        self.transfer_bar.setRange(0, 1000)
        self.transfer_bar.setValue(0)
        self.transfer_bar.setTextVisible(False)
        self.transfer_bar.setFixedHeight(8)
        self.transfer_label = QLabel("")
        self.transfer_label.setStyleSheet("font-size: 11px; color: gray;")

        for widget in (self.progress_bar, self.progress_label, self.progress_eta,
                       self.transfer_bar, self.transfer_label):
            layout.addWidget(widget)
        self.progress_box.setVisible(False)
        self._set_transfer_visible(False)
        return self.progress_box

    def _build_log(self) -> QWidget:
        box = QGroupBox("Status log")
        layout = QVBoxLayout(box)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.log)
        return box

    # ── The switch ────────────────────────────────────────────────────────────

    def mode(self) -> str:
        """:data:`THIS_RUN` or :data:`QUEUE` — what Run would start."""
        return QUEUE if self.queue_radio.isChecked() else THIS_RUN

    def set_mode(self, mode: str) -> None:
        (self.queue_radio if mode == QUEUE else self.this_run_radio).setChecked(True)

    def _on_switch(self, *_args) -> None:
        queued = self.mode() == QUEUE
        self._stack.setCurrentIndex(1 if queued else 0)
        # Testing the setup is about *a* run, so it says nothing useful about
        # a list of them.
        self.test_btn.setVisible(not queued)
        self._relabel_run()

    def _relabel_run(self) -> None:
        if self.mode() == QUEUE:
            n = len(self.queue.paths())
            self.run_btn.setText(
                f"▶  Run queue ({n})" if n else "▶  Run queue")
            # An empty queue has nothing to start; a pipeline run always has.
            self.run_btn.setEnabled(bool(n) and not self._running)
        else:
            self.run_btn.setText("▶  Run pipeline")
            self.run_btn.setEnabled(not self._running)

    def refresh(self) -> None:
        """Re-read anything the switch's labels depend on (the queue's length)."""
        self._relabel_run()

    # ── Starting and stopping ─────────────────────────────────────────────────

    def set_running(self, running: bool) -> None:
        """The one place run/stop enablement is decided, for either kind of run.

        With a single pair of buttons there is no way to ask for a second run
        while one is going, which is why the window no longer has to refuse it.
        """
        self._running = running
        self.stop_btn.setEnabled(running)
        self.test_btn.setEnabled(not running)
        # Editing the queue mid-flight would change a list that is being read.
        self.queue.set_editable(not running)
        self._relabel_run()

    # ── Progress display ──────────────────────────────────────────────────────

    def _set_transfer_visible(self, visible: bool) -> None:
        self.transfer_bar.setVisible(visible)
        self.transfer_label.setVisible(visible)

    def start_progress(self) -> None:
        """Show an empty bar as a run begins."""
        self.progress_box.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting…")
        self.progress_eta.setText("")
        self.transfer_bar.setValue(0)
        self.transfer_label.setText("")
        self._set_transfer_visible(False)

    def show_progress(self, snapshot: Progress, prefix: str = "",
                      fraction: float | None = None) -> None:
        """Render one snapshot from the running pipeline.

        ``prefix`` and ``fraction`` are what let a queue share this display: the
        prefix says which run is in flight, and the fraction is the queue's own
        progress rather than the individual run's.
        """
        self.progress_box.setVisible(True)
        self.progress_bar.setValue(int(round(
            (snapshot.fraction if fraction is None else fraction) * 1000)))
        self._last_elapsed = snapshot.elapsed_s

        headline = f"{snapshot.percent}%  ·  {snapshot.phase}"
        if snapshot.detail:
            headline += f"  ·  {snapshot.detail}"
        self.progress_label.setText(prefix + headline)

        elapsed = format_duration(snapshot.elapsed_s)
        if snapshot.eta_s is None:
            # Saying "estimating" beats showing a number derived from a
            # benchmark machine before this one has finished anything.
            self.progress_eta.setText(f"{elapsed} elapsed  ·  estimating time left…")
        else:
            self.progress_eta.setText(
                f"{elapsed} elapsed  ·  about {format_duration(snapshot.eta_s)} left")

        self._set_transfer_visible(snapshot.transferring)
        if snapshot.transferring:
            share = min(1.0, snapshot.bytes_done / snapshot.bytes_total)
            self.transfer_bar.setValue(int(round(share * 1000)))
            text = (f"Downloaded {format_bytes(snapshot.bytes_done)} of "
                    f"{format_bytes(snapshot.bytes_total)}")
            if snapshot.transfer_detail:
                text += f"  ·  {snapshot.transfer_detail}"
            self.transfer_label.setText(text)

    def show_queue_progress(self, index: int, total: int, label: str,
                            snapshot: Progress) -> None:
        """Where the queue is, and where the run in flight is within it."""
        total = max(total, 1)
        self.queue.mark(index, "running")
        self.show_progress(
            snapshot,
            prefix=f"Run {index + 1} of {total} — {label}   ·   ",
            # Whole runs behind, plus this run's share of the one in flight.
            fraction=(index + snapshot.fraction) / total,
        )
        if snapshot.eta_s is not None:
            self.progress_eta.setText(
                self.progress_eta.text() + " in this run")

    def finish_progress(self, message: str) -> None:
        """Leave the bar showing how the run ended rather than blanking it."""
        self.progress_label.setText(message)
        self.progress_eta.setText(
            f"{format_duration(self._last_elapsed)} total"
            if self._last_elapsed else "")
        self._set_transfer_visible(False)

    # ── Log ───────────────────────────────────────────────────────────────────

    def append_log(self, text: str) -> None:
        self.log.append(text)

    # ── Parameters ────────────────────────────────────────────────────────────

    def load(self, params: Params) -> None:
        self.settings.load(params)

    def save(self, params: Params) -> None:
        self.settings.save(params)
