"""The machine report: what it says about this computer, and what it warns about.

The page exists for two questions — *which of our computers should run the
batch* and *why is MEA-NAP slow on mine* — and both are answered by numbers
that must be the ones the pipeline will really use. So the checks here are
mostly about that correspondence: the worker counts come from calling the same
functions the run calls, with the same per-recording memory estimates the steps
pass in, and the warnings fire on the conditions that actually make a run slow
rather than on round numbers someone liked.

The benchmark itself is run once, small, at the end. It spawns worker
processes, which is why this file has a ``__main__`` guard — without one,
``spawn`` re-imports the module in every child and the pool dies. That is the
same rule the pipeline's own ``spawn_usable`` enforces.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.system_report import SystemReportDialog  # noqa: E402
from meanap.pipeline import machine as machine_mod  # noqa: E402
from meanap.pipeline.machine import (  # noqa: E402
    describe_machine, plan_work, report_lines,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def main() -> None:
    app = QApplication.instance() or QApplication([])

    print("\nWhat this computer is")

    machine = describe_machine()
    check("the core count is real", machine.physical_cores >= 1,
          str(machine.physical_cores))
    check("logical cores are never fewer than physical",
          machine.logical_cores >= machine.physical_cores,
          f"{machine.logical_cores} vs {machine.physical_cores}")
    check("the CPU is named, not left blank",
          bool(machine.cpu_name.strip()) and machine.cpu_name != "unknown",
          machine.cpu_name)
    check("free memory is a positive number", machine.ram_available_gb > 0,
          str(machine.ram_available_gb))
    check("the MEA-NAP version is stamped", machine.meanap_version != "unknown",
          machine.meanap_version)

    print("\nWhat a run will do here")

    plan = plan_work()
    names = [step.name for step in plan.steps]
    check("the three parallel steps are described", len(plan.steps) == 3, str(names))
    check("every step says how wide it goes",
          all(step.workers >= 1 for step in plan.steps),
          str([s.workers for s in plan.steps]))
    check("every step says what is holding it back",
          all(step.limit.strip() for step in plan.steps), str(plan.steps))

    # The numbers must be the pipeline's, not a plausible-looking guess: these
    # are read from the steps themselves, so a step that changes its estimate
    # changes this page with it.
    from meanap.pipeline.step3 import _STEP3_MEM_PER_TASK_GB
    from meanap.pipeline.step4 import _STEP4_MEM_PER_TASK_GB
    memory = machine_mod._step_memory()
    check("step 3's memory estimate is read from step 3",
          memory["step3"] == _STEP3_MEM_PER_TASK_GB, str(memory))
    check("step 4's memory estimate is read from step 4",
          memory["step4"] == _STEP4_MEM_PER_TASK_GB, str(memory))

    from meanap.pipeline.parallel import suggest_thread_count
    check("step 1's thread count is the one detection will really use",
          plan.steps[0].workers == suggest_thread_count(60),
          f"{plan.steps[0].workers} vs {suggest_thread_count(60)}")
    check("step 1 says recordings are done one at a time",
          "one at a time" in plan.steps[0].limit, plan.steps[0].limit)

    print("\nThe warnings fire on the things that actually slow a run")

    real_ram = machine_mod.available_ram_gb
    real_cores = machine_mod.physical_cores
    real_spawn = machine_mod.spawn_usable
    try:
        machine_mod.available_ram_gb = lambda: 2.0
        starved = plan_work(describe_machine())
        check("low free memory is called out",
              any("swap" in w for w in starved.warnings), str(starved.warnings))

        machine_mod.available_ram_gb = lambda: 3.5
        machine_mod.physical_cores = lambda: 32
        # A machine with many cores that can still only do one recording at a
        # time is the classic "why is this slow" and must not pass silently.
        bound = plan_work(describe_machine())
        check("memory beating cores is called out",
              any("binding constraint" in w for w in bound.warnings),
              str(bound.warnings))

        machine_mod.available_ram_gb = real_ram
        machine_mod.physical_cores = real_cores
        machine_mod.spawn_usable = lambda: False
        crippled = plan_work(describe_machine())
        check("worker processes being unavailable is called out",
              any("single core" in w for w in crippled.warnings),
              str(crippled.warnings))
    finally:
        machine_mod.available_ram_gb = real_ram
        machine_mod.physical_cores = real_cores
        machine_mod.spawn_usable = real_spawn

    healthy = plan_work()
    check("a healthy machine is not warned at for no reason",
          not any("swap" in w or "single core" in w for w in healthy.warnings),
          str(healthy.warnings))

    print("\nThe report someone pastes into an email")

    text = "\n".join(report_lines(machine, plan))
    for wanted in (machine.cpu_name, "physical cores", "What a run will do here",
                   "Step 1, spike detection"):
        check(f"the report carries {wanted!r}", wanted in text)
    check("no benchmark section before one has been run",
          "Benchmark:" not in text, text)

    print("\nThe window")

    window = MainWindow()
    window.show()
    app.processEvents()
    check("no report window exists until it is asked for",
          window._system_report is None)
    window._on_show_system_report()
    app.processEvents()
    dialog = window._system_report
    check("the toolbar opens one", dialog is not None)
    window._on_show_system_report()
    app.processEvents()
    check("asking twice shows the same window", window._system_report is dialog)
    check("it opens on this machine's numbers",
          machine.cpu_name in dialog.report_text(), dialog.report_text()[:80])

    dialog._on_copy()
    check("copying puts the report on the clipboard",
          QApplication.clipboard().text() == dialog.report_text())
    check("and says so", "clipboard" in dialog._status.text(),
          dialog._status.text())

    dialog._on_refresh()
    app.processEvents()
    check("refreshing re-reads free memory", "GB free now" in dialog._status.text(),
          dialog._status.text())

    print("\nTiming this computer (small, but the real benchmark)")

    from meanap.shared.benchmark import run_benchmark

    scale = 0.05
    result = run_benchmark(scale=scale, max_processes=2)
    check("it returns a positive score", result.score > 0, str(result.score))
    check("it times both halves separately",
          result.detection_s > 0 and result.network_s > 0,
          f"{result.detection_s} / {result.network_s}")
    # The parts are measured; the total is what a full-size run would take. The
    # two differ by exactly the scale, and the window only ever runs at 1.0 —
    # where they are the same number.
    check("the reported total is the measured work scaled up",
          abs(result.detection_s + result.network_s - result.seconds * scale) < 1e-6,
          str(result))

    dialog._on_done(result)
    app.processEvents()
    check("the window shows the score", "Relative speed" in dialog._score.text(),
          dialog._score.text()[:80])
    check("and says which half was slower",
          any(word in dialog._score.text()
              for word in ("slower half", "balanced")), dialog._score.text())
    with_bench = dialog.report_text()
    check("the copied report now carries the benchmark",
          "Benchmark:" in with_bench, with_bench)

    dialog._on_failed("no worker processes")
    check("a failed run says so rather than showing a stale score",
          "could not finish" in dialog._score.text(), dialog._score.text())

    dialog.close()
    window.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
