"""Resource-aware parallel execution helpers for the pipeline.

The pipeline has two very different parallelism profiles, and a single
"number of workers" knob would be wrong for both:

* **Step 1 (spike detection) is RAM-bound.** Each recording's raw ``dat``
  array is ~3.8 GB in memory (64 ch x 7.5M samples x float64). Running
  recordings in separate *processes* would duplicate that per worker, so on
  a 16 GB machine you could fit only ~2 before swapping. But the per-channel
  work (``scipy.signal.filtfilt`` + ``numpy.fft``) releases the GIL, so
  Step 1 parallelizes cleanly across *threads over channels* on one shared
  copy of ``dat`` — no extra RAM, cores saturated. Use
  :func:`suggest_thread_count` there.

* **Steps 3/4 are CPU-bound and low-RAM.** They work on spike times and
  64x64 matrices (tens of MB), and their hot loop (``randmio_und_signed``)
  is pure Python, so the GIL blocks threads — they need *processes over
  recordings*. RAM per worker is small, so worker count is CPU-limited. Use
  :func:`suggest_process_count` there, and :func:`worker_env` to stop each
  worker's BLAS from spawning its own thread pool (which would oversubscribe
  cores N-fold).

Everything degrades safely: if ``psutil`` is unavailable the RAM query falls
back to a conservative assumption, and every ``suggest_*`` returns at least 1.
Passing ``max_workers=1`` anywhere gives a fully serial path for debugging.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from typing import Callable, Optional, TypeVar

try:
    import psutil

    _HAVE_PSUTIL = True
except ImportError:  # pragma: no cover - psutil is normally installed
    _HAVE_PSUTIL = False

T = TypeVar("T")
R = TypeVar("R")

# Conservative assumption when we cannot measure RAM: pretend a 16 GB machine
# with ~10 GB actually free. Better to under-parallelize than to OOM.
_FALLBACK_AVAILABLE_GB = 10.0


def physical_cores() -> int:
    """Physical core count (falls back to logical, then 1)."""
    if _HAVE_PSUTIL:
        cores = psutil.cpu_count(logical=False)
        if cores:
            return cores
    return os.cpu_count() or 1


def available_ram_gb() -> float:
    """Currently-available RAM in GB, or a conservative fallback."""
    if _HAVE_PSUTIL:
        return psutil.virtual_memory().available / 1e9
    return _FALLBACK_AVAILABLE_GB


def suggest_process_count(
    n_tasks: int,
    mem_per_task_gb: float,
    *,
    reserve_gb: float = 2.0,
    cpu_headroom: int = 1,
    max_workers: Optional[int] = None,
) -> int:
    """Pick a process-pool size bounded by cores *and* free RAM.

    Parameters
    ----------
    n_tasks : number of independent work items (e.g. recordings). Never
        spawn more workers than tasks.
    mem_per_task_gb : peak resident memory one worker needs. This is the
        knob that keeps a 16 GB machine alive — for Step 1 recording-level
        work pass ~5.0 (3.8 GB load + filter copies); for Steps 3/4 pass
        ~0.3.
    reserve_gb : RAM to leave for the OS / GUI / parent process.
    cpu_headroom : cores to leave free (keeps the UI responsive; 1 is a good
        default for a desktop app).
    max_workers : hard user-facing cap, if any.

    Returns at least 1.
    """
    cpu_cap = max(1, physical_cores() - cpu_headroom)

    if mem_per_task_gb and mem_per_task_gb > 0:
        usable = max(0.0, available_ram_gb() - reserve_gb)
        mem_cap = max(1, int(usable // mem_per_task_gb))
    else:
        mem_cap = cpu_cap

    n = min(n_tasks, cpu_cap, mem_cap)
    if max_workers is not None:
        n = min(n, max_workers)
    return max(1, n)


def suggest_thread_count(
    n_tasks: int,
    *,
    cpu_headroom: int = 1,
    max_workers: Optional[int] = None,
) -> int:
    """Pick a thread-pool size for GIL-releasing work (Step 1's channel loop).

    Threads share memory, so RAM is not a factor here — only cores and the
    task count. Returns at least 1.
    """
    cpu_cap = max(1, physical_cores() - cpu_headroom)
    n = min(n_tasks, cpu_cap)
    if max_workers is not None:
        n = min(n, max_workers)
    return max(1, n)


# BLAS/OpenMP libraries default to one thread *per physical core*. Inside a
# process pool that multiplies: N worker processes x C BLAS threads each =
# N*C threads fighting over C cores. Pin each worker to a single BLAS thread.
_BLAS_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",  # Apple Accelerate / M-series
)


def worker_env(threads: str = "1") -> dict[str, str]:
    """Environment overrides for pool workers: pin BLAS/OpenMP to ``threads``
    and force matplotlib's headless Agg backend (spawned workers have no Qt
    event loop, so any GUI backend would error on import). Harmless for
    non-plotting workers.
    """
    env = {var: threads for var in _BLAS_ENV_VARS}
    env["MPLBACKEND"] = "Agg"
    return env


def pin_blas_threads(threads: str = "1") -> None:
    """Process-pool ``initializer``: pin this worker's BLAS thread count.

    Must run *before* numpy/scipy/sklearn import their BLAS backend in the
    worker to take effect, so use it as the pool ``initializer`` (workers are
    forked/spawned fresh) rather than calling it mid-run.
    """
    os.environ.update(worker_env(threads))


#: Cached across the session — whether ``__main__`` is guarded cannot change.
_SPAWN_USABLE: Optional[bool] = None


def spawn_usable() -> bool:
    """Whether worker processes can be started without re-running the caller.

    ``spawn`` — the only start method available on all of macOS, Windows and
    Linux — re-imports the parent's ``__main__`` in every worker. When the
    entry point is a script that starts a run at module scope, with no
    ``if __name__ == "__main__":`` guard, each worker therefore re-executes
    the whole script before getting to its task. For a pipeline script that
    means running the pipeline again, per worker, writing to the same output
    folder: not merely wasteful but a way to corrupt a run.

    Python's own recursion check does not reliably stop it — a child that
    survives its nested pool attempt goes on to complete its task, so the
    parent sees a perfectly healthy pool and never learns that every worker
    re-ran its script. Probing cannot detect this; only reading the entry
    point can. So the main module is parsed once, and a script without a
    guard runs serially.

    Anything not a readable script — the REPL, ``-c``, a frozen build, a
    console-script wrapper (which generates its own guard) — is treated as
    safe, which is what those all are.
    """
    global _SPAWN_USABLE
    if _SPAWN_USABLE is None:
        _SPAWN_USABLE = not _entry_point_reruns_itself()
    return _SPAWN_USABLE


def _entry_point_reruns_itself() -> bool:
    """True when ``__main__`` is a script whose top level would re-run."""
    import ast
    import sys

    if getattr(sys, "frozen", False):
        return False  # freeze_support handles this case
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    if not path:
        return False  # interactive / -c: spawn re-imports nothing
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - unreadable/odd entry point: assume fine
        return False
    for node in tree.body:
        if isinstance(node, ast.If) and "__name__" in ast.dump(node.test):
            return False
    return True


_NO_WORKERS_MSG = (
    "could not start worker processes — continuing on one core. If this run "
    "was started from a script, putting the call behind "
    '`if __name__ == "__main__":` restores parallelism.'
)


class StreamingPool:
    """A process pool fed one task at a time, as work becomes available.

    :func:`map_recordings` wants the whole task list up front. The CAT-NAP path
    cannot give it one: its recordings arrive from a remote source that fetches,
    computes and then *releases* each one before starting the next, so a batch's
    peak local storage stays at one or two recordings instead of the whole
    dataset. Collecting every task before dispatching would either defeat that
    (holding the entire dataset on disk) or idle every core until the last
    download landed.

    So tasks are submitted as the stream yields them and results are collected
    as they finish. ``max_pending`` bounds how far the producer may run ahead —
    without it the parent would queue every remaining recording's adjacency
    matrices in memory, which on a large batch is gigabytes. When the bound is
    reached :meth:`submit` blocks until a result comes back, which is the
    correct steady state for compute-bound work.

    Results come back in completion order, so callers that need a stable
    ordering should key them (by recording name) rather than relying on
    position — the same contract as :func:`map_recordings`.
    """

    def __init__(
        self,
        n_workers: int,
        *,
        max_pending: Optional[int] = None,
        blas_threads: Optional[str] = None,
        on_result: Optional[Callable[[R], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        on_degrade: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._cancel_check = cancel_check
        self._on_degrade = on_degrade
        self._cancelled = False
        # Tasks still in flight, so a pool that dies can be re-run serially.
        self._task_of: dict = {}
        self._n = max(1, n_workers)
        # Two per worker keeps every core fed while one result is being
        # harvested, without letting the producer run away.
        self._max_pending = max_pending if max_pending is not None else max(2 * self._n, 4)
        self._on_result = on_result
        self._results: list = []
        self._pending: set = set()
        self._ex = None
        if self._n > 1 and not spawn_usable():
            if on_degrade is not None:
                on_degrade(_NO_WORKERS_MSG)
        elif self._n > 1:
            if blas_threads is None:
                blas_threads = str(max(1, physical_cores() // self._n))
            ctx = mp.get_context("spawn")
            self._ex = ProcessPoolExecutor(
                max_workers=self._n, mp_context=ctx,
                initializer=pin_blas_threads, initargs=(blas_threads,),
            )

    @property
    def parallel(self) -> bool:
        """False when this degraded to the serial path (one worker)."""
        return self._ex is not None

    def submit(self, worker_fn: Callable[[T], R], task: T) -> None:
        """Queue one task, blocking while the pool is saturated.

        With a single worker the task runs inline, so the same call site serves
        the serial path — useful for debugging and for single-recording runs.
        """
        if self._cancelled:
            return
        if self._ex is None:
            self._collect(worker_fn(task))
            if self._cancel_check is not None and self._cancel_check():
                self._cancelled = True
            return
        while len(self._pending) >= self._max_pending:
            self._harvest()
            if self._cancelled:
                return
        if self._ex is None:  # the pool died while we were harvesting
            self._collect(worker_fn(task))
            return
        fut = self._ex.submit(worker_fn, task)
        self._task_of[fut] = (worker_fn, task)
        self._pending.add(fut)

    def _harvest(self) -> None:
        """Block until at least one in-flight task completes, and collect it.

        A cancel is noticed here rather than only between submissions, so a
        run stopped while the pool is draining drops everything not yet
        started instead of waiting out the whole queue. Work already running
        still finishes — the same cooperative stop :func:`map_recordings`
        gives, bounded by one task rather than the batch.
        """
        if not self._pending:
            return
        done, self._pending = wait(self._pending, return_when=FIRST_COMPLETED)
        for fut in done:
            if fut.cancelled():
                self._task_of.pop(fut, None)
                continue
            try:
                result = fut.result()
            except BrokenProcessPool:
                self._degrade(done)
                return
            self._task_of.pop(fut, None)
            self._collect(result)
        if self._cancel_check is not None and self._cancel_check():
            self._cancelled = True
            for fut in self._pending:
                fut.cancel()

    def _degrade(self, done: set) -> None:
        """The worker processes died. Finish the outstanding work in-process.

        Much the commonest cause is a caller with no ``if __name__ ==
        "__main__":`` guard: ``spawn`` re-imports the parent's ``__main__`` in
        every worker, so a script that starts a run at module scope re-runs
        itself in the child, and Python kills the child rather than let it
        recurse. That is a property of the calling script, not of the work, and
        a library has no business turning it into a failed run — an
        out-of-memory kill deserves the same treatment. So the pool is
        abandoned and everything it had not returned is redone here, serially.
        """
        outstanding = [self._task_of[f]
                       for f in list(done) + list(self._pending)
                       if f in self._task_of]
        for fut in self._pending:
            fut.cancel()
        self._pending = set()
        self._task_of = {}
        if self._ex is not None:
            self._ex.shutdown(wait=False, cancel_futures=True)
            self._ex = None
        if self._on_degrade is not None:
            self._on_degrade(_NO_WORKERS_MSG)
        for worker_fn, task in outstanding:
            self._collect(worker_fn(task))

    def _collect(self, result: R) -> None:
        if self._on_result is not None:
            self._on_result(result)
        self._results.append(result)

    def drain(self) -> list:
        """Wait for everything still in flight and return all results."""
        while self._pending:
            self._harvest()
        return self._results

    def close(self) -> None:
        if self._ex is not None:
            self._ex.shutdown(wait=True)
            self._ex = None

    def __enter__(self) -> "StreamingPool":
        return self

    def __exit__(self, *exc) -> None:
        # Cancel anything not yet started, then let in-flight tasks finish —
        # the same cooperative stop map_recordings gives a cancelled run.
        if exc[0] is not None:
            for fut in self._pending:
                fut.cancel()
        self.close()


def map_recordings(
    worker_fn: Callable[[T], R],
    tasks: list[T],
    *,
    mem_per_task_gb: float,
    max_workers: Optional[int] = None,
    on_result: Optional[Callable[[R], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    blas_threads: Optional[str] = None,
) -> list[R]:
    """Run ``worker_fn`` over ``tasks`` in a RAM/CPU-aware process pool.

    This is the "map" half of the pipeline's map→reduce→map structure: each
    task is one independent recording that writes its own output files and
    returns a small, picklable result for the caller to aggregate (fold batch
    bounds, pool PC/Z for cartography, etc.). Because results come back via
    pickling, keep them small — return scalars/paths, not multi-GB arrays.

    ``worker_fn`` must be importable (module-level), since ``spawn`` re-imports
    it in each worker. Workers get BLAS pinned to ``blas_threads`` so N
    processes don't each spin up C BLAS threads.

    ``on_result`` is called in the *parent* as each task finishes (good for
    streaming log lines back in completion order). ``cancel_check`` (evaluated
    in the parent between completions) stops new tasks from being dispatched
    and drops any not-yet-started ones; in-flight tasks run to completion
    (bounded, cooperative stop). A plain callable works for both the serial
    and process paths since nothing is passed into workers.

    Falls back to a fully serial loop when the pool would be size 1 — same
    code path for single-recording runs and for debugging.
    """
    n = suggest_process_count(
        len(tasks), mem_per_task_gb, max_workers=max_workers,
    )

    # Adaptive BLAS threads: when workers < cores (few recordings, many cores),
    # pinning each worker's BLAS to 1 would leave most cores idle and throttle
    # BLAS-heavy work (e.g. sklearn NMF). Give each worker its fair share of
    # cores instead — cores//n — which fills the machine yet still collapses to
    # 1 when workers ~= cores (many recordings), avoiding oversubscription.
    if blas_threads is None:
        blas_threads = str(max(1, physical_cores() // max(1, n)))

    results: list[R] = []

    # ``spawn_usable`` keeps an unguarded caller on the serial path instead of
    # letting every worker re-run its script and then die — see that function.
    if n <= 1 or len(tasks) <= 1 or not spawn_usable():
        for t in tasks:
            if cancel_check is not None and cancel_check():
                break
            r = worker_fn(t)
            if on_result is not None:
                on_result(r)
            results.append(r)
        return results

    # spawn: the only start method available on all of macOS/Windows/Linux,
    # and it guarantees workers re-import cleanly (no inherited fork state).
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=n, mp_context=ctx,
        initializer=pin_blas_threads, initargs=(blas_threads,),
    ) as ex:
        pending = set()
        it = iter(tasks)
        # Prime the pool with up to n tasks, then top up as each completes —
        # this keeps at most n futures alive and lets a cancel drop the rest.
        for _ in range(n):
            try:
                pending.add(ex.submit(worker_fn, next(it)))
            except StopIteration:
                break
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                r = fut.result()
                if on_result is not None:
                    on_result(r)
                results.append(r)
            if cancel_check is not None and cancel_check():
                for fut in pending:
                    fut.cancel()
                break
            for _ in range(len(done)):
                try:
                    pending.add(ex.submit(worker_fn, next(it)))
                except StopIteration:
                    break
    return results
