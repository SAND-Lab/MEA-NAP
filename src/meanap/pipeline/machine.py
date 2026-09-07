"""What this computer is, and what a run will do with it.

Two questions keep coming back, and neither has been answerable from inside
MEA-NAP: *which of our computers should run the big batch*, and *why is it slow
on mine*. Both need the same three things — what the hardware is, what the
pipeline decided to do with it, and how fast it actually goes — so they are
gathered here in one place, and :mod:`meanap.gui.system_report` only renders
what this returns.

The middle one is the part that has been invisible. Worker counts are chosen
automatically (see :mod:`meanap.pipeline.parallel`) from cores and free RAM,
and the choice is usually right — but when it is not, nothing said so. A batch
crawling through step 4 one recording at a time because 3 GB were free looks
exactly like a batch that is simply large.

Nothing here guesses: the numbers come from calling the same functions the run
calls, with the same per-task memory estimates the steps pass in. If a step's
estimate changes, this changes with it.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field

from meanap.pipeline.parallel import (
    _HAVE_PSUTIL, available_ram_gb, physical_cores, spawn_usable,
    suggest_process_count, suggest_thread_count,
)

__all__ = ["Machine", "Step", "WorkPlan", "describe_machine", "plan_work",
           "report_lines"]

#: Per-recording memory the steps actually pass to the process pool. Kept as a
#: table so this module reports what the pipeline does rather than a plausible
#: guess — these are imported from the steps below, not retyped.
_STEP_MEMORY: dict[str, float] = {}


def _step_memory() -> dict[str, float]:
    """The steps' own per-task estimates, read from the steps themselves."""
    global _STEP_MEMORY
    if not _STEP_MEMORY:
        from meanap.pipeline.step3 import _STEP3_MEM_PER_TASK_GB
        from meanap.pipeline.step4 import _STEP4_MEM_PER_TASK_GB
        _STEP_MEMORY = {"step3": _STEP3_MEM_PER_TASK_GB,
                        "step4": _STEP4_MEM_PER_TASK_GB}
    return _STEP_MEMORY


@dataclass
class Machine:
    """The hardware, as far as it affects how fast a run goes."""

    system: str
    release: str
    architecture: str
    cpu_name: str
    physical_cores: int
    logical_cores: int
    ram_available_gb: float
    python_version: str
    meanap_version: str
    #: False when psutil is missing, so the RAM figure is a conservative
    #: assumption rather than a measurement — worth saying, because every
    #: worker count derived from it is then a guess too.
    ram_measured: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Step:
    """One step's parallelism: how wide it goes here, and what limits it."""

    name: str
    workers: int
    unit: str          # "threads over channels" / "recordings at once"
    limit: str         # what stopped it going wider

    def describe(self) -> str:
        return f"{self.name}: {self.workers} {self.unit} — {self.limit}"


@dataclass
class WorkPlan:
    steps: list[Step]
    warnings: list[str] = field(default_factory=list)


def _cpu_name() -> str:
    """The processor's marketing name, or the best available substitute.

    ``platform.processor()`` returns something useful on Windows and nothing at
    all on most Linux builds, so each platform is asked in its own way before
    falling back to the architecture — which is at least never empty.
    """
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True, timeout=2)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        elif sys.platform.startswith("linux"):
            with open("/proc/cpuinfo") as handle:
                for line in handle:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or platform.machine() or "unknown"


def describe_machine() -> Machine:
    """Everything about this computer that bears on how fast MEA-NAP runs."""
    from meanap.version import meanap_version

    return Machine(
        system=platform.system(),
        release=platform.release(),
        architecture=platform.machine(),
        cpu_name=_cpu_name(),
        physical_cores=physical_cores(),
        logical_cores=os.cpu_count() or physical_cores(),
        ram_available_gb=available_ram_gb(),
        python_version=platform.python_version(),
        meanap_version=meanap_version(),
        ram_measured=_HAVE_PSUTIL,
    )


def _process_limit(memory_per_task_gb: float, machine: Machine) -> tuple[int, str]:
    """How many recordings run at once, and which ceiling decided it."""
    workers = suggest_process_count(999, memory_per_task_gb)
    cpu_cap = max(1, machine.physical_cores - 1)
    if workers >= cpu_cap:
        return workers, f"one per core, keeping one free ({machine.physical_cores} cores)"
    return workers, (f"limited by memory — {machine.ram_available_gb:.0f} GB free, "
                     f"about {memory_per_task_gb:g} GB per recording")


