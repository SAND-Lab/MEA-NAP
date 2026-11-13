"""Test the run progress model and its display.

Run from the repo root::

    uv run python python/test_progress.py

The clock is injected, so every timing assertion here is exact rather than
flaky. What matters is not that a number appears but that it is *right*: an
estimate that is confidently wrong is worse than none, and the failure modes
are specific — a bar that goes backwards, one that stalls when recordings are
skipped, one that finishes at 94%, and an ETA that quietly drops the first
recording's own duration out of its average.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Runs here are tests, not this computer's history: never remember their step times.
os.environ["MEANAP_STEP_TIMES"] = "off"

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.pipeline.progress import (  # noqa: E402
    PHASE_WEIGHTS, Progress, RunProgress, format_bytes, format_duration,
    plan_catnap, plan_ephys,
)

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


class Clock:
    """A hand-wound monotonic clock."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def tick(self, seconds: float) -> None:
        self.t += seconds


def _reporter(**kw) -> tuple[RunProgress, list[Progress], Clock]:
    clock = Clock()
    seen: list[Progress] = []
    return RunProgress(seen.append, clock=clock, **kw), seen, clock


# ── Planning ──────────────────────────────────────────────────────────────────

def _plan_checks() -> list[Check]:
    checks: list[Check] = []

    full = plan_ephys(start_step=1, stop_step=4, n_recordings=3)
    checks.append(("a full run plans every phase",
                   set(full) == {"step1", "step2", "step3", "step4.compute",
                                 "step4.plot", "batch"},
                   str(sorted(full))))
    checks.append(("each phase covers every recording",
                   all(v == 3 for k, v in full.items() if k != "batch")
                   and full["batch"] == 1, str(full)))

    partial = plan_ephys(start_step=3, stop_step=4, n_recordings=2)
    checks.append(("a partial run plans only the steps that will run",
                   set(partial) == {"step3", "step4.compute", "step4.plot", "batch"},
                   str(sorted(partial))))
    checks.append(("stim analysis is planned only when it is on",
                   "stim" not in full
                   and "stim" in plan_ephys(start_step=1, stop_step=4,
                                            n_recordings=2, stimulation=True), ""))
    checks.append(("CAT-NAP plans its own two phases",
                   set(plan_catnap(n_recordings=4))
                   == {"catnap.compute", "catnap.plot", "batch"}, ""))

    # A bar that weighted every recording equally would sit at 50% while the
    # slowest step of the run was still entirely ahead of it.
    express = RunProgress(express=True)
    weights = {k: express._weight(k) for k in
               ("step1", "step2", "step3", "step4.compute", "step4.plot")}
    heavy = weights["step1"] + weights["step4.compute"]
    checks.append(("in express mode, detection and network metrics are most of a run",
                   heavy > 0.85 * sum(weights.values()), str(weights)))
    checks.append(("and detection is no lighter than network metrics, as measured",
                   weights["step1"] >= weights["step4.compute"], str(weights)))
    return checks


# ── The model ─────────────────────────────────────────────────────────────────

def _model_checks() -> list[Check]:
    checks: list[Check] = []

    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=4, n_recordings=2))
    total = 2 * (PHASE_WEIGHTS["step1"] + PHASE_WEIGHTS["step2"]
                 + PHASE_WEIGHTS["step3"] + PHASE_WEIGHTS["step4.compute"]
                 + PHASE_WEIGHTS["step4.plot"]) + PHASE_WEIGHTS["batch"]

    checks.append(("nothing is reported before a phase begins",
                   seen == [], str(len(seen))))

    p.begin("step1", items=2)
    checks.append(("beginning a phase reports it, at zero",
                   seen[-1].fraction == 0.0 and "Spike detection" in seen[-1].phase,
                   seen[-1].phase))
    checks.append(("no estimate exists before any work is done",
                   seen[-1].eta_s is None, str(seen[-1].eta_s)))

    clock.tick(10)
    p.item_done("rec_a")
    expected = PHASE_WEIGHTS["step1"] / total
    checks.append(("one recording of two credits half the phase's weight",
                   abs(seen[-1].fraction - expected) < 1e-9,
                   f"{seen[-1].fraction:.4f} vs {expected:.4f}"))

    clock.tick(10)
    p.item_done("rec_b")
    # 20s bought 2×51.8 = 103.6 of weight, so the rest costs
    # (total - 103.6) × 20/103.6.
    done = 2 * PHASE_WEIGHTS["step1"]
    want = (total - done) * (20 / done)
    checks.append(("the estimate extrapolates from measured wall-clock",
                   abs(seen[-1].eta_s - want) < 1e-6,
                   f"{seen[-1].eta_s:.1f} vs {want:.1f}"))
    checks.append(("and counts the first recording's own duration",
                   # Measuring from the first *completion* would halve this.
                   seen[-1].eta_s > 0.9 * want, f"{seen[-1].eta_s:.1f}"))

    # Skipped recordings must not strand the bar mid-phase.
    p.begin("step2", items=2)
    clock.tick(1)
    p.item_done("rec_a")          # rec_b skipped: no spike file
    p.phase_done()
    after = (2 * PHASE_WEIGHTS["step1"] + 2 * PHASE_WEIGHTS["step2"]) / total
    checks.append(("a phase that skipped a recording still completes",
                   abs(seen[-1].fraction - after) < 1e-9,
                   f"{seen[-1].fraction:.4f} vs {after:.4f}"))
    p.phase_done()
    checks.append(("completing a phase twice does not double-count",
                   abs(seen[-1].fraction - after) < 1e-9, f"{seen[-1].fraction:.4f}"))

    # More completions than planned (a phase re-run, a bad count) must not
    # push the phase past its own weight.
    p.begin("step3", items=1)
    p.item_done("rec_a")
    p.item_done("rec_b")
    ceiling = (2 * PHASE_WEIGHTS["step1"] + 2 * PHASE_WEIGHTS["step2"]
               + 2 * PHASE_WEIGHTS["step3"]) / total
    checks.append(("a phase can never over-run its own weight",
                   abs(seen[-1].fraction - ceiling) < 1e-9,
                   f"{seen[-1].fraction:.4f} vs {ceiling:.4f}"))

    fractions = [s.fraction for s in seen]
    checks.append(("the bar never goes backwards",
                   all(b >= a - 1e-12 for a, b in zip(fractions, fractions[1:])), ""))

    p.finish()
    checks.append(("a finished run reads 100%, not 94%",
                   seen[-1].fraction == 1.0 and seen[-1].eta_s == 0.0,
                   f"{seen[-1].fraction} / {seen[-1].eta_s}"))
    return checks


