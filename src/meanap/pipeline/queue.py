"""Running several analyses back to back, unattended.

A run takes minutes to hours, and until now the only way to do a second one was
to wait for the first, reconfigure, and start again — which means someone has to
be awake for every handover. The work itself is unattended; the *scheduling* was
not.

A queue is a list of saved parameter files. Each is a complete description of a
run, so they can differ in anything at all — different datasets, different
lags, different pipelines. Nothing here inspects them beyond reading them: a
CAT-NAP run and an electrophysiology run sit in the same queue because
:func:`~meanap.pipeline.runner.run_pipeline` already decides which path to take
from the parameters it is handed.

**One failure does not end the night.** Each run is caught individually and
recorded; the queue moves on. The point of leaving something running overnight
is to come back to results, and coming back to five results and one traceback is
better than coming back to one traceback.

**Cancellation is checked between runs as well as inside them.** Stopping the
queue while run three is going should not start run four, and the pipeline's own
cooperative cancellation handles the rest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from meanap.params import Params, load_params

__all__ = [
    "QueuedRun", "RunOutcome", "QueueResult",
    "load_queue", "run_queue", "summarise",
]

#: What a queued run ended up doing.
DONE, FAILED, CANCELLED, SKIPPED = "done", "failed", "cancelled", "skipped"


@dataclass
class QueuedRun:
    """One analysis waiting to run: its parameters, and where they came from."""

    params: Params
    #: The parameter file, when it was loaded from one. Shown in the GUI and in
    #: the summary, because "run 3 of 6" means nothing the next morning.
    source: Path | None = None
    #: Parameter keys the file carried that this version has no field for.
    unknown_keys: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        """A short name for this run, preferring what the user called it."""
        if self.params.output_data_folder_name:
            return self.params.output_data_folder_name
        if self.source is not None:
            return self.source.stem
        return "unnamed run"

    def describe(self) -> str:
        """One line saying what this run will actually do."""
        from meanap.gui.modes import MODES, mode_for_params

        mode = MODES[mode_for_params(self.params)].label
        steps = (f"steps {self.params.start_analysis_step}"
                 f"–{self.params.stop_analysis_step}")
        bits = [mode, steps]
        if self.params.express_mode:
            bits.append("express")
        if self.params.continue_interrupted:
            bits.append("continuing")
        return "  ·  ".join(bits)


@dataclass
class RunOutcome:
    """How one queued run finished."""

    run: QueuedRun
    status: str
    output: Path | None = None
    error: str = ""
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == DONE


@dataclass
class QueueResult:
    """How the whole queue finished."""

    outcomes: list[RunOutcome] = field(default_factory=list)

    @property
    def done(self) -> int:
        return sum(1 for o in self.outcomes if o.status == DONE)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.status == FAILED)

    @property
    def cancelled(self) -> int:
        return sum(1 for o in self.outcomes if o.status == CANCELLED)


def load_queue(paths: Iterable[Path | str]) -> list[QueuedRun]:
    """Read parameter files into queued runs.

    A file that will not load raises here rather than at 3am: the queue is
    checked in full before anything starts, so a typo'd path is a message now
    instead of a gap in the morning's results.
    """
    runs: list[QueuedRun] = []
    for entry in paths:
        path = Path(entry).expanduser()
        if not path.is_file():
            raise ValueError(f"Parameter file not found: {path}")
        try:
            params, unknown = load_params(path)
        except Exception as e:                            # noqa: BLE001
            raise ValueError(f"Could not read {path.name}: {e}") from e
        runs.append(QueuedRun(params=params, source=path,
                              unknown_keys=list(unknown)))
    return runs


def run_queue(
    runs: list[QueuedRun],
    log: Callable[[str], None] = print,
    should_cancel: Callable[[], bool] | None = None,
    progress: Callable[[int, QueuedRun, object], None] | None = None,
    on_finished: Callable[[RunOutcome], None] | None = None,
) -> QueueResult:
    """Run each of *runs* in turn, returning what each one did.

    ``progress`` is called as ``(index, run, snapshot)`` with the pipeline's own
    :class:`~meanap.pipeline.progress.Progress` for the run in flight, so a
    caller can show both "run 2 of 6" and how far into run 2 it is.

    ``on_finished`` is called with each outcome as it happens, which is what
    lets a UI mark runs off one by one rather than all at the end.
    """
    from meanap.pipeline.cancellation import PipelineCancelled
    from meanap.pipeline.runner import run_pipeline

    result = QueueResult()
    total = len(runs)

    for index, run in enumerate(runs):
        if should_cancel is not None and should_cancel():
            # Everything from here on is untouched, and says so rather than
            # being silently missing from the summary.
            for remaining in runs[index:]:
                outcome = RunOutcome(run=remaining, status=SKIPPED)
                result.outcomes.append(outcome)
                if on_finished is not None:
                    on_finished(outcome)
            break

        log(f"\n{'═' * 66}")
        log(f"Run {index + 1} of {total}: {run.label}")
        log(f"  {run.describe()}")
        if run.source is not None:
            log(f"  from {run.source}")
        if run.unknown_keys:
            log(f"  note: {len(run.unknown_keys)} setting(s) in this file are "
                f"not known to this version: {', '.join(run.unknown_keys[:5])}")
        log("═" * 66)

        started = time.perf_counter()
        try:
            output = run_pipeline(
                run.params, log=log, should_cancel=should_cancel,
                progress=(None if progress is None
                          else lambda snap, i=index, r=run: progress(i, r, snap)),
            )
        except PipelineCancelled:
            outcome = RunOutcome(run=run, status=CANCELLED,
                                 seconds=time.perf_counter() - started)
            log(f"Run {index + 1} stopped.")
        except Exception as e:                            # noqa: BLE001
            # Caught per run on purpose: the whole point of a queue left running
            # overnight is that one bad configuration costs one run.
            outcome = RunOutcome(run=run, status=FAILED, error=str(e),
                                 seconds=time.perf_counter() - started)
            log(f"Run {index + 1} FAILED: {e}")
            log("  The queue continues with the next run.")
        else:
            outcome = RunOutcome(run=run, status=DONE, output=output,
                                 seconds=time.perf_counter() - started)
            log(f"Run {index + 1} finished in "
                f"{_duration(outcome.seconds)} → {output}")

        result.outcomes.append(outcome)
        if on_finished is not None:
            on_finished(outcome)

    for line in summarise(result):
        log(line)
    return result


def summarise(result: QueueResult) -> list[str]:
    """The lines to end on: what ran, what didn't, and where the results are.

    Written for someone reading it the next morning, so every run is named and
    the failures say why rather than only that.
    """
    if not result.outcomes:
        return ["Nothing was queued."]

    lines = ["", "═" * 66, "Queue summary", "═" * 66]
    for i, outcome in enumerate(result.outcomes, start=1):
        mark = {DONE: "✓", FAILED: "✗", CANCELLED: "■", SKIPPED: "·"}[outcome.status]
        line = f"  {mark} {i}. {outcome.run.label}"
        if outcome.status == DONE:
            line += f"  ({_duration(outcome.seconds)})"
        elif outcome.status == SKIPPED:
            line += "  — not started"
        lines.append(line)
        if outcome.output is not None:
            lines.append(f"       → {outcome.output}")
        if outcome.error:
            lines.append(f"       {outcome.error}")

    total = len(result.outcomes)
    lines.append("")
    lines.append(f"  {result.done} of {total} completed"
                 + (f", {result.failed} failed" if result.failed else "")
                 + (f", {result.cancelled} stopped" if result.cancelled else ""))
    return lines


def _duration(seconds: float) -> str:
    from meanap.pipeline.progress import format_duration

    return format_duration(seconds)
