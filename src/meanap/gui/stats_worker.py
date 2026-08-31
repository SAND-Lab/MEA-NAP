"""Background worker for the statistics and machine-learning step.

Separate from :class:`~meanap.gui.pipeline_worker.PipelineWorker` because it
runs something else entirely — :func:`meanap.stats.run.run_stats` against a
finished run rather than the pipeline against raw recordings — and reports a
different outcome (a results folder and a digest of what it found). The step
takes tens of seconds to a few minutes: enough that running it on the UI thread
would freeze the window through every permutation.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from meanap.stats.run import StatsSettings, run_stats


class StatsWorker(QThread):
    """Runs the stats step in the background.

    Exactly one of ``finished_ok`` / ``failed`` is emitted when it ends;
    ``log_message`` may be emitted many times first.
    """

    log_message = pyqtSignal(str)
    #: ``StatsRunResult`` for a completed run.
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, source: Path, dest: Path | None, settings: StatsSettings,
                 parent=None) -> None:
        super().__init__(parent)
        self._source = Path(source)
        self._dest = Path(dest) if dest is not None else None
        self._settings = settings

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            result = run_stats(
                self._source, dest=self._dest, settings=self._settings,
                log=self.log_message.emit)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(result)