def _calibration_checks() -> list[Check]:
    """The estimate must track the machine, not the benchmark it was tuned on."""
    checks: list[Check] = []

    # Two identical plans; one machine ten times slower than the other. The
    # weights are the same, so only the measured rate can tell them apart.
    etas = []
    for pace in (1.0, 10.0):
        p, seen, clock = _reporter()
        p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=4))
        p.begin("step1", items=4)
        clock.tick(pace)
        p.item_done("a")
        etas.append(seen[-1].eta_s)
    checks.append(("a slower machine reports a proportionally longer estimate",
                   abs(etas[1] - 10 * etas[0]) < 1e-6,
                   f"{etas[0]:.1f} then {etas[1]:.1f}"))
    checks.append(("with 1 of 4 done, the estimate is 3 more units' worth",
                   abs(etas[0] - 3.0) < 1e-6, f"{etas[0]:.3f}"))

    # Setup before the first phase (folder creation, pre-flight listing) is not
    # work, and must not be charged to the rate.
    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=2))
    clock.tick(600)                      # a long pre-flight
    p.begin("step1", items=2)
    clock.tick(10)
    p.item_done("a")
    checks.append(("setup before the first phase is not charged to the rate",
                   abs(seen[-1].eta_s - 10.0) < 1e-6, f"{seen[-1].eta_s:.1f}"))
    checks.append(("but it still counts as elapsed time",
                   abs(seen[-1].elapsed_s - 610.0) < 1e-6,
                   f"{seen[-1].elapsed_s:.1f}"))

    # Each phase at its own pace: slow detection must not make the rest of a
    # quick step 4 look slow once step 4 has shown its own speed.
    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=4, n_recordings=2))
    w = PHASE_WEIGHTS
    p.begin("step1", items=2)
    clock.tick(300); p.item_done("a")
    clock.tick(300); p.item_done("b")
    p.phase_done()
    for key in ("step2", "step3"):
        p.begin(key, items=2)
        clock.tick(10); p.item_done("a")
        clock.tick(10); p.item_done("b")
        p.phase_done()
    p.begin("step4.compute", items=2)
    overall = (clock.t) / p._done            # the run-wide rate as step 4 starts
    checks.append(("a phase that has not started yet is estimated at the run-wide rate",
                   abs(seen[-1].eta_s - (p._total - p._done) * overall) < 1e-6,
                   f"{seen[-1].eta_s:.1f}"))
    clock.tick(5); p.item_done("a")
    after = p._total - p._done - w["step4.compute"]   # step 4 plots + batch
    overall = clock.t / p._done
    expected = 5.0 + after * overall
    checks.append(("once it has done a recording, the rest of it goes at its own pace",
                   abs(seen[-1].eta_s - expected) < 1e-6,
                   f"{seen[-1].eta_s:.1f} vs {expected:.1f}"))
    run_wide = (p._total - p._done) * overall
    checks.append(("which is far shorter than detection's pace would say",
                   seen[-1].eta_s < run_wide, f"{seen[-1].eta_s:.1f} vs {run_wide:.1f}"))

    # Half a recording in: half trusted.
    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=2, stop_step=3, n_recordings=2))
    p.begin("step2", items=2)
    clock.tick(10); p.item_done("a")
    p.phase_done()
    p.begin("step3", items=2)
    overall_before = clock.t / p._done
    clock.tick(100)
    p.item_progress(0.5)
    earned = w["step3"] / 2
    own = 100 / earned
    overall = clock.t / p._done
    rate = 0.5 * own + 0.5 * overall
    expected = (w["step3"] * 2 - earned) * rate
    checks.append(("half a recording into a phase, its own pace is half trusted",
                   abs(seen[-1].eta_s - expected) < 1e-6 and overall_before > 0,
                   f"{seen[-1].eta_s:.1f} vs {expected:.1f}"))

    # Express mode drops most plotting, so the plotting phases must weigh less
    # or the bar would crawl through work that is no longer being done.
    plan = plan_ephys(start_step=4, stop_step=4, n_recordings=2)
    full, seen_f, _ = _reporter()
    full.plan(plan)
    full.begin("step4.compute", items=2)
    full.item_done("a")
    full.item_done("b")
    express, seen_e, _ = _reporter(express=True)
    express.plan(plan)
    express.begin("step4.compute", items=2)
    express.item_done("a")
    express.item_done("b")
    checks.append(("express mode reaches further on the same compute",
                   seen_e[-1].fraction > seen_f[-1].fraction,
                   f"{seen_e[-1].fraction:.3f} vs {seen_f[-1].fraction:.3f}"))
    return checks


