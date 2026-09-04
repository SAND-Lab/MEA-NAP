"""Where the pipeline gets a recording's raw data from.

Both analysis paths want ordinary local files: CAT-NAP a ``suite2p/plane0``
directory, electrophysiology a single ``.mat``/``.h5``/``.raw``. This produces
them, whether the data is already on disk or has to be fetched — and for the
remote case, fetches the *next* recording while the current one is analysed and
drops each one as soon as its results are safely written.

Three decisions make that work without touching the loaders:

**The cache mirrors the remote tree**, so a fetched folder or file is an
ordinary path. Nothing downstream knows or cares where it came from.

**Only the files the pipeline opens are fetched.** The listing gives names and
sizes for free, so the ``.csv`` exports, ``Fneu.npy`` and ``stat.xlsx`` that
suite2p writes alongside — about a fifth of a folder — are never transferred.

**Releases are reference-counted.** One Axion ``.raw`` holds a whole plate and
MEA-NAP treats each well as its own recording, so several recordings share a
file. Evicting it when the first of them finishes would re-download it for the
next; the count is what prevents that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

from meanap.remote.base import RemoteStore
from meanap.remote.cache import FileCache
from meanap.remote.preflight import (
    CATNAP_OPTIONAL, CATNAP_REQUIRED, EPHYS_EXTENSIONS,
)
from meanap.remote.prefetch import stream_ahead

__all__ = ["RecordingSource", "SUITE2P_SUBDIR", "stream_needing_work"]

SUITE2P_SUBDIR = "suite2p/plane0"

#: Everything :func:`load_suite2p` may open, in one set.
WANTED = frozenset(CATNAP_REQUIRED) | frozenset(CATNAP_OPTIONAL)


@dataclass
class RecordingSource:
    """Supplies local ``plane0`` directories, fetching and evicting as needed."""

    store: RemoteStore
    cache: FileCache | None = None
    log: Callable[[str], None] = print
    #: Spreadsheet name → the folder that actually holds it, from pre-flight.
    #: Applying it here means neither the spreadsheet nor the data folder has
    #: to be edited for a run to find its recordings.
    name_map: dict = field(default_factory=dict)
    #: Optional :class:`~meanap.pipeline.progress.RunProgress`, told how many
    #: bytes have arrived. Reported from here rather than from the cache because
    #: only this knows the transfer is one run's worth of work.
    progress: object | None = None
    #: Where CAT-NAP's derived files live, so a fetch can tell what an earlier
    #: run already extracted. See :meth:`_wanted_for`.
    derived_root: str | Path | None = None
    #: cache-relative path → how many not-yet-released recordings still need it.
    _holders: dict = field(default_factory=dict, repr=False)
    #: Bytes fetched so far this run, across every file. Not guarded: prefetch
    #: runs on a single worker thread (``stream_ahead``'s pool is size 1), so
    #: only one fetch is ever in flight.
    _fetched: int = field(default=0, repr=False)

    @property
    def remote(self) -> bool:
        return self.store.copies

    def folder(self, recording: str) -> str:
        return self.name_map.get(recording, recording)

    def _hold(self, recording: str, rel: str) -> None:
        """Record that *recording* is using *rel*, so a shared file survives."""
        self._holders.setdefault(rel, set()).add(recording)

    def _rels_for(self, recording: str) -> list[str]:
        return [rel for rel, users in self._holders.items() if recording in users]

    def _fetch(self, rel: str, detail: str = ""):
        """``cache.get``, keeping the run's transfer counter up to date.

        The cache reports bytes per file; a run wants one running total, and one
        that doesn't lurch when a file turns out to be cached already.
        """
        if self.progress is None:
            return self.cache.get(self.store, rel)

        base = self._fetched
        self.progress.transferred(base, detail=detail)
        seen = 0

        def report(done: int, total: int | None) -> None:
            nonlocal seen
            seen = done
            self.progress.transferred(base + done, detail=detail)

        try:
            return self.cache.get(self.store, rel, report)
        finally:
            self._fetched = base + seen

    def _wanted_for(self, recording: str) -> frozenset:
        """Which of :data:`WANTED` this recording still has to be fetched for.

        ``ops.npy`` is the whole set bar a rounding error — 463 MB of a 480 MB
        folder in this dataset — and the pipeline wants two small fields out of
        it, the frame rate and the mean projection. :func:`load_suite2p` reads
        those from the ``ops_fields.npz`` sidecar whenever one exists and never
        opens ``ops.npy`` at all, so once an earlier run has written the sidecar
        there is nothing left for the download to supply. Re-running a batch
        with different parameters then costs a twentieth of the first pass.

        The sidecar carries no parameters — it is a verbatim copy of two
        suite2p fields — so it stays valid across runs, and
        :func:`~meanap.catnap.loader._load_ops_fields` still discards one older
        than the ``ops.npy`` it came from.
        """
        from meanap.catnap.derived import OPS_CACHE_NAME, derived_dir

        cached = derived_dir(self.derived_root, recording)
        if cached is not None and (cached / OPS_CACHE_NAME).exists():
            return WANTED - {"ops.npy"}
        return WANTED

    def plane0(self, recording: str) -> Path:
        """A local ``suite2p/plane0`` for *recording*, fetching it if remote.

        Raises :class:`FileNotFoundError` when the recording has no suite2p
        output, which the caller reports as a skip.
        """
        rel = f"{self.folder(recording)}/{SUITE2P_SUBDIR}"
        if not self.remote:
            local = self.store.fetch_dir_path(rel) if hasattr(
                self.store, "fetch_dir_path") else Path(self.store.root) / rel
            if not (local / "stat.npy").exists():
                raise FileNotFoundError(f"no suite2p output at {local}")
            return local

        if self.cache is None:
            raise ValueError("A remote source needs a cache.")

        entries = [e for e in self.store.list(rel) if not e.is_dir]
        if not entries:
            raise FileNotFoundError(f"no suite2p output at {rel}")

        keep = self._wanted_for(recording)
        wanted = [e for e in entries if e.name in keep]
        skipped = sum(e.size or 0 for e in entries if e.name not in WANTED)
        cached_ops = sum(e.size or 0 for e in entries
                         if e.name in WANTED and e.name not in keep)
        total = sum(e.size or 0 for e in wanted)
        self.log(f"  [{recording}] fetching {total / 1e6:.0f} MB"
                 + (f" (skipping {skipped / 1e6:.0f} MB the pipeline never opens)"
                    if skipped else "")
                 + (f" (skipping {cached_ops / 1e6:.0f} MB of ops.npy — already "
                    "extracted by an earlier run)" if cached_ops else ""))
        for entry in wanted:
            self._fetch(entry.path, detail=recording)
        return self.cache.path_for(self.store, rel)

    def raw_file(self, recording: str):
        """A local electrophysiology recording, fetching it if remote.

        Returns a :class:`~meanap.pipeline.io.RawSource` so an Axion plate
        carries which well this recording is. Raises :class:`FileNotFoundError`
        when no supported file exists.
        """
        from meanap.pipeline.io import RawSource, find_raw_file, split_well_suffix

        name = self.folder(recording)
        if not self.remote:
            found = find_raw_file(Path(self.store.root), name)
            if found is None:
                raise FileNotFoundError(
                    f"no raw recording for {name} in {self.store.root}")
            return found

        if self.cache is None:
            raise ValueError("A remote source needs a cache.")

        rel, well = None, None
        for ext in EPHYS_EXTENSIONS:
            if self.store.stat(f"{name}{ext}") is not None:
                rel = f"{name}{ext}"
                break
        if rel is None:
            split = split_well_suffix(name)
            if split is not None and self.store.stat(f"{split[0]}.raw") is not None:
                rel, well = f"{split[0]}.raw", split[1]
        if rel is None:
            raise FileNotFoundError(
                f"no raw recording for {name} "
                f"(looked for {', '.join(EPHYS_EXTENSIONS)})")

        entry = self.store.stat(rel)
        self._hold(recording, rel)
        cached = self.cache.path_for(self.store, rel)
        if not cached.exists():
            self.log(f"  [{recording}] fetching {(entry.size or 0) / 1e6:.0f} MB")
        return RawSource(self._fetch(rel, detail=recording), well)

    def release(self, recording: str) -> None:
        """Drop a recording's raw data now that its results are written.

        Called by the pipeline rather than inferred, because only the pipeline
        knows when the derived outputs are safely on disk. A file still held by
        another recording — an Axion plate shared between wells — is kept.
        Cheap and silent for a local source, which owns nothing to release.
        """
        if not self.remote or self.cache is None:
            return

        freed = 0
        for rel in self._rels_for(recording):
            users = self._holders[rel]
            users.discard(recording)
            if users:
                self.log(f"  [{recording}] keeping {Path(rel).name} — "
                         f"{len(users)} more recording(s) need it")
                continue
            del self._holders[rel]
            freed += self.cache.evict_prefix(self.store, rel)

        # CAT-NAP holds a folder rather than named files.
        freed += self.cache.evict_prefix(self.store, self.folder(recording))
        if freed:
            self.log(f"  [{recording}] released {freed / 1e6:.0f} MB "
                     f"(cache now {self.cache.usage() / 1e6:.0f} MB)")

    def stream(
        self, recordings: Iterable, depth: int = 1, kind: str = "catnap",
    ) -> Iterator[tuple[object, object]]:
        """Yield ``(recording, data)`` in order, fetching ahead when remote.

        ``kind`` selects what "data" means: a ``plane0`` directory for CAT-NAP,
        a :class:`RawSource` for electrophysiology. A local source yields
        immediately and does no work in the background — there is nothing to
        overlap, and a thread to hand back a path would only add a way to fail.
        """
        get = self.plane0 if kind == "catnap" else self.raw_file

        if not self.remote:
            for rec in recordings:
                try:
                    yield rec, get(rec.filename)
                except BaseException as exc:  # noqa: BLE001
                    yield rec, exc
            return

        def pin(rec) -> None:
            if self.cache is None:
                return
            self.cache.pin_prefix(self.store, self.folder(rec.filename))
            for rel in self._rels_for(rec.filename):
                self.cache.pin_prefix(self.store, rel)

        yield from stream_ahead(
            recordings, lambda rec: get(rec.filename), depth=depth, on_yield=pin,
        )

    def unpin(self, recording: str) -> None:
        """Release the eviction hold taken when this recording was handed over.

        Takes a name, like every other method here — the stream yields whole
        recording records, but the source is addressed by name throughout.
        """
        if not self.remote or self.cache is None:
            return
        self.cache.unpin_prefix(self.store, self.folder(recording))
        for rel in self._rels_for(recording):
            self.cache.unpin_prefix(self.store, rel)


def stream_needing_work(
    source: "RecordingSource",
    recordings: list,
    skip: Callable[[str], bool],
    *,
    depth: int = 1,
    kind: str = "catnap",
    stand_in: Callable[[object], object] | None = None,
) -> Iterator[tuple[object, object]]:
    """Like :meth:`RecordingSource.stream`, but never fetches a finished recording.

    A continued run knows which recordings are already done before it starts.
    Deciding that *after* the stream has handed one over — which is where the
    check naturally sits, next to the work it skips — means a remote source has
    already downloaded it. The compute is saved and the transfer is paid in
    full, and on a batch read over a share link the transfer is most of the run:
    continuing a Dropbox-hosted analysis took as long as never having continued.

    So the decision moves in front of the fetch. ``skip`` is asked about each
    recording by name; :meth:`RecordingSource.stream` yields in the order it is
    given, so the skipped ones splice back into their places and callers see the
    spreadsheet's order either way. What they see *for* a skipped recording is
    ``stand_in(rec)`` — a path that would have been fetched, for a caller that
    still wants one — or ``None``.

    Nothing is pinned or fetched for a skipped recording, so its caller must not
    ``unpin`` or ``release`` it either: there is no hold to drop.
    """
    todo = [rec for rec in recordings if not skip(rec.filename)]
    fetching = iter(source.stream(todo, depth=depth, kind=kind))
    for rec in recordings:
        if skip(rec.filename):
            yield rec, (stand_in(rec) if stand_in is not None else None)
        else:
            yield next(fetching)
