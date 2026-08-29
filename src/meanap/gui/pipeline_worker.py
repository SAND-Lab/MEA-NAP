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
    #: A :class:`~meanap.pipeline.progress.Progress` snapshot. The pipeline
    #: calls back on this thread; emitting it as a signal is what gets it onto
    #: the UI thread, so the receiving slot may touch widgets freely.
    progress = pyqtSignal(object)
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
                progress=self.progress.emit,
            )
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as exc:  # surface any failure to the UI as a message
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(output_root)


class QueueWorker(QThread):
    """Runs a queue of saved analyses in the background.

    Separate from :class:`PipelineWorker` rather than a mode of it: this owns a
    *list* of runs and has to report which one is in flight, and folding both
    into one class would mean every signal carrying an index the single-run case
    never uses.
    """

    log_message = pyqtSignal(str)
    #: ``(index, label, Progress)`` for the run currently going.
    progress = pyqtSignal(int, str, object)
    #: ``(index, status)`` as each run ends — see meanap.pipeline.queue.
    run_finished = pyqtSignal(int, str)
    #: The whole queue is done; carries a one-line summary.
    finished_all = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, paths, parent=None) -> None:
        super().__init__(parent)
        self._paths = list(paths)
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Stop after the current run reaches its next checkpoint."""
        self._cancel_requested = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        from meanap.pipeline.queue import load_queue, run_queue

        try:
            runs = load_queue(self._paths)
        except ValueError as e:
            # Bad input is worth refusing before anything starts, so the person
            # who set this up at 6pm hears about it at 6pm.
            self.failed.emit(str(e))
            return

        index = {"of": 0}

        def finished(outcome) -> None:
            self.run_finished.emit(index["of"], outcome.status)
            index["of"] += 1

        try:
            result = run_queue(
                runs,
                log=self.log_message.emit,
                should_cancel=lambda: self._cancel_requested,
                progress=lambda i, run, snap: self.progress.emit(
                    i, run.label, snap),
                on_finished=finished,
            )
        except Exception as exc:                          # noqa: BLE001
            self.failed.emit(str(exc))
            return

        total = len(result.outcomes)
        summary = f"{result.done} of {total} completed"
        if result.failed:
            summary += f", {result.failed} failed"
        if result.cancelled or any(o.status == "skipped" for o in result.outcomes):
            summary += ", stopped early"
        self.finished_all.emit(summary)


class SharedMainWorker(QThread):
    """The main computer's side of a shared run, in the background.

    Its own share, the wait for the helpers, the pooling, the batch-wide run
    — see :func:`meanap.shared.roles.run_main`. Two requests can come from
    the UI: ``request_cancel`` (Stop) and ``request_finish_now`` (stop waiting
    for the others; whatever they have not done is analysed here).
    """

    log_message = pyqtSignal(str)
    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)  # the pooled output root: Path
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, workspace, machine_name: str, output_folder: str,
                 output_name: str, raw_data: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._ws = workspace
        self._name = machine_name
        self._output_folder = output_folder
        self._output_name = output_name
        self._raw_data = raw_data
        self._cancel_requested = False
        self._finish_now = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def request_finish_now(self) -> None:
        self._finish_now = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        from meanap.shared.roles import run_main

        try:
            root = run_main(
                self._ws, self._name,
                output_data_folder=self._output_folder,
                output_data_folder_name=self._output_name,
                raw_data=self._raw_data,
                log=self.log_message.emit,
                should_cancel=lambda: self._cancel_requested,
                progress=self.progress.emit,
                finish_now=lambda: self._finish_now,
            )
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as exc:                          # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(root)


class SharedHelperWorker(QThread):
    """A helper's side of a shared run: wait to be started, do the share."""

    log_message = pyqtSignal(str)
    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(str)     # the machine's final status
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, workspace, machine_name: str, raw_data: str | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._ws = workspace
        self._name = machine_name
        self._raw_data = raw_data
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        from meanap.shared.roles import run_helper

        try:
            status = run_helper(
                self._ws, self._name, raw_data=self._raw_data,
                log=self.log_message.emit,
                should_cancel=lambda: self._cancel_requested,
                progress=self.progress.emit,
            )
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as exc:                          # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(status)
