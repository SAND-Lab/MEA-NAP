"""Fetch the next recording while the current one is being analysed.

The pipeline is a loop over recordings that are independent until the batch-wide
barrier, and analysing one takes far longer than fetching it — measured on the
CAT-NAP example data, roughly 275 s of compute against 95 s of transfer. Run
serially that transfer is dead time; overlapped, it disappears.

The generator here is deliberately the whole mechanism. Fetching runs on one
background thread with a bounded lookahead, so at any moment at most
``depth + 1`` recordings are resident — which is exactly the quantity the cache
budget is checked against in pre-flight. Deeper lookahead buys nothing once
compute dominates and costs another recording's worth of disk.

A failed fetch is yielded as the exception rather than raised, so one
unreadable recording skips that recording instead of ending the batch.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Iterable, Iterator, TypeVar

__all__ = ["stream_ahead"]

T = TypeVar("T")
R = TypeVar("R")


def stream_ahead(
    items: Iterable[T],
    fetch: Callable[[T], R],
    *,
    depth: int = 1,
    on_yield: Callable[[T], None] | None = None,
) -> Iterator[tuple[T, R | BaseException]]:
    """Yield ``(item, fetched)`` in order, keeping *depth* fetches in flight.

    ``fetch`` runs on a worker thread. Results are yielded strictly in the
    original order — the pipeline's batch statistics depend on recordings being
    processed in spreadsheet order, and a "whichever finishes first" stream
    would quietly change which recordings pair with which.

    ``on_yield`` is called just before each item is handed over, after its
    fetch completed: the hook the caller uses to pin what it is about to read.
    """
    depth = max(0, depth)
    iterator = iter(items)
    pending: deque[tuple[T, Future]] = deque()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="meanap-prefetch") as pool:
        def submit_next() -> bool:
            try:
                item = next(iterator)
            except StopIteration:
                return False
            pending.append((item, pool.submit(fetch, item)))
            return True

        for _ in range(depth + 1):
            if not submit_next():
                break

        while pending:
            item, future = pending.popleft()
            try:
                result: R | BaseException = future.result()
            except BaseException as exc:  # noqa: BLE001 - handed to the caller
                result = exc
            if on_yield is not None and not isinstance(result, BaseException):
                on_yield(item)
            yield item, result
            # Queue the next one only now, so the number resident stays bounded
            # by what the caller has actually finished with.
            submit_next()