def _transfer_checks() -> list[Check]:
    checks: list[Check] = []

    p, seen, clock = _reporter()
    p.plan(plan_catnap(n_recordings=2))
    checks.append(("a local run reports no transfer",
                   not p.snapshot().transferring, ""))

    p.expect_transfer(1_000_000_000)
    checks.append(("pre-flight fixes the download total up front",
                   seen[-1].bytes_total == 1_000_000_000 and seen[-1].bytes_done == 0,
                   str(seen[-1].bytes_total)))

    p.transferred(250_000_000, detail="rec_a")
    checks.append(("bytes are reported against that total",
                   seen[-1].bytes_done == 250_000_000
                   and seen[-1].transfer_detail == "rec_a", str(seen[-1].bytes_done)))

    # Files already cached report their whole size at once; the running total
    # must not fall back when the next file starts from zero.
    p.transferred(100_000_000, detail="rec_b")
    checks.append(("the transfer total never goes backwards",
                   seen[-1].bytes_done == 250_000_000, str(seen[-1].bytes_done)))

    checks.append(("transfers are not counted as pipeline progress",
                   # They overlap compute, so charging them would double-count.
                   seen[-1].fraction == 0.0, str(seen[-1].fraction)))
    return checks + _source_transfer_checks()


class _FakeCache:
    """Enough of :class:`~meanap.remote.cache.FileCache` to drive one fetch."""

    def __init__(self, sizes: dict[str, int]) -> None:
        self.sizes = sizes

    def get(self, store, rel, progress=None):
        size = self.sizes[rel]
        if progress is not None:      # the real cache streams in chunks
            for sent in range(0, size + 1, size // 2 or 1):
                progress(min(sent, size), size)
            progress(size, size)
        return Path("/cache") / rel

    def path_for(self, store, rel):
        return Path("/cache") / rel


def _source_transfer_checks() -> list[Check]:
    """The counter has to be wired to the thing that actually downloads."""
    from meanap.remote.base import RemoteEntry
    from meanap.remote.source import RecordingSource

    class Store:
        copies = True
        store_id = "fake"

        def list(self, path=""):
            return [RemoteEntry(path=f"{path}/{n}", is_dir=False, size=s)
                    for n, s in (("stat.npy", 100), ("F.npy", 300),
                                 ("ops.npy", 100), ("iscell.npy", 100))]

        def stat(self, path):
            return None

    checks: list[Check] = []
    p, seen, _ = _reporter()
    p.plan(plan_catnap(n_recordings=2))
    p.expect_transfer(1200)

    sizes = {f"rec_a/suite2p/plane0/{n}": s
             for n, s in (("stat.npy", 100), ("F.npy", 300),
                          ("ops.npy", 100), ("iscell.npy", 100))}
    sizes.update({k.replace("rec_a", "rec_b"): v for k, v in sizes.items()})

    source = RecordingSource(store=Store(), cache=_FakeCache(sizes),
                             log=lambda m: None, progress=p)
    source.plane0("rec_a")
    checks.append(("fetching a recording's folder reports its bytes",
                   seen[-1].bytes_done == 600, str(seen[-1].bytes_done)))

    source.plane0("rec_b")
    checks.append(("a second recording adds to the run's total",
                   seen[-1].bytes_done == 1200, str(seen[-1].bytes_done)))
    checks.append(("which lands exactly on what pre-flight predicted",
                   seen[-1].bytes_done == seen[-1].bytes_total,
                   f"{seen[-1].bytes_done} of {seen[-1].bytes_total}"))

    counts = [s.bytes_done for s in seen]
    checks.append(("the byte count never goes backwards mid-file",
                   all(b >= a for a, b in zip(counts, counts[1:])), str(counts)))

    # A source with no reporter must behave exactly as before.
    plain = RecordingSource(store=Store(), cache=_FakeCache(sizes),
                            log=lambda m: None)
    checks.append(("a source with no reporter still fetches",
                   plain.plane0("rec_a") == Path("/cache/rec_a/suite2p/plane0"),
                   str(plain.plane0("rec_a"))))
    return checks


def _format_checks() -> list[Check]:
    return [
        ("seconds under a minute", format_duration(45) == "45s", format_duration(45)),
        ("minutes and seconds", format_duration(605) == "10m 05s", format_duration(605)),
        ("hours and minutes", format_duration(7500) == "2h 05m", format_duration(7500)),
        ("an unknown estimate says so",
         format_duration(None) == "unknown", format_duration(None)),
        ("a negative estimate is clamped, not printed",
         format_duration(-5) == "0s", format_duration(-5)),
        ("megabytes below a gigabyte",
         format_bytes(340_000_000) == "340 MB", format_bytes(340_000_000)),
        ("gigabytes above one",
         format_bytes(14_200_000_000) == "14.20 GB", format_bytes(14_200_000_000)),
    ]


# ── Within a recording ───────────────────────────────────────────────────────

def _partial_checks() -> list[Check]:
    """A recording's own progress moves the bar before the recording is done.

    Without it, step 1 of a two-recording run sat at 0% for the whole first
    recording — minutes of loading and detecting that looked like a hang.
    """
    import threading

    from meanap.pipeline.runner import (
        CHANNEL_REPORTS, STEP1_DETECTED, STEP1_LOADED, _channel_progress,
    )

    checks: list[Check] = []
    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=2))
    p.begin("step1", items=2)

    p.item_progress(0.5, "rec_a · detecting spikes")
    half = seen[-1].fraction
    p.item_progress(1.0)
    one_item = seen[-1].fraction
    checks.append(("half a recording credits half its share",
                   half > 0 and abs(half - one_item / 2) < 1e-9,
                   f"{half:.4f} vs {one_item:.4f}"))
    checks.append(("the detail says what the recording is doing",
                   seen[-2].detail.startswith("rec_a · detecting spikes"), seen[-2].detail))
    checks.append(("a detail-less update keeps the last detail",
                   seen[-1].detail.startswith("rec_a · detecting spikes"), seen[-1].detail))

    p.item_progress(0.2)
    checks.append(("a late, smaller report never moves the bar back",
                   seen[-1].fraction == one_item, f"{seen[-1].fraction:.4f}"))
    p.item_progress(7.0)
    checks.append(("a fraction past 1 stops at the end of the item",
                   seen[-1].fraction == one_item, f"{seen[-1].fraction:.4f}"))

    p.item_done("rec_a")
    checks.append(("finishing the item adds nothing it already credited",
                   abs(seen[-1].fraction - one_item) < 1e-9,
                   f"{seen[-1].fraction:.4f} vs {one_item:.4f}"))
    p.item_progress(0.5)
    checks.append(("the second recording's progress builds on the first",
                   abs(seen[-1].fraction - 1.5 * one_item) < 1e-9,
                   f"{seen[-1].fraction:.4f}"))
    p.item_done("rec_b")
    p.finish()
    checks.append(("the run still ends at 100%",
                   seen[-1].fraction == 1.0, f"{seen[-1].fraction}"))

    # Detection reports from worker threads, out of order.
    p, seen, _ = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=1))
    p.begin("step1", items=1)
    report = _channel_progress(p, "rec")
    order = list(range(1, 241))
    threads = [threading.Thread(target=lambda part=order[i::8]: [report(d, 240) for d in part])
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fractions = [s.fraction for s in seen]
    checks.append(("reports from many threads never move the bar back",
                   all(b >= a for a, b in zip(fractions, fractions[1:])), ""))
    expected = STEP1_DETECTED * PHASE_WEIGHTS["step1"] / p._total
    checks.append(("detection ends where the checks begin",
                   abs(max(fractions) - expected) < 1e-9,
                   f"{max(fractions):.4f} vs {expected:.4f}"))

    p, seen, _ = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=1))
    p.begin("step1", items=1)
    before = len(seen)
    report = _channel_progress(p, "rec")
    for done in range(1, 1001):
        report(done, 1000)
    sent = len(seen) - before
    checks.append(("a 1000-channel array sends tens of updates, not a thousand",
                   sent <= CHANNEL_REPORTS + 1, str(sent)))
    checks.append(("the last channel is always reported",
                   seen[-1].detail == "rec · detecting spikes, 1000 of 1000 channels",
                   seen[-1].detail))
    report(0, 0)
    checks.append(("an empty recording reports nothing", len(seen) - before == sent, ""))
    checks.append(("loading comes before detecting",
                   0 < STEP1_LOADED < STEP1_DETECTED < 1, ""))
    return checks


