"""Background worker that runs the pipeline off the Qt UI thread.

``run_pipeline`` is CPU-bound and can take several minutes (wavelet spike
detection, probabilistic thresholding, null-model randomization). Running it on
the UI thread froze the window and made the Stop button cosmetic. This
:class:`QThread` runs it in the background instead, forwarding log lines and the
final outcome back to the UI thread through Qt signals (which are delivered on
the receiver's thread automatically), and exposes a cooperative
``request_cancel`` that the pipeline polls at step / recording boundaries.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from meanap.params import Params
from meanap.pipeline.cancellation import PipelineCancelled
from meanap.pipeline.runner import run_pipeline


class PipelineWorker(QThread):
    """Runs ``run_pipeline`` in a background thread.

    Exactly one of ``finished_ok`` / ``cancelled`` / ``failed`` is emitted when
    the run ends. ``log_message`` may be emitted many times before that.
    """

    log_message = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # output_root: Path
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, params: Params, parent=None) -> None:
        super().__init__(parent)
        self._params = params
        # Plain bool flipped from the UI thread and read from the worker thread.
        # CPython attribute reads/writes are atomic, and the pipeline only reads
        # it, so no lock is needed for this one-way signal.
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Ask the running pipeline to stop at its next cancellation checkpoint."""
        self._cancel_requested = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            output_root = run_pipeline(
                self._params,
                log=self.log_message.emit,
                should_cancel=lambda: self._cancel_requested,
            )
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as exc:  # surface any failure to the UI as a message
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(output_root)
