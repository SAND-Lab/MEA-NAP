"""A run's elapsed time and time left, kept moving between progress reports.

The pipeline reports progress when something finishes — a recording, a step —
which can be minutes apart. A display that only changes then reads as stuck:
the elapsed time sits still and then jumps. :class:`RunClock` takes each
report's elapsed time and estimate, and ticks once a second in between,
counting elapsed time up and time left down from the last report.
"""

from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from meanap.pipeline.progress import format_duration

__all__ = ["RunClock", "timing_text"]

#: Below this, a countdown says the run should be done shortly rather than
#: sitting on "0s" — an estimate that runs out has not stopped the run.
DONE_SHORTLY_S = 1.0


def timing_text(elapsed_s: float, eta_s: float | None) -> str:
    """"3m 05s elapsed  ·  about 2m 10s left", as both views show it."""
    elapsed = format_duration(elapsed_s)
    if eta_s is None:
        return f"{elapsed} elapsed  ·  estimating time left…"
    if eta_s < DONE_SHORTLY_S:
        return f"{elapsed} elapsed  ·  should be done shortly"
    return f"{elapsed} elapsed  ·  about {format_duration(eta_s)} left"


class RunClock(QObject):
    """Elapsed time and time left, as of now rather than as of the last report.

    *now* is injectable so tests need not wait for real seconds to pass.
    """

    #: Once a second while running, and on every report.
    ticked = pyqtSignal()

    def __init__(self, parent: QObject | None = None,
                 now: Callable[[], float] = time.monotonic) -> None:
        super().__init__(parent)
        self._now = now
        self._elapsed = 0.0
        self._eta: float | None = None
        self._at = now()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.ticked)

    def start(self) -> None:
        """A run has begun: count from zero, with no estimate yet."""
        self._elapsed, self._eta, self._at = 0.0, None, self._now()
        self._timer.start()
        self.ticked.emit()

    def report(self, elapsed_s: float, eta_s: float | None) -> None:
        """A progress report: the pipeline's own figures replace the count."""
        self._elapsed, self._eta, self._at = float(elapsed_s), eta_s, self._now()
        if not self._timer.isActive():
            self._timer.start()
        self.ticked.emit()

    def stop(self) -> None:
        self._timer.stop()

    def running(self) -> bool:
        return self._timer.isActive()

    def elapsed(self) -> float:
        since = self._now() - self._at if self.running() else 0.0
        return self._elapsed + since

    def eta(self) -> float | None:
        if self._eta is None:
            return None
        since = self._now() - self._at if self.running() else 0.0
        return max(0.0, self._eta - since)

    def text(self) -> str:
        return timing_text(self.elapsed(), self.eta())
