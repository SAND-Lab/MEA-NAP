"""Packing a finished run into a bundle, off the GUI thread.

Zipping an output folder is a couple of seconds on the example dataset and can
be a minute on a large batch — long enough that doing it in the GUI thread
would freeze the window mid-click, short enough that it does not want a
progress bar and a cancel button of its own.

So it takes the same shape as :mod:`meanap.gui.stats_worker`: a ``QThread``
that logs as it goes and ends by emitting either the result or the failure.
There is no cancellation, for the same reason the statistics step has none —
there is nothing to stop it at. The one destructive moment, deleting a bundle
that will not read back, is inside :func:`~meanap.pipeline.pack.bundle_output_folder`
and finishes in milliseconds.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

__all__ = ["BundleWorker"]


class BundleWorker(QThread):
    """Pack *source* into *dest*, reporting progress through signals."""

    log_message = pyqtSignal(str)
    #: The :class:`~meanap.pipeline.pack.BundleResult` — passed as ``object``
    #: because Qt signals carry only registered types.
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, source: Path, dest: Path | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._source = Path(source)
        self._dest = Path(dest) if dest is not None else None

    def run(self) -> None:  # noqa: D102 - QThread entry point
        # Imported here rather than at module scope: the packer pulls in the
        # renderer to read a folder's recording table, and the GUI should not
        # pay for that at import time when most sessions never pack anything.
        from meanap.pipeline.pack import bundle_output_folder

        try:
            result = bundle_output_folder(
                self._source, self._dest, log=self.log_message.emit)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(result)
