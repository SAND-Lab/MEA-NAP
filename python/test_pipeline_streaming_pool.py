"""Parallel network metrics must not change what a CAT-NAP run produces.

Run from the repo root::

    uv run python python/test_pipeline_streaming_pool.py

CAT-NAP's phase 1 hands each recording's network metrics to a
:class:`~meanap.pipeline.parallel.StreamingPool` as the (possibly remote)
stream yields it. Two properties have to hold for that to be safe:

1. **Results do not depend on the worker count or on completion order.** Each
   recording's generator is seeded from its own filename, so concurrency
   cannot reach the numbers. This is what lets the run be parallel and still
   reproduce a serial run byte for byte.
2. **The pool bounds how far the producer runs ahead.** Without that the
   parent would queue every remaining recording's adjacency matrices in
   memory while the workers fell behind — gigabytes on a large batch, and
   exactly the thing the streaming source exists to avoid.

The worker functions here are module-level because ``spawn`` (the start
method, chosen for macOS/Windows compatibility) re-imports this module in
every worker.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.pipeline import _MetricsTask, _metrics_worker  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.parallel import StreamingPool  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def _square(x: int) -> int:
    """Trivial pool payload — must be importable for spawn."""
    return x * x


def _slow_square(x: int) -> int:
    time.sleep(0.05)
    return x * x


def _boom(x: int) -> int:
    raise ValueError(f"worker refused {x}")


def _die_in_worker(x: int) -> int:
    """Kill the worker process outright, but compute normally in the parent.

    Stands in for the ways a pool really dies — most often a caller with no
    ``if __name__ == "__main__":`` guard, since spawn re-imports the parent's
    ``__main__``; an OOM kill looks the same from here.
    """
    import multiprocessing
    import os

    if multiprocessing.current_process().name != "MainProcess":
        os._exit(1)
    return x * x


def make_network(n: int, density: float, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    w = r.random((n, n)) * (r.random((n, n)) < density)
    w = np.triu(w, 1)
    return w + w.T


def digest(results: dict) -> str:
    """Order-independent fingerprint of a whole batch's metrics."""
    import hashlib
    parts = []
    for name in sorted(results):
        for lag in sorted(results[name]):
            for key in sorted(results[name][lag]):
                v = np.asarray(results[name][lag][key], dtype=float).ravel()
                v = np.nan_to_num(v, nan=-7.77, posinf=-8.88, neginf=-9.99)
                parts.append(f"{name}|{lag}|{key}|" + ",".join(f"{x:.17g}" for x in v))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def run_batch(tasks: list[_MetricsTask], workers: int) -> dict:
    out: dict = {}
    with StreamingPool(workers, on_result=lambda r: out.__setitem__(r[0], r[1])) as pool:
        for t in tasks:
            pool.submit(_metrics_worker, t)
        pool.drain()
    return out


