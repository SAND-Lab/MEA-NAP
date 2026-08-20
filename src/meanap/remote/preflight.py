"""Check a dataset can actually be analysed, before fetching a byte of it.

Listing a remote folder returns names *and sizes* without transferring
anything, so everything worth knowing up front is cheap: which recordings the
spreadsheet names are actually present, which are missing a file the pipeline
needs, how much will be downloaded, and whether it will fit in the cache
budget. A few dozen requests, seconds, no data.

The alternative is discovering at recording eleven of thirteen that one folder
never had a ``plane0`` — after an hour of downloading. Which is why this refuses
to start a run rather than warning and proceeding: a batch that silently
analyses twelve of thirteen recordings produces a result that looks complete.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from meanap.remote.base import RemoteStore

__all__ = [
    "CATNAP_REQUIRED", "CATNAP_OPTIONAL", "EPHYS_EXTENSIONS",
    "RecordingCheck", "PreflightReport", "run_preflight", "find_spreadsheet",
]

#: Without these, :func:`~meanap.catnap.loader.load_suite2p` cannot run.
CATNAP_REQUIRED = ("stat.npy", "F.npy", "iscell.npy", "ops.npy")

#: Fetched when present. ``spks.npy`` is needed only for that activity type;
#: the denoising outputs are produced locally when absent.
CATNAP_OPTIONAL = (
    "spks.npy", "Fdenoised.npy", "timePoints.npy",
    "peakStartFrames.npy", "peakEndFrames.npy", "peakHeights.npy",
    "eventAreas.npy",
)

EPHYS_EXTENSIONS = (".mat", ".h5", ".raw")

#: How many individual failures to spell out before summarising. A batch
#: spreadsheet can name hundreds of recordings; a report that lists every one
#: of them is a report nobody reads.
MAX_LISTED = 8

#: Throughput assumed for the time estimate. Measured at 6–9 MB/s against a
#: Dropbox share link; deliberately the pessimistic end, since an estimate that
#: turns out optimistic is the one that annoys.
ASSUMED_MB_PER_S = 6.0


@dataclass
class RecordingCheck:
    """What was found for one recording named by the spreadsheet."""

    name: str
    found: bool
    missing: list[str] = field(default_factory=list)
    fetch_bytes: int = 0
    skipped_bytes: int = 0
    needs_denoising: bool = False
    #: A folder that is present and looks like this recording under another
    #: name. Renamed folders are the commonest reason a batch silently shrinks.
    suggestion: str | None = None
    #: Everything needed is present, but the files contradict each other, so
    #: the recording will be skipped at load time.
    unusable: str | None = None

    @property
    def ok(self) -> bool:
        return self.found and not self.missing and not self.unusable


@dataclass
class PreflightReport:
    mode: str
    source: str
    spreadsheet: str | None
    recordings: list[RecordingCheck] = field(default_factory=list)
    unreferenced: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    budget_bytes: int = 0
    free_bytes: int = 0
    peak_bytes: int = 0

    @property
    def usable(self) -> list[RecordingCheck]:
        return [r for r in self.recordings if r.ok]

    @property
    def fetch_bytes(self) -> int:
        return sum(r.fetch_bytes for r in self.usable)

    @property
    def skipped_bytes(self) -> int:
        return sum(r.skipped_bytes for r in self.usable)

    @property
    def name_map(self) -> dict:
        """Spreadsheet name → the folder that actually holds it.

        Only unambiguous matches appear. Applying this is preferable to editing
        either side by hand: the spreadsheet is often shared or published, and
        the data folder is frequently read-only.
        """
        return {r.name: r.suggestion for r in self.recordings if r.suggestion}

    @property
    def ok(self) -> bool:
        return not self.problems and bool(self.usable)

    def render(self) -> str:
        """The report a user reads before committing to a run."""
        gb = 1e9
        lines = [f"Source: {self.source}", f"Mode:   {self.mode}"]
        if self.spreadsheet:
            lines.append(f"Batch:  {self.spreadsheet}")
        lines.append("")

        ok = self.usable
        lines.append(f"  ✓ {len(ok)} of {len(self.recordings)} recordings ready")

        failed = [r for r in self.recordings if not r.ok]
        for rec in failed[:MAX_LISTED]:
            if not rec.found:
                why = "not found"
            elif rec.missing:
                why = "missing " + ", ".join(rec.missing)
            else:
                why = rec.unusable or "unusable"
            hint = (f"\n      ↳ the folder '{rec.suggestion}' looks like this "
                    "recording under a different name" if rec.suggestion else "")
            lines.append(f"  ✗ {rec.name} — {why}{hint}")
        rest = failed[MAX_LISTED:]
        if rest:
            why = ("not found" if all(not r.found for r in rest)
                   else "that cannot be used")
            lines.append(f"  ✗ …and {len(rest)} more {why}")

        unmatched = [n for n in self.unreferenced
                     if n not in {r.suggestion for r in self.recordings}]
        for name in unmatched[:MAX_LISTED]:
            lines.append(f"  ! {name} — present but not in the spreadsheet")
        if len(unmatched) > MAX_LISTED:
            lines.append(f"  ! …and {len(unmatched) - MAX_LISTED} more unreferenced")

        denoise = [r for r in ok if r.needs_denoising]
        if denoise:
            lines.append(f"  · {len(denoise)} of {len(ok)} need denoising, "
                         "which will run locally")

        lines.append("")
        if self.fetch_bytes:
            mins = self.fetch_bytes / 1e6 / ASSUMED_MB_PER_S / 60
            lines.append(f"  Download      {self.fetch_bytes / gb:6.2f} GB"
                         + (f"   ({self.skipped_bytes / gb:.2f} GB skipped — "
                            "files the pipeline never opens)"
                            if self.skipped_bytes else ""))
            lines.append(f"  Est. transfer {mins:6.0f} min at "
                         f"{ASSUMED_MB_PER_S:.0f} MB/s")
        if self.budget_bytes:
            fits = "OK" if self.peak_bytes <= self.budget_bytes else "TOO SMALL"
            lines.append(f"  Peak storage  {self.peak_bytes / gb:6.2f} GB"
                         f"   (budget {self.budget_bytes / gb:.2f} GB, "
                         f"{self.free_bytes / gb:.0f} GB free)  {fits}")

        for w in self.warnings:
            lines.append(f"\n  Warning: {w}")
        for p in self.problems:
            lines.append(f"\n  Problem: {p}")
        return "\n".join(lines)


def find_spreadsheet(store: RemoteStore, configured: str = "") -> str | None:
    """Locate the batch spreadsheet within the source.

    Prefers what the user configured; otherwise falls back to a single ``.csv``
    at the top level, which is how a shared folder is usually laid out. Two or
    more candidates is ambiguous, so it asks rather than guessing.
    """
    if configured:
        name = Path(configured).name
        if store.stat(name) is not None:
            return name
        if Path(configured).exists():
            return configured
        return None
    csvs = [e.path for e in store.list()
            if not e.is_dir and fnmatch.fnmatch(e.path.lower(), "*.csv")]
    return csvs[0] if len(csvs) == 1 else None


#: A ``.npy`` written by numpy for a plain numeric array: 10-byte magic and
#: version, then a header dict padded so the data starts on a 64-byte boundary.
#: Simple dtypes always land in the first such block.
_NPY_HEADER = 128


def _empty_required(empty: list[str]) -> str | None:
    """Message for required files that are present but zero bytes."""
    if not empty:
        return None
    return (f"{', '.join(sorted(empty))} "
            f"{'is' if len(empty) == 1 else 'are'} zero bytes at the source — "
            f"the suite2p export is incomplete and will not load "
            f"(re-export this recording)")


def _roi_mismatch(entries: dict) -> str | None:
    """Detect an ``iscell.npy`` that cannot belong to the ``F.npy`` beside it.

    From sizes alone, which is all a listing gives. ``iscell`` is always an
    ``(n_rois, 2)`` float64 array, so its row count is exact; ``F`` is an
    ``(n_rois, n_frames)`` float32 one, so its element count must be a multiple
    of that row count. When it is not, no frame count can reconcile the two and
    the folder is provably inconsistent — worth catching here, because the
    alternative is finding out after downloading half a gigabyte and denoising
    every ROI in it (see :func:`meanap.catnap.loader._check_roi_counts` for what
    causes it and how to repair it).

    Deliberately one-sided: a folder that passes may still be misaligned by a
    number of rows that happens to divide, which the loader catches exactly.
    Returns ``None`` unless the counts are *impossible*.
    """
    iscell, f = entries.get("iscell.npy"), entries.get("F.npy")
    # Zero-size is not a *mismatch* — it is caught by _empty_required, which
    # gives the more useful message.
    if iscell is None or f is None or not iscell.size or not f.size:
        return None

    iscell_bytes, f_bytes = iscell.size - _NPY_HEADER, f.size - _NPY_HEADER
    if iscell_bytes <= 0 or f_bytes <= 0 or iscell_bytes % 16 or f_bytes % 4:
        return None  # not the layout assumed above; leave it to the loader

    n_rois = iscell_bytes // 16
    # float32 is what suite2p writes, but a float64 F would halve the count, so
    # only flag a folder that fits neither.
    if any(f_bytes % (n_rois * width) == 0 for width in (4, 8)):
        return None
    return (f"iscell.npy describes {n_rois} ROIs, which does not divide "
            "F.npy — the suite2p output is inconsistent and will not load "
            "(re-save the recording in the suite2p GUI)")


def _check_catnap(store: RemoteStore, name: str) -> RecordingCheck:
    plane0 = f"{name}/suite2p/plane0"
    entries = {e.name: e for e in store.list(plane0)}
    if not entries:
        return RecordingCheck(name=name, found=False,
                              missing=["suite2p/plane0"])

    # A zero-byte file is present by name and unusable in fact: np.load gives
    # "No data left in file", which names neither the file nor the recording.
    # Listing sizes catch it here, before a byte is downloaded.
    missing = [f for f in CATNAP_REQUIRED if f not in entries]
    empty = [f for f in CATNAP_REQUIRED
             if f in entries and entries[f].size == 0]
    wanted = set(CATNAP_REQUIRED) | set(CATNAP_OPTIONAL)
    fetch = sum(e.size or 0 for n, e in entries.items() if n in wanted)
    skipped = sum(e.size or 0 for n, e in entries.items() if n not in wanted)
    return RecordingCheck(
        name=name, found=True, missing=missing,
        fetch_bytes=fetch, skipped_bytes=skipped,
        needs_denoising="Fdenoised.npy" not in entries,
        unusable=_empty_required(empty) or _roi_mismatch(entries),
    )


def _check_ephys(store: RemoteStore, name: str) -> RecordingCheck:
    for ext in EPHYS_EXTENSIONS:
        entry = store.stat(f"{name}{ext}")
        if entry is not None:
            return RecordingCheck(name=name, found=True,
                                  fetch_bytes=entry.size or 0)
    return RecordingCheck(
        name=name, found=False,
        missing=[f"{name}{{{','.join(EPHYS_EXTENSIONS)}}}"])


def _suggest_renames(report: PreflightReport) -> None:
    """Point each missing recording at a present folder that resembles it."""
    from meanap.pipeline.spreadsheet import match_recording_name

    leftovers = list(report.unreferenced)
    for rec in report.recordings:
        if rec.found:
            continue
        hit = match_recording_name(rec.name, leftovers)
        if hit is not None:
            rec.suggestion = hit
            leftovers.remove(hit)

    renamed = [r for r in report.recordings if r.suggestion]
    if renamed:
        report.problems.append(
            f"{len(renamed)} recording(s) exist in the source under a slightly "
            f"different folder name (e.g. '{renamed[0].name}' vs "
            f"'{renamed[0].suggestion}'). Rename the folders, or edit the "
            "spreadsheet to match — otherwise they will be silently skipped.")


def run_preflight(
    store: RemoteStore,
    recording_names: list[str],
    *,
    mode: str = "catnap",
    spreadsheet: str | None = None,
    cache_dir: Path | str | None = None,
    cache_budget_gb: float | None = None,
    prefetch_depth: int = 1,
) -> PreflightReport:
    """Inspect a source and report whether the named recordings can be analysed.

    Does no transfer beyond folder listings. ``recording_names`` comes from the
    batch spreadsheet; anything present in the source but not named there is
    reported as unreferenced rather than silently analysed or silently ignored.
    """
    report = PreflightReport(mode=mode, source=str(store),
                             spreadsheet=spreadsheet)

    check = _check_catnap if mode == "catnap" else _check_ephys
    for name in recording_names:
        report.recordings.append(check(store, name))

    named = set(recording_names)
    present = [e.name for e in store.list() if e.is_dir]
    report.unreferenced = [n for n in present if n not in named]

    # Match renamed folders back to the spreadsheet. A folder gaining a suffix
    # ("… David Oluigbo") is invisible to an exact-name lookup, and the result
    # is a batch that quietly analyses a fraction of what was asked for — the
    # exact failure this whole check exists to prevent.
    _suggest_renames(report)

    if not report.usable:
        report.problems.append(
            "No recording in the spreadsheet has the files this mode needs — "
            "check that the source folder and the spreadsheet describe the "
            "same dataset.")
    elif len(report.usable) < len(report.recordings):
        n = len(report.recordings) - len(report.usable)
        report.warnings.append(
            f"{n} recording(s) will be skipped. Batch comparisons and the "
            "node-cartography boundaries are computed across whichever "
            "recordings actually run, so results will not match a complete "
            "batch.")

    if store.copies and cache_dir is not None:
        from meanap.remote.cache import CacheFull, resolve_budget

        largest = max((r.fetch_bytes for r in report.usable), default=0)
        report.peak_bytes = largest * (prefetch_depth + 1)
        try:
            report.budget_bytes = resolve_budget(
                cache_dir, cache_budget_gb, required_bytes=report.peak_bytes)
        except CacheFull as e:
            report.problems.append(str(e))
            report.budget_bytes = 0
        import shutil
        probe = Path(cache_dir)
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        report.free_bytes = shutil.disk_usage(probe).free

    return report
