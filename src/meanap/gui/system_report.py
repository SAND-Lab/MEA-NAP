"""This computer, what a run will do with it, and how fast it actually goes.

Opened from the toolbar, and there for two questions that were previously only
answerable by guesswork.

**Which of our computers should run the batch?** The benchmark times the real
spike detector and the real null-model pool, so the score reflects the work
MEA-NAP does rather than a spec sheet. Two scores are in the ratio of the work
the two machines should be given.

**Why is MEA-NAP slow on mine?** Usually because of something on this page: too
little free memory to run steps 3 and 4 more than one recording at a time, a
CPU with fewer cores than it appears to have, or worker processes disabled
altogether. None of that was visible before — a batch crawling because 3 GB
were free looked exactly like a batch that was simply large.

**Copy report** puts the lot on the clipboard as plain text, which is the form
in which one collaborator can actually send it to another.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QDialog, QGroupBox, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from meanap.gui.widgets import pin_width, scrollable
from meanap.pipeline.machine import (
    Machine, WorkPlan, describe_machine, plan_work, report_lines,
)

__all__ = ["SystemReportDialog"]


class _BenchmarkThread(QThread):
    """The timing run, off the UI thread — 10-20 s on an ordinary laptop."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def run(self) -> None:
        from meanap.shared.benchmark import run_benchmark

        try:
            self.done.emit(run_benchmark(log=self.progress.emit))
        except Exception as exc:   # noqa: BLE001 - shown to the user as text
            self.failed.emit(str(exc))


