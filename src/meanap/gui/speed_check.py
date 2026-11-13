"""The one-off benchmark the GUI runs on a computer's first launch.

See :meth:`meanap.gui.main_window.MainWindow.start_speed_check`. The result is
handed back rather than kept here, so the window can drop it if a run started
while it was timing — a busy computer's benchmark would mislead every estimate
after it.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

__all__ = ["SpeedCheck"]


class SpeedCheck(QThread):
    """Runs :func:`meanap.shared.benchmark.run_benchmark` off the UI thread."""

    #: The :class:`~meanap.shared.benchmark.BenchmarkResult`, or ``None`` if it
    #: failed or was discarded.
    finished_check = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        #: Set when the window closes mid-check: the result is then not wanted.
        self.discard = False

    def run(self) -> None:  # noqa: D401 - QThread entry point
        from meanap.shared.benchmark import run_benchmark

        try:
            result = run_benchmark(remember=False)
        except Exception:                                   # noqa: BLE001
            result = None  # a convenience; failing it is not worth a message
        self.finished_check.emit(None if self.discard else result)