def _skip_checks() -> list[Check]:
    """Recordings the sheet lists but the folder lacks are not work."""
    checks: list[Check] = []
    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=4, n_recordings=60))
    p.begin("step1", items=60)
    for i in range(2, 60):
        p.skip(f"missing_{i}")
    p.item_done("real_0")
    checks.append(("with 58 of 60 missing, one real recording is half of step 1",
                   abs(p._phase_credited - p._weights["step1"] / 2) < 1e-9,
                   f"{p._phase_credited:.2f} of {p._weights['step1']:.2f}"))
    one_rec = sum(PHASE_WEIGHTS[k] for k in
                  ("step1", "step2", "step3", "step4.compute", "step4.plot"))
    expected = 2 * one_rec + PHASE_WEIGHTS["batch"]
    checks.append(("and the whole plan is two recordings' worth plus the batch",
                   abs(p._total - expected) < 1e-6, f"{p._total:.1f} vs {expected:.1f}"))
    p.skip("missing_5")
    checks.append(("skipping twice changes nothing",
                   abs(p._total - expected) < 1e-6, f"{p._total:.1f}"))
    p.item_done("missing_7")
    checks.append(("a report for a skipped recording is ignored",
                   abs(p._phase_credited - p._weights["step1"] / 2) < 1e-9, ""))
    p.item_done("real_1")
    p.phase_done()
    p.begin("step2", items=60)
    checks.append(("later steps loop over the sheet but count only what will run",
                   p._items_total == 2, str(p._items_total)))
    for name in ["real_0"] + [f"missing_{i}" for i in range(2, 60)]:
        p.item_done(name)
    checks.append(("so their bar moves a half per real recording",
                   abs(p._phase_credited - p._weights["step2"] / 2) < 1e-9, ""))
    p.item_done("real_1")
    p.phase_done()
    for key in ("step3", "step4.compute", "step4.plot"):
        p.begin(key, items=60)
        p.item_done("real_0"); p.item_done("real_1")
        p.phase_done()
    p.begin("batch", items=1)
    p.item_done("")
    checks.append(("and the bar reaches the end on the real work alone",
                   abs(seen[-1].fraction - 1.0) < 1e-9, f"{seen[-1].fraction:.4f}"))

    # Found part-way: the steps already done keep their credit.
    p, seen, clock = _reporter()
    p.plan(plan_ephys(start_step=1, stop_step=2, n_recordings=2))
    p.begin("step1", items=2)
    p.item_done("a")
    p.phase_done()
    before = seen[-1].fraction
    p.begin("step2", items=2)
    p.skip("b")
    checks.append(("a recording dropped in a later step leaves earlier credit alone",
                   abs(p._done - PHASE_WEIGHTS["step1"] * 2) < 1e-9 and before > 0,
                   f"{p._done:.2f}"))
    return checks