class SystemReportDialog(QDialog):
    """What this computer is, what a run will do with it, and how fast it is."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("This computer")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(640, 560)

        self._machine: Machine = describe_machine()
        self._plan: WorkPlan = plan_work()
        self._benchmark = None
        self._worker: _BenchmarkThread | None = None

        page = QWidget()
        column = QVBoxLayout(page)
        column.addWidget(self._build_machine_box())
        column.addWidget(self._build_plan_box())
        column.addWidget(self._build_benchmark_box())
        column.addWidget(self._build_notes_box())
        column.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(scrollable(page))
        layout.addLayout(self._build_buttons())
        self._render()

    # ── Sections ──────────────────────────────────────────────────────────────

    def _build_machine_box(self) -> QGroupBox:
        box = QGroupBox("This computer")
        layout = QVBoxLayout(box)
        self._machine_label = _body("")
        layout.addWidget(self._machine_label)
        return box

    def _build_plan_box(self) -> QGroupBox:
        # The point of the section: these numbers are chosen automatically from
        # the cores and free memory, and until now nothing said what they were.
        box = QGroupBox("What a run will do here")
        layout = QVBoxLayout(box)
        self._plan_label = _body("")
        layout.addWidget(self._plan_label)
        return box

    def _render(self) -> None:
        """Put the current machine and plan on screen.

        One place, called on open and on every refresh, so the two can never
        show figures from different moments — free memory moves while the
        window is open, and a plan explained by a stale memory figure would be
        worse than no explanation.
        """
        machine = self._machine
        ram = (f"{machine.ram_available_gb:.1f} GB memory free"
               + ("" if machine.ram_measured
                  else " (estimated — psutil is not installed)"))
        self._machine_label.setText(
            f"<b>{machine.cpu_name}</b><br>"
            f"{machine.physical_cores} physical cores "
            f"({machine.logical_cores} logical) · {ram}<br>"
            f"{machine.system} {machine.release} ({machine.architecture}) · "
            f"MEA-NAP {machine.meanap_version} on Python {machine.python_version}")
        self._plan_label.setText("<br><br>".join(
            f"<b>{step.name}</b> — {step.workers} {step.unit}"
            f"<br><span style='color:gray'>{step.limit}</span>"
            for step in self._plan.steps))
        self._refresh_notes()

    def _build_benchmark_box(self) -> QGroupBox:
        box = QGroupBox("Speed")
        layout = QVBoxLayout(box)

        self._run_btn = QPushButton("Time this computer")
        self._run_btn.setObjectName("primary")
        self._run_btn.setToolTip(
            "Times the real spike detector and the real network null models — "
            "the two things a run spends its time on — and reports a relative "
            "speed. Takes 10-20 seconds. Run it on two computers to see which "
            "should take the larger share of a batch.")
        self._run_btn.clicked.connect(self._on_run)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedWidth(160)
        self._progress.setVisible(False)

        row = QHBoxLayout()
        pin_width(self._run_btn, 170)
        row.addWidget(self._run_btn, 0)
        row.addWidget(self._progress, 0)
        # Without this the button takes the whole width whenever the progress
        # bar beside it is hidden, which is most of the time.
        row.addStretch(1)

        self._score = _body(
            "Not timed yet. A relative speed of 1.00 is roughly a mid-range "
            "2020s laptop; twice the number means twice the work per hour, so "
            "two computers' scores say how a batch should be split between "
            "them.")
        layout.addLayout(row)
        layout.addWidget(self._score)
        return box

    def _build_notes_box(self) -> QGroupBox:
        self._notes_box = QGroupBox("Worth knowing")
        layout = QVBoxLayout(self._notes_box)
        self._notes = _body("")
        layout.addWidget(self._notes)
        return self._notes_box

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        copy = QPushButton("Copy report")
        copy.setToolTip(
            "Put this page on the clipboard as plain text, to paste into an "
            "email or a bug report.")
        copy.clicked.connect(self._on_copy)
        refresh = QPushButton("Refresh")
        refresh.setToolTip(
            "Measure free memory again. It changes as other applications open "
            "and close, and the worker counts change with it.")
        refresh.clicked.connect(self._on_refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        row.addWidget(copy)
        row.addWidget(refresh)
        row.addWidget(self._status, 1)
        row.addWidget(close)
        return row

    # ── Behaviour ─────────────────────────────────────────────────────────────

    def _refresh_notes(self) -> None:
        warnings = self._plan.warnings
        self._notes_box.setVisible(bool(warnings))
        self._notes.setText("<br><br>".join(f"• {w}" for w in warnings))

    def _on_refresh(self) -> None:
        self._machine = describe_machine()
        self._plan = plan_work()
        self._render()
        self._status.setText(
            f"Re-read: {self._machine.ram_available_gb:.1f} GB free now.")

    def _on_run(self) -> None:
        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._score.setText("Timing spike detection and network null models…")
        self._worker = _BenchmarkThread()
        self._worker.progress.connect(
            lambda message: self._score.setText(message))
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, result) -> None:
        self._benchmark = result
        self._progress.setVisible(False)
        self._run_btn.setEnabled(True)
        self._score.setText(
            f"<b style='font-size:15px'>Relative speed {result.score:.2f}</b>"
            f"<br>{result.seconds:.1f} s in total — spike detection "
            f"{result.detection_s:.1f} s on {result.threads} thread(s), "
            f"network null models {result.network_s:.1f} s on "
            f"{result.processes} process(es)."
            f"<br><span style='color:gray'>{_reading(result)}</span>")

    def _on_failed(self, message: str) -> None:
        self._progress.setVisible(False)
        self._run_btn.setEnabled(True)
        self._score.setText(f"The timing run could not finish: {message}")

    def _on_copy(self) -> None:
        QApplication.clipboard().setText(self.report_text())
        self._status.setText("Report copied to the clipboard.")

    def report_text(self) -> str:
        """The plain-text report, as **Copy report** would put it on the clipboard."""
        return "\n".join(report_lines(self._machine, self._plan, self._benchmark))


def _reading(result) -> str:
    """One sentence saying which half of the work this computer is good at.

    A machine can be fast at one and slow at the other — detection is threads
    and memory bandwidth, null models are processes and raw core count — and
    knowing which tells you whether the complaint is about step 1 or step 4.
    """
    if result.detection_s <= 0 or result.network_s <= 0:
        return ""
    ratio = result.detection_s / result.network_s
    if ratio > 2.0:
        return ("Detection is the slower half here, which points at memory "
                "speed and at how many channels each recording has.")
    if ratio < 0.5:
        return ("The network models are the slower half here, which points at "
                "core count — steps 3 and 4 spread over recordings.")
    return "The two halves are balanced on this computer."


def _body(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label
