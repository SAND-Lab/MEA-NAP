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
    checks.append(("step 4 outweighs step 2, as measured",
                   PHASE_WEIGHTS["step4.compute"] > 10 * PHASE_WEIGHTS["step2"],
                   f"{PHASE_WEIGHTS['step4.compute']} vs {PHASE_WEIGHTS['step2']}"))
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


# ── The panel ─────────────────────────────────────────────────────────────────

def _panel_checks(app) -> list[Check]:
    from meanap.gui.panels.pipeline import PipelinePanel

    checks: list[Check] = []
    panel = PipelinePanel()
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