def main() -> None:
    print("[1] StreamingPool basics")

    with StreamingPool(1) as pool:
        for i in range(5):
            pool.submit(_square, i)
        got = pool.drain()
    check("one worker runs inline (no processes)", sorted(got) == [0, 1, 4, 9, 16],
          str(got))
    check("a one-worker pool reports itself serial", not StreamingPool(1).parallel)

    with StreamingPool(3) as pool:
        check("a multi-worker pool reports itself parallel", pool.parallel)
        for i in range(12):
            pool.submit(_square, i)
        got = pool.drain()
    check("every task completes across workers",
          sorted(got) == sorted(i * i for i in range(12)), str(sorted(got)))

    # The producer must be held back once the pool saturates. With 2 workers
    # the bound is 4, so submitting 12 slow tasks cannot return before at
    # least (12 - 4) of them have actually completed.
    pool = StreamingPool(2, max_pending=4)
    submitted = 0
    try:
        t0 = time.perf_counter()
        for i in range(12):
            pool.submit(_slow_square, i)
            submitted += 1
        elapsed_at_last_submit = time.perf_counter() - t0
        pool.drain()
    finally:
        pool.close()
    # 8 tasks x 50ms across 2 workers = 200ms of unavoidable waiting.
    check("submit blocks once the pool is full",
          elapsed_at_last_submit > 0.15,
          f"returned after only {elapsed_at_last_submit:.3f}s")

    # A stop must drop queued work rather than waiting out the whole batch.
    # The flag flips after the first result, so most of the 40 tasks should
    # never run — with a 4-deep pool at most a handful are already in flight.
    stop = []
    done_count = []

    def _record(r: int) -> None:
        done_count.append(r)
        stop.append(True)

    pool = StreamingPool(2, max_pending=4, on_result=_record,
                         cancel_check=lambda: bool(stop))
    try:
        for i in range(40):
            pool.submit(_slow_square, i)
        pool.drain()
    finally:
        pool.close()
    check("a cancel stops the pool dispatching further work",
          len(done_count) < 40, f"{len(done_count)}/40 tasks still ran")

    # Whether workers would re-run the caller's script is read off the entry
    # point, since it cannot be probed: a child that survives its own nested
    # pool attempt still completes its task, so the parent sees a healthy pool
    # while every worker has quietly re-run the script (and, for a pipeline
    # script, re-written its output folder).
    import sys
    import tempfile

    from meanap.pipeline import parallel as par

    main_mod = sys.modules["__main__"]
    original = getattr(main_mod, "__file__", None)
    cases = [
        ("guarded script", 'x = 1\nif __name__ == "__main__":\n    pass\n', False),
        ("unguarded script", "x = 1\nprint(x)\n", True),
        ("guard on __name__ compared the other way",
         'if "__main__" == __name__:\n    pass\n', False),
    ]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for label, src, expected in cases:
                f = Path(tmp) / f"{label.replace(' ', '_')}.py"
                f.write_text(src)
                main_mod.__file__ = str(f)
                check(f"entry-point check: {label}",
                      par._entry_point_reruns_itself() is expected,
                      f"got {par._entry_point_reruns_itself()}, want {expected}")
        main_mod.__file__ = None
        check("entry-point check: no file (REPL / -c) is treated as safe",
              par._entry_point_reruns_itself() is False)
    finally:
        if original is None:
            main_mod.__dict__.pop("__file__", None)
        else:
            main_mod.__file__ = original

    # A dead pool must finish the work on one core rather than fail the run.
    warned: list[str] = []
    with StreamingPool(2, on_degrade=warned.append) as pool:
        for i in range(6):
            pool.submit(_die_in_worker, i)
        got = pool.drain()
    check("a dead pool falls back to serial instead of failing the run",
          sorted(got) == sorted(i * i for i in range(6)), str(sorted(got)))
    check("…and says why", bool(warned) and "one core" in warned[0],
          str(warned))

    raised = None
    try:
        with StreamingPool(2) as pool:
            for i in range(4):
                pool.submit(_boom, i)
            pool.drain()
    except Exception as e:  # noqa: BLE001
        raised = e
    check("a failing worker surfaces its error rather than being swallowed",
          isinstance(raised, ValueError), repr(raised))

    print()
    print("[2] metrics are independent of worker count")

    p = Params()
    p.suite2p_mode = True
    p.random_seed = 0
    # Sizes and densities spanning what a calcium batch actually contains,
    # including the near-complete networks a 1000ms lag produces.
    shapes = [(24, 0.30), (40, 0.95), (31, 1.00), (18, 0.10), (45, 0.75),
              (12, 0.50), (37, 0.99), (28, 0.60)]
    tasks = []
    for i, (n, dens) in enumerate(shapes):
        adj = make_network(n, dens, seed=i)
        tasks.append(_MetricsTask(
            filename=f"rec{i:02d}", adjMs={"adjM1000mslag": adj},
            spike_counts=np.full(n, 20.0), duration_s=600.0,
            lag_independent={}, params=p, min_nodes=3))

    serial = run_batch(tasks, 1)
    parallel = run_batch(tasks, 4)
    check("all recordings come back from the pool",
          set(serial) == set(parallel) == {t.filename for t in tasks},
          f"{sorted(serial)} vs {sorted(parallel)}")
    check("4 workers reproduce the serial result exactly",
          digest(serial) == digest(parallel),
          f"{digest(serial)} != {digest(parallel)}")

    # Submission order must not matter either: with a pool, completion order
    # already varies run to run, so the numbers must not depend on sequence.
    shuffled = run_batch(list(reversed(tasks)), 3)
    check("reversing submission order changes nothing",
          digest(serial) == digest(shuffled),
          f"{digest(serial)} != {digest(shuffled)}")

    # Multiple lags per recording share one generator, in lag order — so a
    # second lag must not be affected by which recordings ran alongside it.
    multi = []
    for i, (n, dens) in enumerate(shapes[:4]):
        adj = make_network(n, dens, seed=i)
        multi.append(_MetricsTask(
            filename=f"multi{i:02d}",
            adjMs={"adjM1000mslag": adj, "adjM2500mslag": make_network(n, dens, seed=100 + i)},
            spike_counts=np.full(n, 20.0), duration_s=600.0,
            lag_independent={"effRank": float(i)}, params=p, min_nodes=3))
    check("multi-lag recordings match too",
          digest(run_batch(multi, 1)) == digest(run_batch(multi, 4)))
    check("lag-independent fields are carried onto every lag",
          all(r["1000mslag"]["effRank"] == r["2500mslag"]["effRank"]
              for r in run_batch(multi, 2).values()))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("All streaming-pool checks passed.")


if __name__ == "__main__":
    main()