def _memory_checks() -> list[Check]:
    """This computer's step times, remembered between runs."""
    import json
    import tempfile

    from meanap.pipeline import step_times
    from meanap.pipeline.step_times import StepTimes, for_this_computer

    checks: list[Check] = []
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deep" / "step_times.json"

    def run(times, *, express=False, step1=100.0, step4=10.0, finish=True,
            missing=0) -> RunProgress:
        p, _, clock = _reporter(express=express, times=times)
        p.plan(plan_ephys(start_step=1, stop_step=4, n_recordings=2 + missing))
        p.begin("step1", items=2 + missing)
        for i in range(missing):
            p.skip(f"gone_{i}")
        for name in ("a", "b"):
            clock.tick(step1); p.item_done(name)
        p.phase_done()
        for key, secs in (("step2", 1.0), ("step3", 2.0),
                          ("step4.compute", step4), ("step4.plot", 0.5)):
            p.begin(key, items=2 + missing)
            for name in ("a", "b"):
                clock.tick(secs); p.item_done(name)
            p.phase_done()
        p.begin("batch", items=1)
        clock.tick(3.0)  # finished with phase_done alone, as step 4 does
        p.phase_done()
        if finish:
            p.finish()
        return p

    times = StepTimes(path)
    checks.append(("a computer with no history plans with the benchmark",
                   run(times, finish=False)._per_item["step1"] == PHASE_WEIGHTS["step1"], ""))
    checks.append(("a run that never finished leaves nothing behind",
                   not path.exists(), ""))

    run(times, missing=58)
    saved = json.loads(path.read_text())["phases"]
    checks.append(("a finished run saves seconds per recording, per step",
                   abs(saved["step1"]["seconds"] - 100.0) < 1e-9
                   and abs(saved["step4.compute"]["seconds"] - 10.0) < 1e-9,
                   str({k: v["seconds"] for k, v in saved.items()})))
    checks.append(("recordings with no raw file do not dilute the per-recording time",
                   saved["step1"]["runs"] == 1, ""))
    checks.append(("the once-per-run comparisons are timed as one unit",
                   abs(saved.get("batch@full", {}).get("seconds", 0) - 3.0) < 1e-9,
                   str(saved.get("batch@full"))))
    checks.append(("the drawing phases are kept per figure mode",
                   "step4.plot@full" in saved and "step4.plot" not in saved, str(list(saved))))
    checks.append(("the file is made where it is asked for, folders and all",
                   path.is_file(), str(path)))

    again = StepTimes(path)
    p = run(again, finish=False)
    checks.append(("the next run plans with this computer's own times",
                   p._per_item["step1"] == 100.0 and p._per_item["step4.compute"] == 10.0,
                   str(p._per_item)))

    p = run(StepTimes(path), express=True, finish=False)
    plotted = p._per_item["step4.plot"]
    # Not remembered in express mode: the benchmark's figure, scaled by how
    # this computer compares on what it does remember.
    # Step 2 is mostly drawing, so its full-figure time does not count here.
    measured = {"step1": 100.0, "step3": 2.0, "step4.compute": 10.0}
    scale = sorted(v / PHASE_WEIGHTS[k] for k, v in measured.items())[1]
    expected = PHASE_WEIGHTS["step4.plot"] * 0.01 * scale
    checks.append(("a phase it has not timed is scaled to this computer's pace",
                   abs(plotted - expected) < 1e-9, f"{plotted:.4f} vs {expected:.4f}"))

    run(StepTimes(path), step1=50.0)
    entry = json.loads(path.read_text())["phases"]["step1"]
    checks.append(("one new run moves the remembered time halfway, not all the way",
                   abs(entry["seconds"] - 75.0) < 1e-9 and entry["runs"] == 2, str(entry)))

    path.write_text("{not json")
    checks.append(("an unreadable file is ignored, not fatal",
                   StepTimes(path).seconds("step1") is None, ""))
    path.write_text(json.dumps({"version": 99, "phases": {"step1": {"seconds": 5}}}))
    checks.append(("a file from another format version is ignored",
                   StepTimes(path).seconds("step1") is None, ""))
    blocked = tmp / "a_file"
    blocked.write_text("")
    try:
        StepTimes(blocked / "step_times.json").record({"step1": 1.0})
        quiet = True
    except Exception as e:  # noqa: BLE001
        quiet = f"{type(e).__name__}: {e}"
    checks.append(("a file that cannot be written does not stop the run",
                   quiet is True, str(quiet)))

    old_env = os.environ.pop(step_times.ENV_VAR, None)
    old_flag = step_times._enabled
    try:
        step_times._enabled = False
        checks.append(("scripts and tests calling the runner do not remember",
                       for_this_computer() is None, ""))
        step_times.remember_on_this_computer()
        found = for_this_computer()
        checks.append(("the GUI and the meanap command do, in this computer's cache folder",
                       found is not None and found.path == step_times.default_path(),
                       str(found and found.path)))
        os.environ[step_times.ENV_VAR] = "off"
        checks.append(("and MEANAP_STEP_TIMES=off turns it off",
                       for_this_computer() is None, ""))
        os.environ[step_times.ENV_VAR] = str(path)
        checks.append(("or points it at another file",
                       for_this_computer().path == path, ""))
    finally:
        step_times._enabled = old_flag
        os.environ.pop(step_times.ENV_VAR, None)
        if old_env is not None:
            os.environ[step_times.ENV_VAR] = old_env
    return checks


