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

**Why each phase has its own rate.** The relative sizes are not right
everywhere, though: spike detection scales with recording length and channel
count, connectivity and network metrics with how many units are active, so a
long recording with few active channels spends far longer in step 1 than its
weight says and far less in step 4. One run-wide rate would then charge step
1's slowness to all of step 4 — an estimate that is too long all through
detection and a bar that races at the end. So the phase that is running is
estimated from its own measured rate, blended in over its first recording, and
only phases not yet reached fall back to the run-wide rate.

That also handles remote runs without modelling them. Downloads overlap
compute — :mod:`meanap.remote.prefetch` fetches the next recording while this
one is analysed — so adding transfer time to the total would double-count it.
Instead a slow link shows up as wall-clock spent per unit of weight, which is
exactly what the calibration measures. The transfer figures are reported
alongside, for the one stretch where there is genuinely nothing else happening:
the first recording, before any compute has started.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from meanap.pipeline.step_times import StepTimes

__all__ = [
    "Progress", "ProgressFn", "RunProgress", "PHASE_WEIGHTS",
    "format_duration", "plan_ephys", "plan_catnap",
]

#: Relative cost of one recording in each phase: seconds per recording on
#: ``ExampleData`` (two Axion64 recordings, 12.5 kHz) with the GUI's default
#: settings, measured per progress phase on 2026-11-12 with
#: ``RunProgress``'s own phase boundaries, full figures:
#:
#:     step 1 16.4s   step 2 6.6s   step 3 1.7s   step 4 compute 15.8s
#:     step 4 figures 29.4s   batch comparisons 27.6s   (wall 97s)
#:
#: The earlier benchmark these replaced had step 4 at twice step 1; the
#: numba/threading work since has made it about equal, which is why the old
#: weights crawled through detection and raced through step 4.
#:
#: Only the ratios matter — :class:`RunProgress` calibrates the scale, and each
#: phase is re-measured against its own pace as it runs — so these need
#: re-deriving only if the *relative* cost of the steps changes.
PHASE_WEIGHTS: dict[str, float] = {
    "step1": 8.6,
    "step2": 3.3,
    "step3": 0.8,
    "step4.compute": 7.8,
    "step4.plot": 14.7,
    # Not re-measured: kept at its old proportion to step 1.
    "stim": 3.3,
    # CAT-NAP has no separate benchmark. Adjacency + activity stats dominate its
    # compute phase and the trace/network figures its plotting phase, so it is
    # modelled on step 4's shape, which has the same compute-then-plot split.
    "catnap.compute": 7.8,
    "catnap.plot": 14.7,
    # Batch-level work: group comparison figures, CSV export, bundle writing.
    # One unit for the whole run rather than one per recording.
    "batch": 27.6,
}

#: What is left of a plotting phase in express mode. The same measurement in
#: express mode: step 2 6.6s → 0.04s, step 4 figures 29.4s → 0.02s, batch
#: comparisons 27.6s → 0.06s — under 1% each, since express skips every figure
#: that can be rebuilt from the bundle. Rounded up to 1% so the phases still
#: register.
EXPRESS_PLOT_FACTOR = 0.01

#: :mod:`meanap.shared.benchmark` on the machine the weights above were
#: measured on (2026-11-13, three runs within 0.04 s): its spike-detection and
#: network null-model parts. Another computer's benchmark against these says
#: how its detection and network steps compare with the benchmark machine's,
#: which the weights alone cannot know — a laptop with few cores loses more on
#: channel-threaded detection than on recording-parallel network metrics.
BENCHMARK_REFERENCE = {"detection_s": 0.32, "network_s": 2.32}

#: Seconds of step 1 per second of benchmark detection, per benchmark-sized
#: amount of recording (:data:`meanap.shared.benchmark.DETECTION_SAMPLES`
#: channel-samples). On the reference machine an ExampleData recording
#: (64 channels x 7.5M samples, 30 benchmark-sizes) took 8.6 s against the
#: benchmark's 0.32 s: 8.6 / (0.32 x 30) = 0.9. It covers loading and the
#: spike-check summaries as well as detection itself.
STEP1_PER_BENCHMARK = 0.9

