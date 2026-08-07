"""A local cache for remote files, bounded by a byte budget.

This is what lets a batch larger than the disk run at all: fetch a recording,
analyse it, drop it, fetch the next. The pipeline already works one recording at
a time and — since :mod:`meanap.catnap.derived` — reads each one exactly once,
so peak usage is one recording plus whatever is being fetched ahead, not the
whole dataset.

Two rules keep that safe:

**Pinned files are never evicted.** Anything the current recording needs, and
anything being fetched ahead of it, is pinned. Without this a large prefetch
could evict the file the analysis is reading.

**Presence means completeness.** The cache — not each backend — fetches to a
temporary name and renames into place, so a crashed or cancelled download never
leaves a truncated file that later looks like a cache hit. Centralising it here
means a new backend cannot get it subtly wrong; backends just write to the path
they are handed. Rename is atomic within a filesystem, which is why the
temporary lives beside its target rather than in ``/tmp``. Any ``.part`` left by
a killed process is swept when the cache is opened.

Recency is tracked with the file's own mtime, touched on access, rather than a
separate index — one less thing to corrupt, and it survives restarts.

**Thread-safe by necessity, not ambition.** Prefetching fetches the next
recording while the current one is analysed, so eviction runs concurrently with
reads. Pinning would be worthless if the pin set could be updated non-atomically
while ``make_room`` walked it, so both are serialised under one lock.
"""

from __future__ import annotations

import os
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from meanap.remote.base import ProgressFn, RemoteStore

__all__ = ["FileCache", "CacheFull", "resolve_budget", "DEFAULT_BUDGET_FRACTION",
           "MAX_AUTO_BUDGET_BYTES", "PARTIAL_SUFFIX"]

#: Extension used while a fetch is in flight. Never a valid cache entry.
PARTIAL_SUFFIX = ".part"

#: Share of free disk an auto-sized budget will claim. Deliberately modest:
#: the cache is transient scratch, and filling a user's disk to run an analysis
#: is a worse failure than running slowly.
DEFAULT_BUDGET_FRACTION = 0.25

#: Ceiling on an auto-sized budget. Past this, more cache stops helping —
#: the pipeline only ever needs a couple of recordings resident.
MAX_AUTO_BUDGET_BYTES = 50 * 1000**3


class CacheFull(RuntimeError):
    """The budget cannot accommodate what the run needs.

    Raised up front where possible, with the numbers, rather than after an
    hour of downloading.
    """


def resolve_budget(
    cache_dir: Path | str,
    configured_gb: float | None = None,
    required_bytes: int = 0,
) -> int:
    """Decide the cache budget in bytes, and check it can hold *required_bytes*.

    ``configured_gb`` wins when given. Otherwise a quarter of the free space on
    the cache's own filesystem, capped — measured on the cache directory rather
    than the working directory, since the two are often different disks.
    """
    cache_dir = Path(cache_dir)
    probe = cache_dir
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    free = shutil.disk_usage(probe).free

    if configured_gb is not None:
        budget = int(configured_gb * 1000**3)
        if budget > free:
            raise CacheFull(
                f"Cache budget {configured_gb:.1f} GB exceeds the "
                f"{free / 1000**3:.1f} GB free on {probe}.")
    else:
        budget = int(min(free * DEFAULT_BUDGET_FRACTION, MAX_AUTO_BUDGET_BYTES))

    if required_bytes and required_bytes > budget:
        raise CacheFull(
            f"This run needs {required_bytes / 1000**3:.2f} GB resident at once "
            f"(the largest recording, plus anything fetched ahead of it), but the "
            f"cache budget is {budget / 1000**3:.2f} GB. Raise "
            f"Params.cache_budget_gb, reduce Params.prefetch_depth, or free disk "
            f"space — {free / 1000**3:.1f} GB is currently free on {probe}.")
    return budget


