"""Reading a run for the results viewer without freezing the window.

Opening a bundle unpacks it and lists every figure it can draw; on a large
batch that takes seconds, longer on a slow laptop, and done on the GUI thread
it looked like the program had hung. :func:`read_run` does the reading on a
worker thread and, if it is not done almost at once, shows a busy dialog that
says which stage it is at. It still returns only when the run is read, so its
callers stay as simple as before.
"""

from __future__ import annotations

import threading
from pathlib import Path

__all__ = ["read_run"]

#: Below this a dialog would only flash.
QUIET_S = 0.3


def read_run(source: Path, parent=None):
    """``(service, manifest)`` for *source*, read on a worker thread.

    Raises whatever reading it raised (``ValueError`` for an unreadable run).
    """
    from PyQt6.QtCore import QEventLoop, Qt, QTimer
    from PyQt6.QtWidgets import QProgressDialog

    from meanap.pipeline.bundle import is_bundle
    from meanap.viewer.server import ViewerService

    source = Path(source)
    state = {"stage": "Unpacking" if is_bundle(source) else "Reading"}

    def work() -> None:
        try:
            service = ViewerService(source)
            state["stage"] = "Listing the figures in"
            state["result"] = (service, service.manifest())
        except BaseException as e:  # noqa: BLE001 - re-raised on the GUI thread
            state["error"] = e

    thread = threading.Thread(target=work, name="meanap-read-run", daemon=True)
    thread.start()
    thread.join(QUIET_S)
    if thread.is_alive():
        dialog = QProgressDialog(parent)
        dialog.setWindowTitle("Opening results")
        dialog.setCancelButton(None)
        dialog.setRange(0, 0)                 # busy: the stages have no known length
        dialog.setMinimumDuration(0)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setMinimumWidth(380)

        def label() -> str:
            return f"{state['stage']} {source.name}…"

        dialog.setLabelText(label())
        dialog.show()
        loop = QEventLoop()
        timer = QTimer()

        def poll() -> None:
            if not thread.is_alive():
                loop.quit()
            elif dialog.labelText() != label():
                dialog.setLabelText(label())

        timer.timeout.connect(poll)
        timer.start(50)
        loop.exec()
        timer.stop()
        dialog.close()
        dialog.deleteLater()
    thread.join()
    if "error" in state:
        raise state["error"]
    return state["result"]