def _benchmark_checks() -> list[Check]:
    """A first run on a computer, with its benchmark but no history."""
    import json
    import tempfile

    import h5py
    import numpy as np
    import scipy.io as sio

    from meanap.pipeline.progress import (
        BENCHMARK_REFERENCE, STEP1_PER_BENCHMARK, STEP1_RATE_KEY,
    )
    from meanap.pipeline.recording_probe import channel_samples
    from meanap.pipeline.step_times import StepTimes
    from meanap.shared.benchmark import DETECTION_SAMPLES, remember_benchmark, run_benchmark

    checks: list[Check] = []
    tmp = Path(tempfile.mkdtemp())
    ref = BENCHMARK_REFERENCE

    def times_with(detection: float, network: float, name: str) -> StepTimes:
        t = StepTimes(tmp / f"{name}.json")
        t.record_benchmark({"detection_s": detection, "network_s": network})
        return StepTimes(tmp / f"{name}.json")

    def per_item(times) -> dict:
        p, _, _ = _reporter(times=times)
        p.plan(plan_ephys(start_step=1, stop_step=4, n_recordings=2))
        return p._per_item

    plain = per_item(None)
    slow_detect = per_item(times_with(4 * ref["detection_s"], ref["network_s"], "a"))
    ratio = lambda w: w["step1"] / w["step4.compute"]  # noqa: E731
    checks.append(("a computer four times slower at detection weighs step 1 four times heavier",
                   abs(ratio(slow_detect) / ratio(plain) - 4.0) < 1e-9,
                   f"{ratio(slow_detect):.2f} vs {ratio(plain):.2f}"))
    uniform = per_item(times_with(3 * ref["detection_s"], 3 * ref["network_s"], "b"))
    checks.append(("one uniformly slower keeps the same balance",
                   all(abs(uniform[k] / plain[k] - 3.0) < 1e-9 for k in plain), str(uniform)))

    # One recording of 64 channels x 1.2M samples, with this computer's benchmark.
    size = 64 * 1_200_000
    bench_times = times_with(0.5, 2.0, "c")
    p, seen, clock = _reporter(times=bench_times)
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=1))
    p.begin("step1", items=1)
    checks.append(("without the recordings' size there is no number yet",
                   seen[-1].eta_s is None, str(seen[-1].eta_s)))
    p.expect_detection(size, 1)
    predicted = 0.5 * STEP1_PER_BENCHMARK * size / DETECTION_SAMPLES
    checks.append(("with it, the benchmark gives a time left before any work is done",
                   seen[-1].eta_s is not None and abs(seen[-1].eta_s - predicted) < 1e-6,
                   f"{seen[-1].eta_s} vs {predicted:.2f}"))
    clock.tick(predicted * 3)  # this computer is three times slower than predicted
    p.item_progress(0.5)
    # Seconds per recording: as measured so far, and as predicted. Half a
    # recording in, the run-wide pace is half each; step 1's own pace, which
    # is the measured one again, is then trusted half over that — so the
    # measurement carries three-quarters.
    measured, prior = predicted * 3 / 0.5, predicted
    expected = 0.5 * (0.75 * measured + 0.25 * prior)
    checks.append(("half a recording in, the run's own pace already outweighs the prediction",
                   abs(seen[-1].eta_s - expected) < 1e-6,
                   f"{seen[-1].eta_s:.2f} vs {expected:.2f}"))
    clock.tick(predicted * 3)
    p.item_done("a")
    p.phase_done()
    p.finish()
    kept = StepTimes(tmp / "c.json").seconds(STEP1_RATE_KEY)
    checks.append(("a finished run keeps step 1's own seconds per channel-sample",
                   kept is not None and abs(kept - predicted * 6 / size) < 1e-15,
                   f"{kept} vs {predicted * 6 / size}"))

    p, seen, clock = _reporter(times=StepTimes(tmp / "c.json"))
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=1))
    p.begin("step1", items=1)
    p.expect_detection(size, 1)
    checks.append(("and the next run predicts from that, not from the benchmark",
                   abs(seen[-1].eta_s - predicted * 6) < 1e-6,
                   f"{seen[-1].eta_s:.2f} vs {predicted * 6:.2f}"))

    p, seen, clock = _reporter(times=StepTimes(tmp / "nothing.json"))
    p.plan(plan_ephys(start_step=1, stop_step=1, n_recordings=1))
    p.begin("step1", items=1)
    p.expect_detection(size, 1)
    checks.append(("with neither, it waits for real work as before",
                   seen[-1].eta_s is None, str(seen[-1].eta_s)))

    both = tmp / "both.json"
    t = StepTimes(both)
    t.record({"step1": 5.0})
    t.record_benchmark({"detection_s": 0.4, "network_s": 1.0})
    data = json.loads(both.read_text())
    checks.append(("the benchmark is kept beside the step times, neither losing the other",
                   data["phases"]["step1"]["seconds"] == 5.0
                   and data["benchmark"]["detection_s"] == 0.4, str(data)))

    # Sizes from headers: an HDF5 .mat is read, a v7 .mat is not loaded.
    h5 = tmp / "rec.mat"
    with h5py.File(h5, "w") as f:
        f["dat"] = np.zeros((4, 1000), dtype=np.float32)
        f["channels"] = np.arange(1, 5, dtype=float)
        f["fs"] = np.array([[25000.0]])
    v7 = tmp / "old.mat"
    sio.savemat(v7, {"dat": np.zeros((1000, 4)), "channels": np.arange(1, 5), "fs": 25000.0})
    checks.append(("a recording's size is read from its header",
                   channel_samples(h5) == 4000, str(channel_samples(h5))))
    checks.append(("an old-style .mat is not loaded just to size it",
                   channel_samples(v7) is None, str(channel_samples(v7))))
    checks.append(("a file that will not open is no size, not an error",
                   channel_samples(tmp / "missing.mat") is None, ""))

    os.environ["MEANAP_STEP_TIMES"] = str(tmp / "bench.json")
    try:
        run_benchmark(scale=0.02)
        checks.append(("a scaled-down benchmark is never kept as this computer's",
                       not (tmp / "bench.json").exists(), ""))
        remember_benchmark(run_benchmark(scale=0.02, remember=False))
        checks.append(("but a result can be kept on purpose",
                       StepTimes(tmp / "bench.json").benchmark is not None, ""))
    finally:
        os.environ["MEANAP_STEP_TIMES"] = "off"
    return checks


