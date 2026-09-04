"""How much a run says about itself, and the log that decides it.

``Params.verbose_level`` used to be stored and never read: the GUI offered
three levels and every run printed the same thing. This is what makes the
setting mean something.

The levels are **additive**. ``Verbose`` adds to what ``Normal`` prints;
``Debug`` adds to both. Nothing is ever taken away, so turning the level up
cannot hide a warning and turning it down cannot hide a failure — the only
question is how much detail sits between the lines that always appear.

:class:`RunLog` is callable, so ``log("...")`` still means "print this at every
level" and the ~150 existing call sites did not have to change. What is new is
``log.detail(...)`` (Verbose and up) and ``log.debug(...)`` (Debug only). Any
function that is handed a plain callable — a worker collecting lines into a
list, a test passing ``print`` — can promote it with :func:`as_run_log`, which
leaves an existing :class:`RunLog` alone.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Iterable, Iterator

__all__ = [
    "VERBOSE_LEVELS", "RunLog", "as_run_log", "normalise_level",
    "format_elapsed",
]

#: The levels, quietest first, as the GUI offers them.
VERBOSE_LEVELS = ["Normal", "Verbose", "Debug"]

_RANK = {name: i for i, name in enumerate(VERBOSE_LEVELS)}

#: MATLAB's ``Params.verboseLevel`` is ``'Normal' | 'High' | 'Silent'``, and a
#: params file can come from either pipeline. Mapping the names it uses means
#: such a file keeps its intent instead of silently landing on the default.
#: 'Silent' has no equivalent here — every level prints the run's progress —
#: so it maps to the quietest one we have.
_ALIASES = {"high": "Verbose", "silent": "Normal", "none": "Normal"}


def normalise_level(level: str | None) -> str:
    """The canonical level name for whatever was stored, defaulting to Normal.

    Never raises: a params file is user-editable, and an unrecognised level is
    a reason to log normally, not a reason to lose the run.
    """
    text = str(level or "").strip().lower()
    for name in VERBOSE_LEVELS:
        if text == name.lower():
            return name
    return _ALIASES.get(text, VERBOSE_LEVELS[0])


def format_elapsed(seconds: float) -> str:
    """A short duration, keeping the decimals that matter for a single step."""
    seconds = max(0.0, float(seconds))
    if seconds < 10:
        return f"{seconds:.2f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class RunLog:
    """A run's log, with a detail channel and a debug channel above it.

    Wraps the callable the caller gave :func:`~meanap.pipeline.runner.run_pipeline`
    — the GUI's log pane, ``print``, a worker's ``list.append`` — and gates the
    two extra channels on the run's verbose level.
    """

    __slots__ = ("_out", "level", "_rank")

    def __init__(self, out: Callable[[str], None], level: str | None = None) -> None:
        self._out = out
        self.level = normalise_level(level)
        self._rank = _RANK[self.level]

    def __call__(self, message: str) -> None:
        """Print at every level. What ``log(...)`` has always meant."""
        self._out(message)

    # ── The two extra channels ────────────────────────────────────────────────

    @property
    def wants_detail(self) -> bool:
        """Whether ``detail`` would print — for skipping work only it needs."""
        return self._rank >= _RANK["Verbose"]

    @property
    def wants_debug(self) -> bool:
        return self._rank >= _RANK["Debug"]

    def detail(self, message: str) -> None:
        """The numbers behind a step: Verbose and above."""
        if self._rank >= _RANK["Verbose"]:
            self._out(message)

    def debug(self, message: str) -> None:
        """Internals — paths, shapes, workers, versions: Debug only."""
        if self._rank >= _RANK["Debug"]:
            self._out(message)

    def detail_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.detail(line)

    def debug_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.debug(line)

    @contextmanager
    def timed(self, label: str, *, level: str = "Verbose") -> Iterator[None]:
        """Time the block and say how long it took, at *level*.

        Silent — and free of the clock call — when the run is below *level*, so
        it can wrap anything without a Normal run paying for it.
        """
        if _RANK[normalise_level(level)] > self._rank:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            self._out(f"{label} took {format_elapsed(time.perf_counter() - started)}")


def as_run_log(log: Callable[[str], None], level: str | None = None) -> RunLog:
    """Promote a plain log callable to a :class:`RunLog`.

    An existing :class:`RunLog` is returned unchanged, level and all: it was
    built by whoever started the run, and a function further down the stack
    guessing a level from its own arguments is how the two would drift apart.
    """
    if isinstance(log, RunLog):
        return log
    return RunLog(log, level)
