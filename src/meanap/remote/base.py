"""What MEA-NAP needs from a place raw data lives.

Deliberately three operations, not a filesystem. Everything the pipeline does
with raw data reduces to *list a folder*, *ask how big a file is*, and *get me
the bytes* — it never seeks, appends, or writes back (once
:mod:`meanap.catnap.derived` moved the derived files out). Keeping the protocol
that small is what lets a scraped share-link backend satisfy it as honestly as
a local directory does.

Two properties matter more than they look:

``size`` **comes from listing.** Both backends report sizes without
transferring anything, which is what makes a pre-flight estimate — total
download, time, peak disk — possible before a run starts rather than
discovered at recording eleven of thirteen.

``store_id`` **identifies the source, not the URL.** The cache is keyed by it,
so the same dataset reached through a re-issued link is still a cache hit, and
two different datasets can never collide.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

__all__ = ["RemoteEntry", "RemoteStore", "ProgressFn", "store_id_for"]

#: Called with ``(bytes_so_far, total_or_None)`` during a fetch.
ProgressFn = Callable[[int, "int | None"], None]


@dataclass(frozen=True)
class RemoteEntry:
    """One item in a store, addressed by a POSIX path relative to its root."""

    path: str
    is_dir: bool
    size: int | None = None

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@runtime_checkable
class RemoteStore(Protocol):
    """A read-only source of recordings."""

    #: Stable identity of the underlying data, used to key the cache.
    store_id: str

    #: Whether :meth:`fetch` copies bytes. ``False`` for a local directory,
    #: which hands back the original path — a local run must never duplicate
    #: gigabytes just to satisfy an abstraction.
    copies: bool

    def list(self, path: str = "") -> list[RemoteEntry]:
        """Entries directly under *path*. Empty list if it isn't a folder."""

    def stat(self, path: str) -> RemoteEntry | None:
        """Metadata for one path, or ``None`` if absent."""

    def fetch(self, path: str, dest: Path, progress: ProgressFn | None = None) -> Path:
        """Materialise *path* locally and return where it landed.

        Implementations must be safe to call when *dest* already holds a
        complete copy, and must not leave a partial file behind on failure —
        the cache treats "the file is there" as "the file is whole".
        """


def store_id_for(*parts: str) -> str:
    """A short, stable id from whatever identifies a source."""
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:16]