def _percent_checks() -> list[Check]:
    def text(fraction: float) -> str:
        return Progress(fraction=fraction, phase="", detail="",
                        elapsed_s=0.0, eta_s=None).percent_text

    return [
        ("nothing done reads 0%", text(0.0) == "0%", text(0.0)),
        ("under 10% shows a decimal, so the start visibly moves",
         text(0.004) == "0.4%", text(0.004)),
        ("10% and over is whole numbers", text(0.372) == "37%", text(0.372)),
        ("done reads 100%", text(1.0) == "100%", text(1.0)),
    ]


# ── The panel ─────────────────────────────────────────────────────────────────

def _panel_checks(app) -> list[Check]:
    from meanap.gui.panels.run import RunPanel

    checks: list[Check] = []
    panel = RunPanel()
    checks.append(("the progress box is hidden until a run starts",
                   not panel.progress_box.isVisibleTo(panel), ""))

    panel.start_progress()
    checks.append(("starting a run shows it, empty",
                   panel.progress_box.isVisibleTo(panel)
                   and panel.progress_bar.value() == 0, str(panel.progress_bar.value())))
    checks.append(("with no transfer bar on a local run",
                   not panel.transfer_bar.isVisibleTo(panel), ""))

    panel.show_progress(Progress(fraction=0.25, phase="Step 1 · Spike detection",
                                 detail="rec_a (1/4)", elapsed_s=65, eta_s=None))
    checks.append(("an uncalibrated estimate says 'estimating', not a number",
                   "estimating" in panel.progress_eta.text()
                   and "1m 05s elapsed" in panel.progress_eta.text(),
                   panel.progress_eta.text()))
    checks.append(("the headline carries percent, phase and recording",
                   panel.progress_label.text() == "25%  ·  Step 1 · Spike detection  ·  rec_a (1/4)",
                   panel.progress_label.text()))
    checks.append(("the bar tracks the fraction at per-mille resolution",
                   panel.progress_bar.value() == 250, str(panel.progress_bar.value())))

    panel.show_progress(Progress(fraction=0.5, phase="Step 3", detail="",
                                 elapsed_s=120, eta_s=180))
    checks.append(("a calibrated estimate is shown as a duration",
                   "about 3m 00s left" in panel.progress_eta.text(),
                   panel.progress_eta.text()))

    panel.show_progress(Progress(fraction=0.5, phase="Step 1", detail="rec_b",
                                 elapsed_s=130, eta_s=170,
                                 bytes_done=340_000_000, bytes_total=1_000_000_000,
                                 transfer_detail="rec_c"))
    checks.append(("a remote run shows the download separately",
                   panel.transfer_bar.isVisibleTo(panel)
                   and panel.transfer_bar.value() == 340,
                   str(panel.transfer_bar.value())))
    checks.append(("with the figures spelled out",
                   panel.transfer_label.text() == "Downloaded 340 MB of 1.00 GB  ·  rec_c",
                   panel.transfer_label.text()))

    panel.finish_progress("Finished.")
    checks.append(("the finished bar reports the total time, not a blank",
                   panel.progress_label.text() == "Finished."
                   and "2m 10s total" in panel.progress_eta.text(),
                   panel.progress_eta.text()))
    checks.append(("and the transfer bar is put away",
                   not panel.transfer_bar.isVisibleTo(panel), ""))
    return checks


