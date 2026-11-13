"""How long each step has taken on this computer, remembered between runs.

:data:`~meanap.pipeline.progress.PHASE_WEIGHTS` say how long each step takes
relative to the others on one benchmark machine and dataset. The run's own
measurements correct them as it goes, but only for steps it has reached, so
the estimate during spike detection still rests on the benchmark's idea of
step 4. After a run finishes, the seconds per recording each step took here
are kept in a small file in this computer's cache folder, and the next run
plans with them instead.

Per computer, not per repository or per user account: a laptop and a
workstation running the same analysis have different proportions (spike
detection is threaded per channel, step 4 per recording). A new computer's
first run uses the benchmark; every run after it, its own history.

The same file keeps this computer's benchmark (:mod:`meanap.shared.benchmark`)
— how fast it detects spikes and builds null models — which lets a first run
balance the steps for this computer before it has any history, and put a
number on spike detection from the recordings' size before it starts. And
once a run has detected spikes here, its seconds per sample replace the
benchmark's for that.

The file is a convenience. Reading or writing it never stops a run: anything
unreadable is ignored, and a failed write is silent.

Only the GUI and the ``meanap`` command remember — :func:`remember_on_this_computer`
switches it on — so tests and scripts calling the runner leave no trace. The
``MEANAP_STEP_TIMES`` environment variable overrides the file's location, or
turns it off with ``off``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

__all__ = ["StepTimes", "ENV_VAR", "remember_on_this_computer", "for_this_computer"]

ENV_VAR = "MEANAP_STEP_TIMES"
FILE_NAME = "step_times.json"
_VERSION = 1

#: How much a new run moves the remembered figure: half, so one unusual run
#: (a tiny test dataset, a busy machine) is diluted by the next rather than
#: replacing the history outright.
NEW_RUN_SHARE = 0.5

_enabled = False


def remember_on_this_computer() -> None:
    """Let runs in this process read and add to this computer's step times."""
    global _enabled
    _enabled = True


def default_path() -> Path:
    from meanap.frozen import cache_dir

    return cache_dir() / FILE_NAME


def for_this_computer() -> "StepTimes | None":
    """This computer's step times, or ``None`` when runs here don't remember."""
    override = os.environ.get(ENV_VAR, "").strip()
    if override.lower() == "off":
        return None
    if override:
        return StepTimes(Path(override))
    if not _enabled:
        return None
    return StepTimes(default_path())


class StepTimes:
    """Seconds per recording for each progress phase, from earlier runs here."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._phases: dict[str, dict] = {}
        self._benchmark: dict | None = None
        self._read()

    def _read(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != _VERSION:
            return
        phases = data.get("phases")
        if isinstance(phases, dict):
            self._phases = {k: v for k, v in phases.items()
                            if isinstance(v, dict) and _positive(v.get("seconds"))}
        bench = data.get("benchmark")
        if (isinstance(bench, dict) and _positive(bench.get("detection_s"))
                and _positive(bench.get("network_s"))):
            self._benchmark = bench

    @property
    def benchmark(self) -> dict | None:
        """This computer's last full-size benchmark: ``detection_s``, ``network_s``, …"""
        return self._benchmark

    def record_benchmark(self, result) -> None:
        """Keep a :class:`~meanap.shared.benchmark.BenchmarkResult`, replacing the last."""
        data = result.as_dict() if hasattr(result, "as_dict") else dict(result)
        data["measured_at"] = time.time()
        self._benchmark = data
        self._save()

    def seconds(self, key: str) -> float | None:
        """Remembered seconds per recording for *key*, if any run has measured it."""
        entry = self._phases.get(key)
        return float(entry["seconds"]) if entry else None

    def runs(self, key: str) -> int:
        entry = self._phases.get(key)
        return int(entry.get("runs", 0)) if entry else 0

    def record(self, measured: dict[str, float]) -> None:
        """Fold one finished run's seconds per recording in, and save."""
        for key, seconds in measured.items():
            if not _positive(seconds):
                continue
            old = self.seconds(key)
            new = seconds if old is None else (
                (1 - NEW_RUN_SHARE) * old + NEW_RUN_SHARE * seconds)
            self._phases[key] = {"seconds": new, "runs": self.runs(key) + 1}
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            data = {"version": _VERSION, "phases": self._phases}
            if self._benchmark is not None:
                data["benchmark"] = self._benchmark
            tmp.write_text(json.dumps(data, indent=1))
            os.replace(tmp, self.path)
        except OSError:
            pass


def _positive(value) -> bool:
    return isinstance(value, (int, float)) and value > 0 and value == value