#: The step-times key for step 1's measured seconds per channel-sample, which
#: replaces the benchmark's figure once a run here has detected spikes.
STEP1_RATE_KEY = "step1.per_channel_sample"

#: Which benchmark part each phase moves with. Phases that are neither (drawing,
#: activity statistics) move with both, as their geometric mean.
_DETECTION_PHASES = ("step1",)
_NETWORK_PHASES = ("step3", "step4.compute", "catnap.compute")

#: Phases done once per run rather than once per recording.
_PER_RUN_PHASES = ("batch",)

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
    def percent_text(self) -> str:
        """"0.4%" early on, "37%" later.

        Whole percents are too coarse at the start of a long batch: one
        recording's spike detection can be under a percent of the run, and a
        bar reading 0% for minutes looks stuck however hard it is working.
        """
        if 0 < self.fraction < 0.1:
            return f"{100 * self.fraction:.1f}%"
        return f"{self.percent}%"

    @property
    def transferring(self) -> bool:
        return self.bytes_total > 0

    def describe(self) -> str:
        """One line, for a log or a terminal."""
        parts = [self.percent_text, self.phase]
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
        times: "StepTimes | None" = None,
    ) -> None:
        self._emit = emit
        self._express = express
        # This computer's step times from earlier runs: planned with, and
        # added to when the run finishes (see meanap.pipeline.step_times).
        self._times = times
        self._phase_items: dict[str, int] = {}
        self._recorded = False
        # Seconds per unit of weight predicted before any work (see
        # expect_detection), and how much work it takes to stop needing it.
        self._prior_rate: float | None = None
        self._prior_until = 0.0
        self._detection_size: float | None = None
        self._detection_items = 0
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
        # item_progress is called from detection's worker threads.
        self._lock = threading.Lock()
        # Wall-clock at which the current phase began, and what earlier runs of
        # the same phase key spent and were credited (a key is rarely begun
        # twice, but nothing forbids it).
        self._phase_started: float | None = None
        self._phase_spent: dict[str, float] = {}
        self._phase_earned: dict[str, float] = {}
        # Recordings that will not be analysed at all (see skip), and what one
        # recording weighs in each planned phase, to take back out of the plan.
        self._skipped: set[str] = set()
        self._per_item: dict[str, float] = {}
        self._begun: set[str] = set()

    # ── Planning ──────────────────────────────────────────────────────────────

    def plan(self, phases: dict[str, int]) -> None:
        """Declare the phases that will run, as ``{phase key: item count}``."""
        weights = self._planning_weights(list(phases))
        self._weights = {}
        self._per_item = {}
        for key, count in phases.items():
            self._weights[key] = weights[key] * max(0, count)
            if key not in _PER_RUN_PHASES:
                self._per_item[key] = weights[key]
        self._total = sum(self._weights.values())

    def _planning_weights(self, keys: list[str]) -> dict[str, float]:
        """One recording's weight per phase: remembered here, else the benchmark's.

        Remembered figures are this computer's seconds; the benchmark's are
        another machine's. Mixed as they are, a computer three times slower
        would make its remembered phases look three times heavier than the
        rest, so the benchmark figures are first scaled by how this computer
        compares on the phases it does remember.
        """
        defaults = {key: self._weight(key) * self._speed_factor(key) for key in keys}
        if self._times is None:
            return defaults
        remembered = {key: self._times.seconds(self._memory_key(key)) for key in keys}
        ratios = sorted(remembered[k] / defaults[k] for k in keys
                        if remembered[k] and defaults[k] > 0)
        if not ratios:
            return defaults
        scale = ratios[len(ratios) // 2] if len(ratios) % 2 else (
            ratios[len(ratios) // 2 - 1] + ratios[len(ratios) // 2]) / 2
        return {key: remembered[key] or defaults[key] * scale for key in keys}

    def _speed_factor(self, key: str) -> float:
        """How much slower *key* runs here than on the benchmark machine, if known.

        Only the factors' ratios matter, so a uniformly slower computer gets
        the same weights; one slower at detection than at network work gets a
        heavier step 1.
        """
        bench = self._times.benchmark if self._times is not None else None
        if not bench:
            return 1.0
        detection = bench["detection_s"] / BENCHMARK_REFERENCE["detection_s"]
        network = bench["network_s"] / BENCHMARK_REFERENCE["network_s"]
        if key in _DETECTION_PHASES:
            return detection
        if key in _NETWORK_PHASES:
            return network
        return (detection * network) ** 0.5

    def expect_detection(self, channel_samples: float, recordings: int) -> None:
        """How much step 1 has to detect: an estimate before any work is done.

        *channel_samples* is the total over the *recordings* still to detect,
        read from their headers. With this computer's seconds per
        channel-sample — measured by an earlier run, else derived from its
        benchmark — that is step 1's duration, and through the weights the
        whole run's. Without either, the estimate waits for real work as
        before. The prediction gives way to the run's own pace over its first
        recording.
        """
        if channel_samples <= 0 or recordings <= 0:
            return
        self._detection_size = float(channel_samples)
        self._detection_items = recordings
        per_sample = self._times.seconds(STEP1_RATE_KEY) if self._times is not None else None
        bench = self._times.benchmark if self._times is not None else None
        if per_sample is None and bench:
            from meanap.shared.benchmark import DETECTION_SAMPLES

            per_sample = bench["detection_s"] * STEP1_PER_BENCHMARK / DETECTION_SAMPLES
        one = self._per_item.get("step1", 0.0)
        if per_sample is None or one <= 0:
            return
        self._prior_rate = per_sample * channel_samples / (recordings * one)
        self._prior_until = one
        self._publish()

    def _memory_key(self, key: str) -> str:
        """Express mode all but removes the drawing phases, so they are kept apart."""
        if key in _PLOT_PHASES:
            return f"{key}@{'express' if self._express else 'full'}"
        return key

    def _close_phase(self, now: float) -> None:
        """Add the running phase's time, credit and recordings to its totals."""
        if self._phase_started is None or not self._phase_key:
            return
        key = self._phase_key
        self._phase_spent[key] = self._phase_spent.get(key, 0.0) + now - self._phase_started
        self._phase_earned[key] = self._phase_earned.get(key, 0.0) + self._phase_credited
        self._phase_items[key] = self._phase_items.get(key, 0) + self._items_done
        self._phase_started = None

    def measured(self) -> dict[str, float]:
        """Seconds per recording each finished planned phase took, by memory key."""
        out: dict[str, float] = {}
        done = self._phase_items.get("step1", 0)
        if self._detection_size and done and "step1" in self._weights:
            # Per channel-sample, assuming the recordings that ran were of the
            # average size of those expected.
            size = self._detection_size * min(1.0, done / self._detection_items)
            out[STEP1_RATE_KEY] = self._phase_spent.get("step1", 0.0) / size
        for key, items in self._phase_items.items():
            if key in _PER_RUN_PHASES and self._phase_spent.get(key, 0.0) > 0:
                items = 1  # done once whatever it reports, per run not per recording
            if key in self._weights and items > 0:
                out[self._memory_key(key)] = self._phase_spent.get(key, 0.0) / items
        return out

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
        now = self._clock()
        self._close_phase(now)
        self._phase_started = now
        self._phase_key = key
        self._begun.add(key)
        self._phase_label = label or PHASE_LABELS.get(key, key)
        self._items_done = 0
        self._items_total = items if items is not None else 0
        if key in self._per_item:
            # The step still loops over every recording in the sheet; the ones
            # already known to be missing are not work.
            self._items_total = max(0, self._items_total - len(self._skipped))
        self._phase_credited = 0.0
        self._detail = ""
        if self._measure_from is None:
            self._measure_from = self._clock()
        self._publish()

    def skip(self, recording: str) -> None:
        """*recording* will not be analysed, in this phase or any later one.

        A spreadsheet can list recordings whose raw files are not in the
        folder — the example dataset lists sixty and ships two. Planned as
        work, they would make each real recording a sixtieth of the bar, with
        the rest arriving in one jump at the end of each step. Idempotent;
        later reports for a skipped recording are ignored.
        """
        with self._lock:
            if recording in self._skipped:
                return
            self._skipped.add(recording)
            for key, one in self._per_item.items():
                current = key == self._phase_key
                if key in self._begun and not current:
                    continue  # already done and credited
                self._weights[key] = max(0.0, self._weights.get(key, 0.0) - one)
                if current:
                    self._items_total = max(0, self._items_total - 1)
            self._total = sum(self._weights.values())
            self._done = min(self._done, self._total)
            self._publish()

    def item_done(self, detail: str = "") -> None:
        """One recording finished in the current phase."""
        if detail in self._skipped:
            return
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

    def item_progress(self, fraction: float, detail: str | None = None) -> None:
        """Part of the current item is done: *fraction* of it, 0 to 1.

        For items long enough that waiting for the whole one leaves the bar
        still — a recording's spike detection is minutes, and on a small batch
        the whole of step 1's first recording. Never moves the bar back, and
        never past the item: :meth:`item_done` still marks the item finished.
        Safe to call from several threads at once.
        """
        with self._lock:
            if detail is not None:
                self._detail = detail
            planned = self._weights.get(self._phase_key, 0.0)
            if not planned or not self._items_total:
                self._publish()
                return
            share = (self._items_done + min(1.0, max(0.0, fraction))) / self._items_total
            self._credit(planned * min(1.0, share))

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
        """The run is over; show it complete rather than at 97%.

        Also the one point a run's step times are remembered: a run that
        stopped part-way, by cancelling or failing, never gets here.
        """
        self._close_phase(self._clock())
        if self._times is not None and not self._recorded:
            self._recorded = True
            self._times.record(self.measured())
        self._done = self._total
        self._detail = ""
        self._phase_label = "Complete"
        self._publish()

    # ── Snapshot ──────────────────────────────────────────────────────────────

    @property
    def elapsed_s(self) -> float:
        return self._clock() - self._start

    def eta_s(self) -> float | None:
        """Seconds remaining, or ``None`` while there is nothing to go on.

        Before any work is done there is a number only if the recordings' size
        and this computer's detection speed are known (:meth:`expect_detection`);
        otherwise "estimating" is the honest reading until one unit of real
        work has been timed. Once work is being timed, the run's own pace takes
        over from the prediction across the first recording.
        """
        if self._total <= 0 or self._measure_from is None:
            return None
        remaining = self._total - self._done
        if self._done <= 0:
            if self._prior_rate is None:
                return None
            return remaining * self._prior_rate
        spent = self._clock() - self._measure_from
        if spent <= 0:
            return None
        if remaining <= 0:
            return 0.0
        overall = spent / self._done
        if self._prior_rate is not None and self._prior_until > 0:
            trust = min(1.0, self._done / self._prior_until)
            overall = trust * overall + (1.0 - trust) * self._prior_rate
        current = self._weights.get(self._phase_key, 0.0)
        left_here = max(0.0, current - self._phase_credited) if current else 0.0
        return (remaining - left_here) * overall + left_here * self._phase_rate(overall)

    def _phase_rate(self, overall: float) -> float:
        """Seconds per unit of weight in the running phase.

        Its own measurement once it has done a recording's worth of work, the
        run-wide rate before it has done any, and a blend in between — the
        first moments of a phase (loading a file, warming a cache) say little
        about its pace, and a rate from a sliver of work would swing wildly.
        """
        key = self._phase_key
        earned = self._phase_earned.get(key, 0.0) + self._phase_credited
        if earned <= 0 or self._phase_started is None:
            return overall
        spent = self._phase_spent.get(key, 0.0) + self._clock() - self._phase_started
        own = spent / earned
        one_item = self._weights.get(key, 0.0) / max(1, self._items_total)
        trust = min(1.0, earned / one_item) if one_item > 0 else 1.0
        return trust * own + (1.0 - trust) * overall

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