def _worker_checks(app) -> list[Check]:
    """The pipeline must actually drive the panel, end to end."""
    from meanap.gui.pipeline_worker import PipelineWorker

    checks: list[Check] = []
    checks.append(("the worker exposes a progress signal",
                   hasattr(PipelineWorker, "progress"), ""))

    # run_pipeline must accept and forward it, or the signal would never fire.
    import inspect
    from meanap.pipeline.runner import run_pipeline
    sig = inspect.signature(run_pipeline)
    checks.append(("run_pipeline takes a progress callback",
                   "progress" in sig.parameters
                   and sig.parameters["progress"].default is None, str(sig)))

    for name, fn in [
        ("step 1", "meanap.pipeline.runner:_run_step1_spike_detection"),
        ("step 2", "meanap.pipeline.step2:_run_step2_neuronal_activity"),
        ("step 3", "meanap.pipeline.step3:_run_step3_functional_connectivity"),
        ("step 4", "meanap.pipeline.step4:_run_step4_network_metrics"),
        ("stim analysis", "meanap.pipeline.stim_step:run_stim_analysis"),
        ("CAT-NAP", "meanap.catnap.pipeline:run_catnap_pipeline"),
    ]:
        module, _, attr = fn.partition(":")
        obj = getattr(__import__(module, fromlist=[attr]), attr)
        params = inspect.signature(obj).parameters
        checks.append((f"{name} reports progress",
                       "progress" in params and params["progress"].default is None,
                       str(list(params))))
    return checks


def main() -> int:
    print("=" * 70)
    print("Run progress and time estimates")
    print("=" * 70)

    total_pass = total = 0
    for title, build in [("Planning:", _plan_checks),
                         ("Progress model:", _model_checks),
                         ("Calibration:", _calibration_checks),
                         ("Transfers:", _transfer_checks),
                         ("Within a recording:", _partial_checks),
                         ("Missing recordings:", _skip_checks),
                         ("Remembered step times:", _memory_checks),
                         ("First run, from the benchmark:", _benchmark_checks),
                         ("Percentages:", _percent_checks),
                         ("Formatting:", _format_checks)]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        print(f"\nGUI checks SKIPPED — PyQt6 not available ({e})")
    else:
        app = QApplication.instance() or QApplication([])
        for title, build in [("Pipeline panel:", _panel_checks),
                             ("Wiring:", _worker_checks)]:
            p, n = _report(title, build(app))
            total_pass += p
            total += n

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