@dataclass
class FileCache:
    """Byte-bounded local store of files fetched from a :class:`RemoteStore`."""

    root: Path
    budget_bytes: int
    _pinned: set[Path] = field(default_factory=set)
    #: Bytes promised to fetches that are in flight. Without this two threads
    #: each pass the budget check, then both download, and the cache overshoots
    #: by however much was being fetched concurrently.
    _reserved: dict = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        # A previous process killed mid-fetch leaves these behind; they are
        # never useful, and they would otherwise count against the budget.
        for stale in self.root.rglob(f"*{PARTIAL_SUFFIX}"):
            try:
                stale.unlink()
            except OSError:
                pass

    # ── layout ───────────────────────────────────────────────────────────────

    def path_for(self, store: RemoteStore, rel_path: str) -> Path:
        """Where a store's file lives locally.

        Mirrors the remote tree under a per-store directory, so the cache is
        browsable and a stale entry can be deleted by hand.
        """
        return self.root / store.store_id / rel_path.strip("/")

    # ── accounting ───────────────────────────────────────────────────────────

    def _files(self) -> list[Path]:
        return [p for p in self.root.rglob("*") if p.is_file()]

    def _size(self, path: Path) -> int:
        """Size, or 0 if it vanished — another thread may be evicting."""
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def usage(self) -> int:
        """Bytes accounted for: complete files, plus fetches in flight.

        A ``.part`` is covered by its reservation (the file's *full* size, not
        the fraction downloaded so far), so counting its bytes on disk as well
        would charge for the same fetch twice.
        """
        with self._lock:
            reserved = sum(self._reserved.values())
        on_disk = sum(self._size(p) for p in self._files()
                      if not p.name.endswith(PARTIAL_SUFFIX))
        return on_disk + reserved

    def free(self) -> int:
        return max(0, self.budget_bytes - self.usage())

    # ── pinning ──────────────────────────────────────────────────────────────

    @contextmanager
    def pinned(self, paths):
        """Protect *paths* from eviction for the duration of the block."""
        resolved = {Path(p) for p in paths}
        with self._lock:
            self._pinned |= resolved
        try:
            yield
        finally:
            with self._lock:
                self._pinned -= resolved

    def pin(self, path: Path) -> None:
        with self._lock:
            self._pinned.add(Path(path))

    def unpin(self, path: Path) -> None:
        with self._lock:
            self._pinned.discard(Path(path))

    def _members(self, base: Path) -> set[Path]:
        """The cached files at *base* — which may itself be one.

        CAT-NAP addresses a recording by its folder, electrophysiology by a
        single file. ``rglob`` yields nothing for a file, so a path that is
        already a file would otherwise pin and evict nothing at all.
        """
        if base.is_file():
            return {base}
        return {p for p in base.rglob("*") if p.is_file()}

    def pin_prefix(self, store: RemoteStore, prefix: str) -> None:
        """Pin everything currently cached at or under *prefix*."""
        base = self.path_for(store, prefix)
        with self._lock:
            self._pinned |= self._members(base)

    def unpin_prefix(self, store: RemoteStore, prefix: str) -> None:
        base = self.path_for(store, prefix)
        with self._lock:
            self._pinned -= self._members(base)

    # ── eviction ─────────────────────────────────────────────────────────────

    def make_room(self, needed: int) -> None:
        """Evict least-recently-used unpinned files until *needed* bytes fit."""
        with self._lock:
            self._make_room_locked(needed)

    def _make_room_locked(self, needed: int) -> None:
        if needed > self.budget_bytes:
            raise CacheFull(
                f"A single file of {needed / 1e6:.0f} MB exceeds the whole cache "
                f"budget of {self.budget_bytes / 1e6:.0f} MB.")
        if self.free() >= needed:
            return

        def mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        candidates = sorted(
            (p for p in self._files() if p not in self._pinned),
            key=mtime,
        )
        for path in candidates:
            if self.free() >= needed:
                return
            try:
                path.unlink()
            except OSError:
                continue

        if self.free() < needed:
            pinned_bytes = sum(self._size(p) for p in self._pinned)
            raise CacheFull(
                f"Cannot free {needed / 1e6:.0f} MB: {pinned_bytes / 1e6:.0f} MB is "
                f"pinned by work in progress and the budget is "
                f"{self.budget_bytes / 1e6:.0f} MB. Raise Params.cache_budget_gb or "
                f"reduce Params.prefetch_depth.")

    def evict(self, store: RemoteStore, rel_path: str) -> None:
        """Drop one cached file. Silent if absent or pinned."""
        path = self.path_for(store, rel_path)
        if path in self._pinned or not path.exists():
            return
        try:
            path.unlink()
        except OSError:
            pass

    def evict_prefix(self, store: RemoteStore, prefix: str) -> int:
        """Drop everything under a subtree, returning bytes reclaimed.

        How a finished recording is released: the pipeline knows when its
        derived outputs are safely written, which the cache cannot infer.
        """
        base = self.path_for(store, prefix)
        if not base.exists():
            return 0
        freed = 0
        with self._lock:
            targets = sorted(self._members(base) - self._pinned, reverse=True)
        for path in targets:
            size = self._size(path)
            try:
                path.unlink()
                freed += size
            except OSError:
                pass
        return freed

    # ── the operation everything else exists for ─────────────────────────────

    def get(
        self, store: RemoteStore, rel_path: str,
        progress: ProgressFn | None = None,
    ) -> Path:
        """Return a local path for *rel_path*, fetching it if necessary.

        For a store that doesn't copy (a local directory) this returns the
        original file and the cache stays empty — no accounting, no eviction,
        nothing duplicated.
        """
        if not store.copies:
            return store.fetch(rel_path, self.root)

        target = self.path_for(store, rel_path)
        if target.exists():
            os.utime(target, None)  # mark as most recently used
            if progress is not None:
                size = target.stat().st_size
                progress(size, size)
            return target

        entry = store.stat(rel_path)
        # Reserve space and claim the destination under one lock, so two
        # prefetch threads cannot each pass the budget check and then both
        # write.
        size = entry.size if entry and entry.size else 0
        partial = target.with_name(target.name + PARTIAL_SUFFIX)
        # Reserve, pin and claim the destination under one lock. The download
        # itself runs outside it — serialising fetches would defeat prefetching
        # — so the reservation is what keeps concurrent fetches inside budget,
        # and the pin is what stops one thread evicting another's partial.
        with self._lock:
            self._make_room_locked(size)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._pinned |= {target, partial}
            self._reserved[partial] = size
        try:
            try:
                store.fetch(rel_path, partial, progress)
                partial.replace(target)
            except BaseException:
                # Includes KeyboardInterrupt: a cancelled run must not leave
                # something that the next run treats as a complete cached file.
                partial.unlink(missing_ok=True)
                raise
        finally:
            with self._lock:
                self._reserved.pop(partial, None)
                self._pinned -= {target, partial}
        return target
