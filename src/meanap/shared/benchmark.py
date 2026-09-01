"""A short timing run, so a batch can be split by how fast each machine is.

Two computers rarely run at the same speed, and the split has to reflect
that or the faster one sits idle at the end. Core counts are a poor guide —
a laptop's eight cores and a workstation's eight cores are not the same
eight cores — so this measures what the pipeline actually does, on the
machinery the pipeline actually uses:

* a **detection** part: the real spike detector over a synthetic recording,
  threaded across channels exactly as step 1 is;
* a **network** part: the null-model randomisation behind step 4's
  normalised metrics, spread across a process pool exactly as steps 3 and 4
  are, so a machine with more usable cores scores higher — and one whose
  RAM would not let the pool grow scores as it will really run.

The result is a *score*, the ratio of a reference time to the measured one:
higher is faster, and two machines' scores are in the ratio of the work they
should be given. The absolute value means little on its own; the ratio is
what the split uses.

Sized to take on the order of 10–20 s on an ordinary laptop. Long enough to
swamp process start-up, short enough to run on every join without anyone
minding.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np

__all__ = ["BenchmarkResult", "run_benchmark", "REFERENCE_SECONDS"]

#: The total time that scores 1.0. Chosen so a mid-range 2020s laptop lands
#: near 1; only the ratio between machines matters to the split.
REFERENCE_SECONDS = 15.0

# Detection: channels x seconds of synthetic voltage at an MEA sampling rate.
_DET_FS = 25_000.0
_DET_CHANNELS = 16
_DET_SECONDS = 40.0
# Network: independent tasks, each a run of null models on a 60-node matrix.
_NET_NODES = 60
_NET_TASKS = 12
_NET_MODELS_PER_TASK = 150
_NET_ITERATIONS = 10


@dataclass
class BenchmarkResult:
    seconds: float            # detection_s + network_s
    score: float              # REFERENCE_SECONDS / seconds
    detection_s: float
    network_s: float
    cores: int
    ram_gb: float
    threads: int              # channel threads step 1 would use here
    processes: int            # recording processes steps 3/4 would use here

    def describe(self) -> list[str]:
        return [
            f"Benchmark: {self.seconds:.1f} s  →  relative speed {self.score:.2f}",
            f"  spike detection {self.detection_s:.1f} s on {self.threads} thread(s); "
            f"network null models {self.network_s:.1f} s on {self.processes} process(es)",
            f"  {self.cores} core(s), {self.ram_gb:.0f} GB RAM",
        ]

    def as_dict(self) -> dict:
        return asdict(self)


def _synthetic_recording(scale: float, seed: int = 0) -> np.ndarray:
    """Noise with a sprinkling of spike-shaped events, so the detector has
    templates to build and the timing reflects real work rather than an early
    exit on an empty channel."""
    rng = np.random.default_rng(seed)
    n = int(_DET_FS * _DET_SECONDS * scale)
    dat = rng.normal(0.0, 4.0, (n, _DET_CHANNELS))
    # A biphasic ~1 ms waveform, dropped in at ~5 Hz per channel.
    t = np.arange(int(_DET_FS * 0.0012))
    wave = -40.0 * np.exp(-((t - 8) ** 2) / 18.0) + 12.0 * np.exp(-((t - 20) ** 2) / 40.0)
    for ch in range(_DET_CHANNELS):
        for start in rng.integers(0, max(1, n - len(wave)), size=max(1, int(5 * _DET_SECONDS * scale))):
            dat[start:start + len(wave), ch] += wave
    return dat


def _detection_part(scale: float, threads: int | None) -> float:
    from meanap.pipeline.spike_detection import (
        SpikeDetectionParams, detect_spikes_recording,
    )

    dat = _synthetic_recording(scale)
    channels = np.arange(1, _DET_CHANNELS + 1)
    params = SpikeDetectionParams(fs=_DET_FS)
    t0 = time.perf_counter()
    detect_spikes_recording(dat, channels, _DET_FS, params, max_workers=threads)
    return time.perf_counter() - t0


def _network_task(task: tuple[int, int, int, int]) -> float:
    """One pool task: *models* randomisations of one random weighted graph."""
    from meanap.pipeline.null_models import randmio_und_signed

    seed, n_nodes, models, iterations = task
    rng = np.random.default_rng(seed)
    w = np.abs(rng.normal(0.0, 0.3, (n_nodes, n_nodes)))
    w = (w + w.T) / 2.0
    np.fill_diagonal(w, 0.0)
    w[w < 0.35] = 0.0
    total = 0.0
    for _ in range(models):
        total += float(randmio_und_signed(w, iterations, rng).sum())
    return total


def _network_part(scale: float, processes: int | None) -> float:
    from meanap.pipeline.null_models import randmio_und_signed
    from meanap.pipeline.parallel import map_recordings

    # numba compiles on first call; that is a one-off per process, and it is
    # the *pipeline's* cost too, but including it here would make the score
    # depend on whether the cache was warm. Compile in the parent first.
    randmio_und_signed(np.ones((6, 6)) - np.eye(6), 1, np.random.default_rng(0))
    models = max(1, int(_NET_MODELS_PER_TASK * scale))
    tasks = [(i, _NET_NODES, models, _NET_ITERATIONS) for i in range(_NET_TASKS)]
    t0 = time.perf_counter()
    map_recordings(_network_task, tasks, mem_per_task_gb=0.2, max_workers=processes)
    return time.perf_counter() - t0


def run_benchmark(
    *, scale: float = 1.0, log: Callable[[str], None] | None = None,
    max_threads: int | None = None, max_processes: int | None = None,
) -> BenchmarkResult:
    """Time both parts and return the score.

    *scale* shrinks or grows the work (tests use a small one); the score is
    normalised by it, so a scaled run still lands near what a full one would.
    """
    from meanap.pipeline.parallel import (
        available_ram_gb, physical_cores, suggest_process_count,
        suggest_thread_count,
    )

    threads = suggest_thread_count(_DET_CHANNELS, max_workers=max_threads)
    processes = suggest_process_count(_NET_TASKS, 0.2, max_workers=max_processes)
    if log:
        log(f"Benchmarking this computer ({physical_cores()} cores)…")
    det = _detection_part(scale, max_threads)
    if log:
        log(f"  spike detection: {det:.1f} s")
    net = _network_part(scale, max_processes)
    if log:
        log(f"  network null models: {net:.1f} s")
    seconds = (det + net) / max(scale, 1e-9)
    result = BenchmarkResult(
        seconds=seconds, score=REFERENCE_SECONDS / max(seconds, 1e-6),
        detection_s=det, network_s=net,
        cores=physical_cores(), ram_gb=_total_ram_gb(available_ram_gb()),
        threads=threads, processes=processes,
    )
    if log:
        for line in result.describe():
            log(line)
    return result


def _total_ram_gb(fallback: float) -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / 1e9
    except Exception:                                       # noqa: BLE001
        return fallback
