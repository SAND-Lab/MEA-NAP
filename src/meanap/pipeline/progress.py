"""How far a run has got, and how much longer it has left.

A run is a few minutes to a few hours of near-silent work, and the status log
answers "is it alive?" without answering "should I go to lunch?". This turns the
same work into a fraction and an estimate.

**Why weights, and where they come from.** Counting recordings finished would
make the bar lurch: on the benchmark in ``python/PIPELINE_PORT_STATUS.md`` a
recording costs 3.2s in step 2 and 98.7s in step 4, a factor of thirty. So each
phase carries a weight — its measured share of a real run — and the bar tracks
weighted work, which is a proxy for time rather than for tasks.

**Why the estimate is calibrated, not predicted.** Those weights come from one
machine and one dataset, so their *absolute* scale means nothing here. What is
tracked instead is the ratio of wall-clock actually spent to nominal weight
consumed, and the estimate is the remaining weight times that ratio. Only the
relative sizes have to be right, the reading adapts to the machine it is on
within the first completed recording, and nothing has to be configured.

That also handles remote runs without modelling them. Downloads overlap
compute — :mod:`meanap.remote.prefetch` fetches the next recording while this
one is analysed — so adding transfer time to the total would double-count it.
Instead a slow link shows up as wall-clock spent per unit of weight, which is
exactly what the calibration measures. The transfer figures are reported
alongside, for the one stretch where there is genuinely nothing else happening:
the first recording, before any compute has started.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

__all__ = [
    "Progress", "ProgressFn", "RunProgress", "PHASE_WEIGHTS",
    "format_duration", "plan_ephys", "plan_catnap",
]

#: Relative cost of one recording in each phase, from the 3.3x-optimised
#: benchmark in ``python/PIPELINE_PORT_STATUS.md`` (2 recordings, 350s total):
#: step 1 103.6s, step 2 6.4s, step 3 42.7s, step 4 197.3s. Step 4 is split by
#: the express-mode measurement in ``docs/python/express-mode.md`` (159.0s full
#: vs 113.4s with plotting removed), which puts its plotting at ~29%.
#:
#: Only the ratios matter — :class:`RunProgress` calibrates the scale — so these
#: need re-deriving only if the *relative* cost of the steps changes.
PHASE_WEIGHTS: dict[str, float] = {
    "step1": 51.8,
    "step2": 3.2,
    "step3": 21.4,
    "step4.compute": 70.1,
    "step4.plot": 28.6,
    "stim": 20.0,
    # CAT-NAP has no separate benchmark. Adjacency + activity stats dominate its
    # compute phase and the trace/network figures its plotting phase, so it is
    # modelled on step 4's shape, which has the same compute-then-plot split.
    "catnap.compute": 70.1,
    "catnap.plot": 28.6,
    # Batch-level work: group comparison figures, CSV export, bundle writing.
    # One unit for the whole run rather than one per recording.
    "batch": 40.0,
}

#: What is left of a plotting phase in express mode. From the same table: step 2
#: falls from 7.7s to 0.0 and step 4's plotting from 45.6s to near nothing, since
#: express skips every figure that can be rebuilt from the bundle.
EXPRESS_PLOT_FACTOR = 0.12

#: Phases that are mostly drawing, and so mostly skipped in express mode.
_PLOT_PHASES = ("step2", "step4.plot", "catnap.plot", "batch")

#: Human labels, so a caller doesn't have to pass one at every call site.
PHASE_LABELS = {
    "step1": "Step 1 · Spike detection",
    "step2": "Step 2 · Neuronal activity",
    "step3": "Step 3 · Functional connectivity",
    "step4.compute": "Step 4 · Network metrics",
    "step4.plot": "Step 4 · Network figures",
    "stim": "Stimulation analysis",
    "catnap.compute": "CAT-NAP · Adjacency and activity",
    "catnap.plot": "CAT-NAP · Figures",
    "batch": "Batch comparisons",
}


def format_duration(seconds: float | None) -> str:
    """``None`` → "unknown"; otherwise a short human duration."""
    if seconds is None:
        return "unknown"
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def format_bytes(n: float) -> str:
    """MB below a gigabyte, GB above — the two units a dataset is talked about in."""
    if n < 1000 ** 3:
        return f"{n / 1e6:.0f} MB"
    return f"{n / 1e9:.2f} GB"


@dataclass(frozen=True)
class Progress:
    """One snapshot of a run, safe to hand across a thread boundary."""

    fraction: float           # 0..1 of the weighted work planned
    phase: str                # human label for what is running
    detail: str               # the recording, usually
    elapsed_s: float
    eta_s: float | None       # None until a completed unit calibrates it
    bytes_done: int = 0       # this run's transfers so far
    bytes_total: int = 0      # 0 when nothing has to be fetched
    transfer_detail: str = ""

    @property
    def percent(self) -> int:
        return int(round(100 * self.fraction))

    @property
    def transferring(self) -> bool:
        return self.bytes_total > 0

    def describe(self) -> str:
        """One line, for a log or a terminal."""
        parts = [f"{self.percent}%", self.phase]
        if self.detail:
            parts.append(self.detail)
        parts.append(f"{format_duration(self.elapsed_s)} elapsed")
        if self.eta_s is not None:
            parts.append(f"~{format_duration(self.eta_s)} left")
        return " · ".join(parts)


#: Called with each new snapshot. Must be cheap and must not raise.
ProgressFn = Callable[[Progress], None]


def plan_ephys(
    *, start_step: int, stop_step: int, n_recordings: int,
    stimulation: bool = False,
) -> dict[str, int]:
    """The phases an electrophysiology run will execute, and their item counts.

    Mirrors the step gating in :func:`~meanap.pipeline.runner.run_pipeline`; a
    phase that will be skipped must not be planned, or the bar stops short of
    the end.
    """
    plan: dict[str, int] = {}
    if start_step <= 1 <= stop_step:
        plan["step1"] = n_recordings
    if stimulation:
        plan["stim"] = n_recordings
    if start_step <= 2 <= stop_step:
        plan["step2"] = n_recordings
    if start_step <= 3 <= stop_step:
        plan["step3"] = n_recordings
    if start_step <= 4 <= stop_step:
        plan["step4.compute"] = n_recordings
        plan["step4.plot"] = n_recordings
        plan["batch"] = 1
    return plan


def plan_catnap(*, n_recordings: int) -> dict[str, int]:
    """The phases a CAT-NAP run will execute. It runs as one step, always."""
    return {
        "catnap.compute": n_recordings,
        "catnap.plot": n_recordings,
        "batch": 1,
    }


class RunProgress:
    """Accumulates completed work and reports a fraction and an estimate.

    Default-constructed it is a working no-op, so a step function can take one
    unconditionally instead of guarding every call site.
    """

    def __init__(
        self,
        emit: ProgressFn | None = None,
        *,
        express: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._emit = emit
        self._express = express
        self._clock = clock
        self._start = clock()

        self._weights: dict[str, float] = {}
        self._total = 0.0
        self._done = 0.0
        self._phase_key = ""
        self._phase_label = ""
        self._detail = ""
        self._items_done = 0
        self._items_total = 0
        self._phase_credited = 0.0
        self._bytes_done = 0
        self._bytes_total = 0
        self._transfer_detail = ""
        # Wall-clock at the moment the first phase started. The calibration
        # measures from here rather than from construction, so the setup before
        # any work begins — folder creation, the pre-flight listing — doesn't
        # inflate every estimate for the rest of the run. It must be the phase
        # *start* and not the first completion: measuring from the latter would
        # silently drop the first recording's own duration from the average,
        # which on a two-recording batch halves the estimate.
        self._measure_from: float | None = None

    # ── Planning ──────────────────────────────────────────────────────────────

    def plan(self, phases: dict[str, int]) -> None:
        """Declare the phases that will run, as ``{phase key: item count}``."""
        self._weights = {}
        for key, count in phases.items():
            self._weights[key] = self._weight(key) * max(0, count)
        self._total = sum(self._weights.values())

    def _weight(self, key: str) -> float:
        weight = PHASE_WEIGHTS.get(key, 1.0)
        if self._express and key in _PLOT_PHASES:
            weight *= EXPRESS_PLOT_FACTOR
        return weight

    def expect_transfer(self, total_bytes: int) -> None:
        """How much this run will fetch, when the source is remote."""
        self._bytes_total = max(0, int(total_bytes))
        self._publish()

    # ── Reporting work ────────────────────────────────────────────────────────

    def begin(self, key: str, label: str = "", items: int | None = None) -> None:
        """Enter a phase. Unplanned phases still display, but weigh nothing."""
        self._phase_key = key
        self._phase_label = label or PHASE_LABELS.get(key, key)
        self._items_done = 0
        self._items_total = items if items is not None else 0
        self._phase_credited = 0.0
        self._detail = ""
        if self._measure_from is None:
            self._measure_from = self._clock()
        self._publish()

    def item_done(self, detail: str = "") -> None:
        """One recording finished in the current phase."""
        self._items_done += 1
        self._detail = detail
        planned = self._weights.get(self._phase_key, 0.0)
        if not planned:
            self._publish()
            return
        # Credit against a target rather than by increments, so a phase can
        # never over-run its weight however many times this is called.
        share = (min(1.0, self._items_done / self._items_total)
                 if self._items_total else 1.0)
        self._credit(planned * share)

    def phase_done(self) -> None:
        """Credit whatever is left of the current phase.

        Recordings do get skipped — a missing raw file, no spike times to resume
        from — and the bar must still reach the end of the phase. Idempotent.
        """
        self._credit(self._weights.get(self._phase_key, 0.0))

    def _credit(self, target: float) -> None:
        """Bring the current phase's credited weight up to *target*."""
        delta = target - self._phase_credited
        self._phase_credited = max(self._phase_credited, target)
        if delta > 0:
            self._advance(delta)
        else:
            self._publish()

    def _advance(self, weight: float) -> None:
        self._done = min(self._total, self._done + weight)
        self._publish()

    def transferred(self, done: int, total: int = 0, detail: str = "") -> None:
        """Bytes fetched so far. *total* overrides the planned total if given."""
        self._bytes_done = max(self._bytes_done, int(done))
        if total:
            self._bytes_total = max(self._bytes_total, int(total))
        if detail:
            self._transfer_detail = detail
        self._publish()

    def finish(self) -> None:
        """The run is over; show it complete rather than at 97%."""
        self._done = self._total
        self._detail = ""
        self._phase_label = "Complete"
        self._publish()

    # ── Snapshot ──────────────────────────────────────────────────────────────

    @property
    def elapsed_s(self) -> float:
        return self._clock() - self._start

    def eta_s(self) -> float | None:
        """Seconds remaining, or ``None`` while there is nothing to calibrate on.

        A number invented from the benchmark alone would be a guess about a
        machine this has never run on; "estimating" is the honest reading until
        one unit of real work has been timed.
        """
        if self._total <= 0 or self._measure_from is None:
            return None
        if self._done <= 0:
            return None
        spent = self._clock() - self._measure_from
        if spent <= 0:
            return None
        remaining = self._total - self._done
        if remaining <= 0:
            return 0.0
        return remaining * (spent / self._done)

    def snapshot(self) -> Progress:
        fraction = (self._done / self._total) if self._total > 0 else 0.0
        detail = self._detail
        if self._items_total > 1 and self._items_done <= self._items_total:
            counter = f"{min(self._items_done + 1, self._items_total)}/{self._items_total}"
            detail = f"{detail} ({counter})" if detail else f"recording {counter}"
        return Progress(
            fraction=min(1.0, max(0.0, fraction)),
            phase=self._phase_label,
            detail=detail,
            elapsed_s=self.elapsed_s,
            eta_s=self.eta_s(),
            bytes_done=self._bytes_done,
            bytes_total=self._bytes_total,
            transfer_detail=self._transfer_detail,
        )

    def _publish(self) -> None:
        if self._emit is not None:
            self._emit(self.snapshot())