def plan_work(machine: Machine | None = None, *, channels: int = 60) -> WorkPlan:
    """What each step will do on this computer, and what is holding it back.

    *channels* is the electrode count a recording has; it caps step 1's threads,
    since there is nothing for a thread beyond the last channel to do.
    """
    machine = machine or describe_machine()
    memory = _step_memory()

    threads = suggest_thread_count(channels)
    cpu_cap = max(1, machine.physical_cores - 1)
    step1_limit = (f"one per core, keeping one free ({machine.physical_cores} cores)"
                   if threads >= cpu_cap else
                   f"only {channels} channels to share out")

    step3_workers, step3_limit = _process_limit(memory["step3"], machine)
    step4_workers, step4_limit = _process_limit(memory["step4"], machine)

    steps = [
        Step("Step 1, spike detection", threads, "threads over channels",
             step1_limit + "; recordings are done one at a time"),
        Step("Step 3, functional connectivity", step3_workers,
             "recordings at once", step3_limit),
        Step("Step 4, network metrics", step4_workers,
             "recordings at once", step4_limit),
    ]

    warnings: list[str] = []
    if not machine.ram_measured:
        warnings.append(
            "psutil is not installed, so free memory could not be measured. "
            "Every worker count above is based on a cautious guess, and this "
            "computer is probably being given less to do than it could handle.")
    if not spawn_usable():
        warnings.append(
            "Worker processes are unavailable, so steps 3 and 4 will run on a "
            "single core however many this computer has. That happens when the "
            "run is started from a script whose work is not inside "
            '`if __name__ == "__main__":` — the GUI and the meanap command are '
            "not affected.")
    if machine.ram_available_gb < 4.0:
        warnings.append(
            f"Only {machine.ram_available_gb:.1f} GB of memory is free. Spike "
            "detection holds a whole recording in memory, so a long one may "
            "swap to disk, which is far slower than any of this. Closing other "
            "applications is the fix.")
    if step4_workers < cpu_cap and machine.physical_cores > 2:
        # Whenever memory rather than the processor decides the width — not
        # only when it forces a single recording. On a 32-core machine with 3 GB
        # free, "2 at a time" is just as much the answer to "why is this slow",
        # and the first version of this check stayed silent for it.
        warnings.append(
            f"Step 4 will do {step4_workers} recording(s) at a time despite "
            f"this computer having {machine.physical_cores} cores: memory is "
            f"the binding constraint here, not processors. Closing other "
            f"applications, or more RAM, would widen it; more cores would not.")
    if machine.logical_cores > machine.physical_cores:
        warnings.append(
            f"This CPU reports {machine.logical_cores} logical cores over "
            f"{machine.physical_cores} physical ones. MEA-NAP counts the "
            "physical ones: the pipeline's work is limited by memory bandwidth "
            "as much as by processors, and hyperthreads share both.")
    return WorkPlan(steps=steps, warnings=warnings)


def report_lines(machine: Machine, plan: WorkPlan, benchmark=None) -> list[str]:
    """A plain-text report, for pasting into an email or an issue.

    Plain text on purpose: the point of this is that someone can send it to a
    colleague, or paste it under "MEA-NAP is slow on my machine", and the reply
    can be about the actual numbers.
    """
    lines = [
        f"MEA-NAP {machine.meanap_version} on Python {machine.python_version}",
        f"{machine.system} {machine.release} ({machine.architecture})",
        f"{machine.cpu_name}",
        f"{machine.physical_cores} physical cores "
        f"({machine.logical_cores} logical), "
        f"{machine.ram_available_gb:.1f} GB memory free"
        + ("" if machine.ram_measured else " (estimated — psutil not installed)"),
        "",
        "What a run will do here:",
    ]
    lines += [f"  {step.describe()}" for step in plan.steps]
    if benchmark is not None:
        lines += ["", "Benchmark:"]
        lines += [f"  {line}" for line in benchmark.describe()]
    if plan.warnings:
        lines += ["", "Worth knowing:"]
        lines += [f"  - {warning}" for warning in plan.warnings]
    return lines
