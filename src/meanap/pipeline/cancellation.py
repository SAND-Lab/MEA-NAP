"""Cooperative cancellation for pipeline runs.

The pipeline is long-running (spike detection + probabilistic thresholding can
take minutes). To let the GUI's Stop button actually interrupt a run, each step
periodically calls ``check_cancel(should_cancel)`` — typically once per
recording — which raises :class:`PipelineCancelled` when the caller's
``should_cancel`` predicate returns ``True``. This unwinds cleanly back to
``run_pipeline``'s caller, which is expected to treat it as a normal stop rather
than an error.

Lives in its own module (importing nothing from the rest of the package) so both
``runner`` and the individual ``stepN`` modules can import it without creating a
circular import.
"""

from __future__ import annotations

from typing import Callable, Optional

CancelCheck = Optional[Callable[[], bool]]


class PipelineCancelled(Exception):
    """Raised to unwind the pipeline when the user requests cancellation."""


def check_cancel(should_cancel: CancelCheck) -> None:
    """Raise :class:`PipelineCancelled` if ``should_cancel`` reports cancellation."""
    if should_cancel is not None and should_cancel():
        raise PipelineCancelled()
